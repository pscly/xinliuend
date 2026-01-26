from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
from typing import Iterator

from sqlmodel import Session, SQLModel, create_engine

from flow_backend.config import settings


def _create_engine(database_url: str):
    connect_args = {}
    if database_url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
    return create_engine(database_url, echo=False, connect_args=connect_args)


@lru_cache(maxsize=4)
def get_engine():
    # 允许测试/部署时通过环境变量或 settings 覆写 DATABASE_URL 后重建 engine
    return _create_engine(settings.database_url)


def reset_engine_cache() -> None:
    get_engine.cache_clear()


def init_db() -> None:
    SQLModel.metadata.create_all(get_engine())


@contextmanager
def session_scope() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session


def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session
