@echo off
setlocal enabledelayedexpansion

REM 一键启动（Windows）
REM 说明：你当前报的 "relation users does not exist" 本质是数据库未跑迁移；
REM      该脚本会在启动前自动执行 Alembic upgrade head。

if not exist ".venv" (
  echo [run] .venv not found, running: uv sync
  uv sync
)

echo [run] migrate db: alembic upgrade head
uv run alembic -c alembic.ini upgrade head

echo [run] start server on :31031
uv run uvicorn flow_backend.main:app --host 0.0.0.0 --port 31031 --reload
