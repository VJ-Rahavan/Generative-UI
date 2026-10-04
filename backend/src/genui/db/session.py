"""Async engine/session management. Schema is created with `create_all` (no migrations)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from genui.db.base import Base

SessionFactory = async_sessionmaker[AsyncSession]


class Database:
    def __init__(self, url: str, *, echo: bool = False) -> None:
        self.is_sqlite = url.startswith("sqlite")
        self.engine = create_async_engine(url, echo=echo, pool_pre_ping=not self.is_sqlite)
        if self.is_sqlite:
            event.listen(self.engine.sync_engine, "connect", _enable_sqlite_foreign_keys)
        self.session_factory: SessionFactory = async_sessionmaker(
            self.engine, expire_on_commit=False
        )

    async def create_all(self) -> None:
        # Import models so they register on Base.metadata before create_all.
        import genui.db.models  # noqa: F401
        import genui.domain.fitness.models  # noqa: F401

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as session:
            yield session

    async def dispose(self) -> None:
        await self.engine.dispose()


def _enable_sqlite_foreign_keys(dbapi_conn: Any, _record: Any) -> None:
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
