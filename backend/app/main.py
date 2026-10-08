"""FastAPI application entry point."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router as health_router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = get_settings()
    configure_logging(settings)
    logger.info(
        "startup app=%s llm_provider=%s threshold=%s",
        settings.app_name,
        settings.llm_provider,
        settings.confidence_threshold,
    )
    yield
    logger.info("shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description=(
            "Agentic document verification for RWA tokenization. "
            "This system flags risks only; it never provides investment advice."
        ),
        lifespan=lifespan,
    )
    app.include_router(health_router, prefix="")
    # Phase 4 will add: /cases, /cases/{id}/documents, /cases/{id}/run,
    # /cases/{id}/report, /review-tasks
    return app


app = create_app()
