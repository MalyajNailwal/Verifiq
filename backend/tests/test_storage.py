"""LocalStorage tests."""

import uuid

import pytest

from app.services.storage import LocalStorage, StorageError, sanitize_filename, sha256_bytes


def test_save_and_read_roundtrip(tmp_path) -> None:
    storage = LocalStorage(tmp_path)
    case_id = uuid.uuid4()
    data = b"title deed contents"
    out = storage.save_bytes(case_id, "title_deed", "my deed.pdf", data)

    assert out["sha256"] == sha256_bytes(data)
    assert out["size"] == len(data)
    assert storage.exists(out["path"])
    assert storage.read_bytes(out["path"]) == data
    # deterministic: same content => same path
    again = storage.save_bytes(case_id, "title_deed", "my deed.pdf", data)
    assert again["path"] == out["path"]


def test_sanitize_filename_blocks_traversal(tmp_path) -> None:
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("a/b/c.txt") == "c.txt"
    assert sanitize_filename("we ird$$name.pdf") == "we_ird_name.pdf"


def test_read_blocks_path_traversal(tmp_path) -> None:
    storage = LocalStorage(tmp_path)
    with pytest.raises(StorageError, match="traversal"):
        storage.read_bytes("../outside.txt")


def test_rejects_empty_and_oversized(tmp_path) -> None:
    storage = LocalStorage(tmp_path)
    with pytest.raises(StorageError, match="empty"):
        storage.save_bytes(uuid.uuid4(), "other", "x.txt", b"")
    with pytest.raises(StorageError, match="too large"):
        storage.save_bytes(uuid.uuid4(), "other", "x.txt", b"x" * (51 * 1024 * 1024))
