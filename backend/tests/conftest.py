"""Shared pytest fixtures: in-memory SQLite DB + FastAPI test client."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.db import get_db
from app.main import create_app


@pytest.fixture()
def test_settings() -> Settings:
    """Settings with mock provider; DB URL irrelevant (in-memory engine below)."""
    return Settings(
        DATABASE_URL="sqlite://",
        LLM_PROVIDER="mock",
        STORAGE_DIR="./storage_test",
    )  # type: ignore[call-arg]


@pytest.fixture()
def db_session(test_settings: Settings):
    """Function-scoped in-memory SQLAlchemy session with all tables created."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    import app.models  # noqa: F401  (register tables)

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    from app.models.base import Base

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def client(db_session, test_settings: Settings):
    """TestClient wired to the in-memory DB and test settings."""
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    from app.core.config import get_settings

    app.dependency_overrides[get_settings] = lambda: test_settings
    with TestClient(app) as c:
        yield c
