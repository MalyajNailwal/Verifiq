"""Health endpoint with DB and LLM provider probes."""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_db

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/health")
def health(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict:
    """Liveness + dependency status. Never raises: reports degraded state instead."""
    db_ok = True
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 — health must not 500
        db_ok = False
        logger.warning("health_db_check_failed err=%s", exc)

    return {
        "status": "ok" if db_ok else "degraded",
        "app": settings.app_name,
        "database": "ok" if db_ok else "unreachable",
        "llm_provider": settings.llm_provider,
        "confidence_threshold": settings.confidence_threshold,
    }
