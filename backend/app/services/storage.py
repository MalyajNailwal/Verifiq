"""Storage service — local filesystem for MVP, S3-compatible later.

Files live under:  {STORAGE_DIR}/cases/{case_id}/{doc_type}/{sha8}__{filename}
Content-addressed prefix avoids collisions when the same filename is re-uploaded.
"""

import hashlib
import logging
import re
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")

# Max upload size: 50 MB (guard against pathological files).
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


class StorageError(Exception):
    """Raised when a file cannot be stored or read."""


def sanitize_filename(name: str) -> str:
    """Strip path components and unsafe characters from a filename."""
    base = Path(name).name
    cleaned = _UNSAFE_CHARS.sub("_", base).strip("._") or "file"
    return cleaned[:200]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class LocalStorage:
    """Local-filesystem storage backend."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    def save_bytes(
        self, case_id: uuid.UUID, doc_type: str, filename: str, data: bytes
    ) -> dict[str, object]:
        """Persist an upload; returns path, sha256, size. Idempotent per content."""
        if len(data) > MAX_UPLOAD_BYTES:
            raise StorageError(f"file too large: {len(data)} bytes > {MAX_UPLOAD_BYTES}")
        if not data:
            raise StorageError("empty file")

        safe_name = sanitize_filename(filename)
        digest = sha256_bytes(data)
        target_dir = self.root / "cases" / str(case_id) / doc_type
        target = target_dir / f"{digest[:8]}__{safe_name}"
        if not target.exists():
            target_dir.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            logger.info("stored file path=%s bytes=%d", target, len(data))
        return {
            "path": str(target.relative_to(self.root)),
            "absolute_path": str(target),
            "sha256": digest,
            "size": len(data),
        }

    def read_bytes(self, rel_path: str) -> bytes:
        """Read a stored file by its relative path (no traversal allowed)."""
        target = (self.root / rel_path).resolve()
        if not str(target).startswith(str(self.root)):
            raise StorageError(f"path traversal blocked: {rel_path}")
        if not target.is_file():
            raise StorageError(f"file not found: {rel_path}")
        return target.read_bytes()

    def exists(self, rel_path: str) -> bool:
        return (self.root / rel_path).is_file()
