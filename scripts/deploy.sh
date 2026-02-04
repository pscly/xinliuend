#!/usr/bin/env bash
set -euo pipefail

# 服务器端部署脚本（Docker Compose）：
# - 幂等：反复执行不会产生副作用
# - 保守：默认不清理 ignored 文件，避免误删服务器上的私有 .env
# - 可配置：支持自定义目录/分支/profile

ts() { date '+%F %T'; }
log() { echo "[$(ts)] [deploy] $*"; }
die() { echo "[$(ts)] [deploy] ERROR: $*" >&2; exit 1; }

APP_DIR="${APP_DIR:-/root/dockers/1auto/xinliuend}"
GIT_REMOTE="${GIT_REMOTE:-origin}"
GIT_BRANCH="${GIT_BRANCH:-main}"

# If the caller already updated the repo, we can skip the redundant fetch/reset.
DEPLOY_SKIP_GIT="${DEPLOY_SKIP_GIT:-false}"

# 支持通过环境变量启用 compose profile（例如：export DEPLOY_COMPOSE_PROFILES=postgres）
DEPLOY_COMPOSE_PROFILES="${DEPLOY_COMPOSE_PROFILES:-}"

# 是否在部署前清空 volumes（危险！会删除持久化数据）
DEPLOY_WIPE_VOLUMES="${DEPLOY_WIPE_VOLUMES:-false}"

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

if [[ "${DEPLOY_SKIP_GIT}" == "true" ]]; then
  log "跳过 git 同步（DEPLOY_SKIP_GIT=true）"
else
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

# 规范：确保宿主机持久化目录存在（compose bind mount 目标）
mkdir -p data

log "构建并启动：docker compose up -d --build --remove-orphans"

DOWN_ARGS=(down --remove-orphans)
if [[ "${DEPLOY_WIPE_VOLUMES}" == "true" ]]; then
  DOWN_ARGS=(down -v --remove-orphans)
  log "停止并清空数据：docker compose down -v --remove-orphans（将删除 volumes/持久化数据）"
else
  log "停止：docker compose down --remove-orphans（保留 volumes；如需清空请设 DEPLOY_WIPE_VOLUMES=true）"
fi

docker compose "${PROFILE_ARGS[@]}" "${DOWN_ARGS[@]}"

is_dockerhub_rate_limit_error() {
  local logfile="$1"
  grep -qiE 'toomanyrequests|429[[:space:]]+Too[[:space:]]+Many[[:space:]]+Requests|rate[[:space:]]+limit' "${logfile}"
}

compose_up_with_env() {
  # Usage:
  #   compose_up_with_env            # normal
  #   compose_up_with_env KEY=VALUE  # with env overrides (compose interpolation/build args)
  local -a envs=("$@")

  local tmp_log
  tmp_log="$(mktemp -t xinliuend-compose-up.XXXXXX.log)"

  if [[ ${#envs[@]} -gt 0 ]]; then
    log "执行（带 env 覆写）：${envs[*]} docker compose up -d --build --remove-orphans"
  else
    log "执行：docker compose up -d --build --remove-orphans"
  fi

  set +e
  env "${envs[@]}" docker compose "${PROFILE_ARGS[@]}" up -d --build --remove-orphans 2>&1 | tee "${tmp_log}"
  local status=${PIPESTATUS[0]}
  set -e

  if [[ ${status} -eq 0 ]]; then
    rm -f "${tmp_log}" >/dev/null 2>&1 || true
    return 0
  fi

  # 若遇到 Docker Hub 未登录拉取限流，给出可控 fallback（不改变默认行为）
  if [[ ${#envs[@]} -eq 0 ]] && is_dockerhub_rate_limit_error "${tmp_log}"; then
    log "检测到 Docker Hub 拉取限流（429/toomanyrequests），将尝试使用镜像加速源进行一次重试"

    local fallback_node_image="${DEPLOY_FALLBACK_NODE_IMAGE:-docker.m.daocloud.io/library/node:20-alpine}"
    local fallback_python_image="${DEPLOY_FALLBACK_PYTHON_IMAGE:-docker.m.daocloud.io/library/python:3.11-slim}"
    local fallback_npm_registry="${DEPLOY_FALLBACK_NPM_REGISTRY:-https://registry.npmmirror.com}"

    log "fallback：NODE_IMAGE=${fallback_node_image}"
    log "fallback：PYTHON_IMAGE=${fallback_python_image}"
    log "fallback：NPM_REGISTRY=${fallback_npm_registry}"

    compose_up_with_env \
      "NODE_IMAGE=${fallback_node_image}" \
      "PYTHON_IMAGE=${fallback_python_image}" \
      "NPM_REGISTRY=${fallback_npm_registry}"
    return 0
  fi

  die "docker compose up 失败（exit=${status}），日志：${tmp_log}"
}

compose_up_with_env

log "当前容器状态："
docker compose "${PROFILE_ARGS[@]}" ps

log "完成"
