from __future__ import annotations

from contextlib import asynccontextmanager
from functools import lru_cache
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.config import settings
from flow_backend.db_urls import normalize_database_url_for_async


def _create_async_engine(database_url: str) -> AsyncEngine:
    # 运行时统一使用异步 driver，避免在 Docker/线上因默认 driver 选择导致不可预期行为
    url = normalize_database_url_for_async(database_url)
    return create_async_engine(url, echo=False, pool_pre_ping=True)


@lru_cache(maxsize=4)
def get_engine() -> AsyncEngine:
    # 允许测试/部署时通过环境变量或 settings 覆写 DATABASE_URL 后重建 engine
    return _create_async_engine(settings.database_url)


def reset_engine_cache() -> None:
    get_engine.cache_clear()


async def init_db() -> None:
    # 仅用于本地/测试场景兜底；生产以 Alembic 迁移为准
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    session_maker = async_sessionmaker(get_engine(), class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        yield session


async def get_session() -> AsyncIterator[AsyncSession]:
    session_maker = async_sessionmaker(get_engine(), class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        yield session

