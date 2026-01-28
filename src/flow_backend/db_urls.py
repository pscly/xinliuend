from __future__ import annotations


def normalize_database_url_for_async(database_url: str) -> str:
    """
    将用户给的 DATABASE_URL 规范化为「运行时可用的异步 driver」。

    约定：
    - SQLite：sqlite+aiosqlite://...
    - PostgreSQL：postgresql+psycopg://... （psycopg3 自带 async 支持，兼容 SQLAlchemy AsyncEngine）
    """
    url = (database_url or "").strip()
    if not url:
        return url

    # SQLite
    if url.startswith("sqlite://") and "+aiosqlite" not in url:
        return url.replace("sqlite://", "sqlite+aiosqlite://", 1)

    # PostgreSQL：兼容 postgres:// 与默认 driver（psycopg2）
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]

    if url.startswith("postgresql+psycopg2://"):
        return url.replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)

    return url


def normalize_database_url_for_alembic(database_url: str) -> str:
    """
    Alembic 默认使用同步 engine 连接数据库（engine_from_config）。

    为避免 Alembic 误用异步 driver（如 aiosqlite/asyncpg）导致迁移失败，这里做同步 driver 规范化：
    - sqlite+aiosqlite:// -> sqlite://
    - postgresql:// -> postgresql+psycopg:// （强制 psycopg3，避免落回 psycopg2）
    """
    url = (database_url or "").strip()
    if not url:
        return url

    if url.startswith("sqlite+aiosqlite://"):
        return url.replace("sqlite+aiosqlite://", "sqlite://", 1)

    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]

    if url.startswith("postgresql+psycopg2://"):
        return url.replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)

    return url
