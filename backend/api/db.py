import asyncio
import logging

from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession as AsyncSQLModelSession

from api.config import config

logger = logging.getLogger("uvicorn.error")

engine = None


def get_engine(db_url: str | None = None):
    global engine
    if engine is None:
        url = db_url or config.DB_URL
        kwargs: dict = {
            "pool_pre_ping": True,
        }
        if url.startswith("postgresql"):  # Skip for SQLite
            kwargs.update(
                pool_size=5,
                max_overflow=10,
                # Reclaim connections older than this (seconds)
                pool_recycle=1800,
                # Reuse the most-recently-used connection first
                pool_use_lifo=True,
                # How long to wait for a connection from the pool before raising
                pool_timeout=30,
            )
        engine = create_async_engine(url, **kwargs)
    return engine


async def dispose_engine():
    """Dispose the async engine and its connection pool on shutdown."""
    global engine
    if engine is not None:
        await engine.dispose()
        engine = None


async def _retry_on_db_error(
    coro_factory,
    *,
    operation_name: str = "database operation",
    max_retries: int = 10,
    retry_interval: float = 2.0,
):
    last_exception: Exception | None = None

    for attempt in range(max_retries):
        try:
            return await coro_factory()
        except (OSError, OperationalError) as exc:
            last_exception = exc
            logger.warning(
                f"{operation_name} attempt {attempt + 1}/{max_retries} failed: {exc}"
            )
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_interval)

    if last_exception is not None:
        raise last_exception
    raise RuntimeError(f"Failed {operation_name} after {max_retries} attempts")


async def create_db_and_tables(db_url: str | None = None):
    e = get_engine(db_url)

    async def _create():
        async with e.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

    await _retry_on_db_error(
        _create,
        operation_name="Database connection",
    )


async def get_session(db_url: str | None = None):
    e = get_engine(db_url)

    async def _connect():
        async with e.connect() as conn:
            pass

    await _retry_on_db_error(
        _connect,
        operation_name="Database connection",
    )

    async with AsyncSQLModelSession(e) as session:
        yield session
