#!/usr/bin/env bash
set -euo pipefail

# 服务器端部署脚本（Docker Compose）：
# - 幂等：反复执行不会产生副作用
# - 保守：默认不清理 ignored 文件，避免误删服务器上的私有 .env
# - 可配置：支持自定义目录/分支/profile

ts() { date '+%F %T'; }
log() { echo "[$(ts)] [deploy] $*"; }
die() { echo "[$(ts)] [deploy] ERROR: $*" >&2; exit 1; }

APP_DIR="${APP_DIR:-/root/mnt2/mydocker2/auto_github/xinliuend}"
GIT_REMOTE="${GIT_REMOTE:-origin}"
GIT_BRANCH="${GIT_BRANCH:-main}"

# 支持通过环境变量启用 compose profile（例如：export DEPLOY_COMPOSE_PROFILES=postgres）
DEPLOY_COMPOSE_PROFILES="${DEPLOY_COMPOSE_PROFILES:-}"

# 简单的互斥锁：避免同一台机器并发部署互相踩踏
LOCK_DIR="${DEPLOY_LOCK_DIR:-/tmp/xinliuend-deploy.lock}"
if mkdir "${LOCK_DIR}" 2>/dev/null; then
  trap 'rmdir "${LOCK_DIR}" >/dev/null 2>&1 || true' EXIT
else
  die "检测到正在部署（lock=${LOCK_DIR}），请稍后再试"
fi

command -v git >/dev/null 2>&1 || die "缺少 git"
command -v docker >/dev/null 2>&1 || die "缺少 docker"
docker compose version >/dev/null 2>&1 || die "缺少 docker compose（请安装 compose 插件）"

[[ -d "${APP_DIR}" ]] || die "目录不存在：${APP_DIR}"
cd "${APP_DIR}"
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "不是 git 仓库：${APP_DIR}"

log "当前目录：${APP_DIR}"
if [[ -f ".env" ]]; then
  log "检测到 .env（将由 docker compose 加载）"
else
  log "未检测到 .env（若你依赖 .env 注入配置，请在服务器创建它）"
fi

log "同步代码：${GIT_REMOTE}/${GIT_BRANCH}"
before_sha="$(git rev-parse HEAD || true)"
git fetch "${GIT_REMOTE}" "${GIT_BRANCH}" --prune
git reset --hard "${GIT_REMOTE}/${GIT_BRANCH}"
after_sha="$(git rev-parse HEAD || true)"
if [[ -n "${before_sha}" && -n "${after_sha}" && "${before_sha}" != "${after_sha}" ]]; then
  log "代码已更新：${before_sha:0:7} -> ${after_sha:0:7}"
else
  log "代码无变化（仍为 ${after_sha:0:7}）"
fi

PROFILE_ARGS=()
if [[ -n "${DEPLOY_COMPOSE_PROFILES}" ]]; then
  IFS=',' read -r -a _profiles <<< "${DEPLOY_COMPOSE_PROFILES}"
  for p in "${_profiles[@]}"; do
    p_trimmed="$(echo "${p}" | xargs)"
    [[ -n "${p_trimmed}" ]] && PROFILE_ARGS+=(--profile "${p_trimmed}")
  done
  log "启用 compose profiles：${DEPLOY_COMPOSE_PROFILES}"
fi

log "构建并启动：docker compose up -d --build --remove-orphans"
log "强制清理：docker compose down -v --remove-orphans（会删除 volumes/持久化数据）"
docker compose "${PROFILE_ARGS[@]}" down -v --remove-orphans

log "构建并启动：docker compose up -d --build --remove-orphans"
docker compose "${PROFILE_ARGS[@]}" up -d --build --remove-orphans

log "当前容器状态："
docker compose "${PROFILE_ARGS[@]}" ps

log "完成"
