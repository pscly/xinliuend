@echo off
setlocal enabledelayedexpansion

REM 一键启动（Windows）
REM 约定：依赖用 uv 管理；启动前先跑数据库迁移（Alembic）

if not exist ".venv" (
  echo [run] .venv not found, running: uv sync
  uv sync
)

echo [run] migrate db: alembic upgrade head
uv run alembic -c alembic.ini upgrade head

echo [run] start server on :31031
uv run uvicorn flow_backend.main:app --host 0.0.0.0 --port 31031 --reload

