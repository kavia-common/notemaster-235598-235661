import os
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


def _to_asyncpg_url(url: str) -> str:
    """
    Convert a sync PostgreSQL URL to an asyncpg SQLAlchemy URL if needed.
    """
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        # Some platforms still use postgres://
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


def get_database_url() -> str:
    """
    Read the database URL from environment.

    We prefer POSTGRES_URL (provided by the notes_db container) but allow DATABASE_URL
    as a fallback for flexibility.

    Expected env vars (provided by platform/orchestrator):
      - POSTGRES_URL (preferred) or DATABASE_URL
    """
    url = os.getenv("POSTGRES_URL") or os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "Database URL is not configured. Please set POSTGRES_URL (preferred) or DATABASE_URL in the environment."
        )
    return _to_asyncpg_url(url)


_ENGINE: Optional[AsyncEngine] = None
_SESSIONMAKER: Optional[async_sessionmaker[AsyncSession]] = None


def get_engine() -> AsyncEngine:
    """
    Singleton async SQLAlchemy engine.
    """
    global _ENGINE, _SESSIONMAKER
    if _ENGINE is None:
        _ENGINE = create_async_engine(
            get_database_url(),
            pool_pre_ping=True,
        )
        _SESSIONMAKER = async_sessionmaker(bind=_ENGINE, expire_on_commit=False, class_=AsyncSession)
    return _ENGINE


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """
    Singleton sessionmaker bound to the engine.
    """
    if _SESSIONMAKER is None:
        get_engine()
    assert _SESSIONMAKER is not None
    return _SESSIONMAKER


# PUBLIC_INTERFACE
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async DB session (and closes it)."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        yield session
