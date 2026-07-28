"""Database engine and session management."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from appforge.config import get_settings
from appforge.models import Base


def _engine_kwargs(url: str) -> dict:
    if url.startswith("sqlite"):
        # SQLite is used for tests; allow cross-thread use with a shared pool.
        from sqlalchemy.pool import StaticPool

        return {"connect_args": {"check_same_thread": False}, "poolclass": StaticPool}
    return {"pool_pre_ping": True, "pool_size": 10, "max_overflow": 20}


_settings = get_settings()
engine = create_engine(_settings.database_url, future=True, **_engine_kwargs(_settings.database_url))
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def init_db() -> None:
    """Create tables when they do not exist (Alembic owns production migrations)."""
    Base.metadata.create_all(bind=engine)


def get_session() -> Iterator[Session]:
    """FastAPI dependency."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Context manager for worker/agent code."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
