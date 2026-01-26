#!/usr/bin/env bash
set -euo pipefail

# 服务器端部署脚本：
# - 拉取最新 main
# - 重新构建并重启 docker compose

APP_DIR="/root/mnt2/mydocker2/auto_github/xinliuend"

cd "$APP_DIR"

echo "[deploy] sync git main ..."
git fetch --all --prune
git reset --hard origin/main

echo "[deploy] docker compose up ..."

# 支持通过环境变量启用 profile（例如：export DEPLOY_COMPOSE_PROFILES=postgres）
PROFILE_ARGS=()
if [[ -n "${DEPLOY_COMPOSE_PROFILES:-}" ]]; then
  # 允许传入多个 profile：postgres,xxx
  IFS=',' read -r -a _profiles <<< "${DEPLOY_COMPOSE_PROFILES}"
  for p in "${_profiles[@]}"; do
    p_trimmed="$(echo "$p" | xargs)"
    [[ -n "$p_trimmed" ]] && PROFILE_ARGS+=(--profile "$p_trimmed")
  done
fi

docker compose "${PROFILE_ARGS[@]}" up -d --build --remove-orphans

echo "[deploy] done."

