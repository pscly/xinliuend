FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/src

WORKDIR /app

# uv：用于基于 uv.lock 安装依赖
# 国内网络下构建更稳定：pip 使用阿里云 PyPI 镜像
ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple
ARG PIP_TRUSTED_HOST=mirrors.aliyun.com
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST} \
    # uv 会读取该变量（若版本支持）以加速依赖下载；不支持时会被忽略
    UV_INDEX_URL=${PIP_INDEX_URL}

RUN pip install --no-cache-dir -i "${PIP_INDEX_URL}" --trusted-host "${PIP_TRUSTED_HOST}" uv==0.9.24 \
    && rm -rf /root/.cache/pip

# pydantic-settings 读取 .env 时，若文件不存在可能导致启动/迁移报错；这里放一个空文件兜底
RUN touch .env

# 先拷贝依赖描述文件，利用 Docker layer cache 加速构建
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# 应用代码 + 迁移脚本
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./

EXPOSE 31031

# 启动前执行迁移，避免“镜像已更新但表结构未升级”
CMD ["sh", "-c", "uv run alembic -c alembic.ini upgrade head && uv run uvicorn flow_backend.main:app --host 0.0.0.0 --port 31031"]
