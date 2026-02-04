# syntax=docker/dockerfile:1.6

#
# 说明：
# - 本仓库包含 `web/`（Next.js）前端，且使用 `output: "export"` 静态导出到 `web/out/`
# - 后端在启动时会“尽力”挂载 `web/out` 到 `/`（同源），从而简化 Cookie Session / CSRF / CORS
# - 因此这里采用 multi-stage：在构建镜像时产出静态站并 COPY 到最终镜像中
#

ARG NODE_IMAGE=node:20-alpine
ARG PYTHON_IMAGE=python:3.11-slim

FROM ${NODE_IMAGE} AS web_builder

WORKDIR /web

# 禁用 Next telemetry；避免在构建日志里产生干扰
ENV NEXT_TELEMETRY_DISABLED=1

# 生产镜像构建不需要 E2E 浏览器，且 web/package.json 存在 postinstall（Playwright）
# 使用 --ignore-scripts 跳过 postinstall，避免拉取 Chromium 导致构建巨大且缓慢
ARG NPM_REGISTRY=https://registry.npmjs.org
RUN npm config set registry "${NPM_REGISTRY}"

COPY web/package.json web/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci --ignore-scripts --no-audit --no-fund

COPY web/ ./
RUN npm run build


FROM ${PYTHON_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # Default to production safety in containers; override via .env/env_file when needed.
    ENVIRONMENT=production \
    PYTHONPATH=/app/src \
    VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# uv：用于基于 uv.lock 安装依赖
# 国内网络下构建更稳定：pip 使用阿里云 PyPI 镜像
ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple
ARG PIP_TRUSTED_HOST=mirrors.aliyun.com
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST} \
    # uv 会读取该变量（若版本支持）以加速依赖下载；不支持时会被忽略
    UV_INDEX_URL=${PIP_INDEX_URL} \
    # 缓存目录：配合 BuildKit cache mount，可显著降低重复构建的下载耗时
    UV_CACHE_DIR=/root/.cache/uv \
    # 国内网络下容错与并发（按需调大/调小）
    UV_HTTP_TIMEOUT=60 \
    UV_CONCURRENT_DOWNLOADS=16

RUN pip install --no-cache-dir -i "${PIP_INDEX_URL}" --trusted-host "${PIP_TRUSTED_HOST}" uv==0.9.24 \
    && rm -rf /root/.cache/pip

# pydantic-settings 读取 .env 时，若文件不存在可能导致启动/迁移报错；这里放一个空文件兜底
RUN touch .env
# 约定：容器内的持久化目录统一放在 /app/.data 下（便于 docker compose bind mount）
RUN mkdir -p .data

# 先拷贝依赖描述文件，利用 Docker layer cache 加速构建
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# 应用代码 + 迁移脚本
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./
COPY README.md ./

# 将本项目本身安装到虚拟环境（避免运行时 `uv run` 再触发 editable 构建）
# - `--no-deps`：依赖已在上一层通过 uv sync 安装
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --no-deps -e .

# 将前端静态导出产物打进镜像（默认同源托管）
COPY --from=web_builder /web/out ./web/out

EXPOSE 31031

# 启动前执行迁移，避免“镜像已更新但表结构未升级”
CMD ["sh", "-c", "uv run alembic -c alembic.ini upgrade head && uv run uvicorn flow_backend.main:app --host 0.0.0.0 --port 31031"]
