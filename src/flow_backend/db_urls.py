from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote


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


def _strip_url_query_and_fragment(url: str) -> str:
    # SQLite URL 可能携带 query 参数（例如 check_same_thread 等）
    # 这里仅用于文件路径推断，因此忽略 query/fragment。
    url = url.split("#", 1)[0]
    url = url.split("?", 1)[0]
    return url


def extract_sqlite_db_file_path(database_url: str) -> Path | None:
    """从 SQLite DATABASE_URL 推断本地数据库文件路径（尽力而为）。

    支持：
    - sqlite:///./relative.db
    - sqlite:////abs/path.db
    - sqlite+aiosqlite:///./relative.db

    不处理：
    - sqlite:///:memory:
    - 非 sqlite URL
    """

    url = (database_url or "").strip()
    if not url:
        return None

    url = _strip_url_query_and_fragment(url)
    lower = url.lower()
    if not lower.startswith("sqlite"):
        return None

    # In-memory sqlite DB
    if lower.endswith(":memory:"):
        return None

    sep = url.find("://")
    if sep == -1:
        return None

    rest = url[sep + 3 :]
    # Example:
    # - sqlite:///./.data/dev.db -> rest = "/./.data/dev.db"
    # - sqlite:////tmp/a.db      -> rest = "//tmp/a.db"
    if rest.startswith(":memory:") or rest.startswith("/:memory:"):
        return None

    if rest.startswith("//"):
        # Absolute path (4 slashes after scheme): keep one leading slash.
        file_path = rest[1:]
    elif rest.startswith("/"):
        # Relative path (3 slashes after scheme): drop the leading slash.
        file_path = rest[1:]
    else:
        file_path = rest

    file_path = unquote(file_path)
    if not file_path or file_path == ":memory:":
        return None

    return Path(file_path)


def ensure_sqlite_parent_dir(database_url: str) -> None:
    """确保 SQLite 数据库文件的父目录存在。

    目的：当 DATABASE_URL 形如 `sqlite:///./.data/dev.db` 时，避免因为 `.data/` 不存在导致启动/迁移失败。
    """

    path = extract_sqlite_db_file_path(database_url)
    if path is None:
        return

    parent = path.parent
    # `dev.db` -> parent = "."，无需创建
    if str(parent) in {"", "."}:
        return

    parent.mkdir(parents=True, exist_ok=True)
