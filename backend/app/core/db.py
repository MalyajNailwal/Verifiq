"""SQLAlchemy engine/session management."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings


def _make_engine(database_url: str, echo: bool = False):
    """Create an engine; SQLite needs no pool tweaks, Postgres uses pre-ping."""
    if database_url.startswith("sqlite"):
        return create_engine(database_url, echo=echo, connect_args={"check_same_thread": False})
    return create_engine(database_url, echo=echo, pool_pre_ping=True)


def make_session_factory(settings: Settings | None = None) -> sessionmaker[Session]:
    """Build a sessionmaker bound to the configured database."""
    settings = settings or get_settings()
    engine = _make_engine(settings.database_url, echo=settings.db_echo)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


# Default factory for the running app; tests create their own.
SessionLocal = make_session_factory()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a DB session, always closed afterwards."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
