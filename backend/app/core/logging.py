"""Structured logging setup for the whole backend."""

import logging
import sys

from app.core.config import Settings

_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def configure_logging(settings: Settings) -> None:
    """Configure root logging once, idempotently."""
    root = logging.getLogger()
    if root.handlers:  # already configured (e.g. uvicorn did it)
        root.setLevel(settings.log_level.upper())
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())
    # Quiet down noisy third-party loggers.
    for name in ("httpx", "httpcore", "urllib3", "botocore"):
        logging.getLogger(name).setLevel(logging.WARNING)
