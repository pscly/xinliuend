#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

release_tag=""
release_channel="snapshot"
output_dir="$ROOT_DIR/dist"
workflow_url="${WORKFLOW_URL:-}"
repository_url="${REPOSITORY_URL:-}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --release-tag)
      release_tag="$2"
      shift 2
      ;;
    --channel)
      release_channel="$2"
      shift 2
      ;;
    --output-dir)
      output_dir="$2"
      shift 2
      ;;
    --workflow-url)
      workflow_url="$2"
      shift 2
      ;;
    --repository-url)
      repository_url="$2"
      shift 2
      ;;
    *)
      echo "未知参数: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "$release_tag" ]]; then
  echo "缺少必填参数 --release-tag" >&2
  exit 1
fi

version="$({ python - <<'PY'
from pathlib import Path
import tomllib
print(tomllib.loads(Path('pyproject.toml').read_text(encoding='utf-8'))['project']['version'])
PY
} | tr -d '\n')"
commit_sha="$(git rev-parse HEAD)"
short_sha="$(git rev-parse --short=8 HEAD)"
build_time="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
safe_tag="$(printf '%s' "$release_tag" | tr '/:@ ' '----')"
asset_base="xinliuend-${version}-${safe_tag}"
bundle_root="xinliuend-${version}"

mkdir -p "$output_dir"
rm -f "$output_dir"/*

bundle_path="$output_dir/${asset_base}.tar.gz"
checksum_path="$output_dir/${asset_base}.sha256"
metadata_path="$output_dir/${asset_base}.json"
quickstart_path="$output_dir/${asset_base}.quickstart.md"
release_notes_path="$output_dir/release-notes.md"
manifest_env_path="$output_dir/release-manifest.env"

# 只打包部署/运行所需的跟踪文件，避免把本地缓存、数据库、venv 等非发布内容带进产物。
git archive \
  --format=tar \
  --prefix="${bundle_root}/" \
  HEAD -- \
  .env.example \
  AGENTS.md \
  CHANGELOG.md \
  Dockerfile \
  README.md \
  alembic \
  alembic.ini \
  apidocs \
  docker-compose.yml \
  docs \
  pyproject.toml \
  scripts \
  src \
  uv.lock \
  web \
  | gzip -n > "$bundle_path"

(
  cd "$output_dir"
  sha256sum "$(basename "$bundle_path")" > "$(basename "$checksum_path")"
)

python - <<'PY' "$metadata_path" "$version" "$release_tag" "$release_channel" "$commit_sha" "$short_sha" "$build_time" "$workflow_url" "$repository_url" "$(basename "$bundle_path")" "$(basename "$checksum_path")" "$(basename "$quickstart_path")"
from __future__ import annotations

import json
import sys
from pathlib import Path

(
    metadata_path,
    version,
    release_tag,
    release_channel,
    commit_sha,
    short_sha,
    build_time,
    workflow_url,
    repository_url,
    bundle_name,
    checksum_name,
    quickstart_name,
) = sys.argv[1:]

payload = {
    "project": "xinliuend",
    "package_name": "flow-backend",
    "version": version,
    "release_tag": release_tag,
    "release_channel": release_channel,
    "commit_sha": commit_sha,
    "commit_short_sha": short_sha,
    "built_at_utc": build_time,
    "repository_url": repository_url,
    "workflow_url": workflow_url,
    "assets": {
        "bundle": bundle_name,
        "checksum": checksum_name,
        "quickstart": quickstart_name,
    },
}

Path(metadata_path).write_text(
    json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
PY

python - <<'PY' "$quickstart_path" "$release_notes_path" "$version" "$release_tag" "$release_channel" "$commit_sha" "$build_time" "$(basename "$bundle_path")" "$(basename "$checksum_path")" "$(basename "$metadata_path")" "${bundle_root}"
from __future__ import annotations

import sys
from pathlib import Path

(
    quickstart_path,
    release_notes_path,
    version,
    release_tag,
    release_channel,
    commit_sha,
    build_time,
    bundle_name,
    checksum_name,
    metadata_name,
    bundle_root,
) = sys.argv[1:]

quickstart = f"""# xinliuend 发布包使用说明

- 版本：`{version}`
- 发布标签：`{release_tag}`
- 发布通道：`{release_channel}`
- 提交：`{commit_sha}`
- 构建时间（UTC）：`{build_time}`

## 包内内容

该压缩包已包含后端源码、Web 前端源码、Dockerfile、docker-compose、迁移脚本、部署文档与示例环境变量文件，适合直接下载后部署。

## 快速启动

```bash
tar -xzf {bundle_name}
cd {bundle_root}
cp .env.example .env
# 按需编辑 .env

docker compose up -d --build
```

## 常用命令

```bash
docker compose logs -f api
docker compose ps
docker compose down
```

## 说明

- 默认会把数据持久化到同目录下的 `./data`。
- 若需要 PostgreSQL，可按 README / apidocs 中的说明启用 `postgres` profile。
- 如需校验下载文件完整性，请使用同目录下的 `*.sha256` 文件。
"""

release_notes = f"""## 自动发布说明

- 版本：`{version}`
- 发布标签：`{release_tag}`
- 发布通道：`{release_channel}`
- 提交：`{commit_sha}`
- 构建时间（UTC）：`{build_time}`

## 附件说明

- `{bundle_name}`：可直接下载的部署包（含后端源码、Web 源码、Docker Compose、迁移与文档）
- `{checksum_name}`：SHA-256 校验值
- `{metadata_name}`：版本 / 提交 / 工作流元数据
- `{Path(quickstart_path).name}`：下载后快速启动说明

## 下载后快速启动

```bash
tar -xzf {bundle_name}
cd {bundle_root}
cp .env.example .env
docker compose up -d --build
```
"""

Path(quickstart_path).write_text(quickstart, encoding="utf-8")
Path(release_notes_path).write_text(release_notes, encoding="utf-8")
PY

cat > "$manifest_env_path" <<EOF2
VERSION=${version}
ASSET_BASE=${asset_base}
BUNDLE_PATH=${bundle_path}
CHECKSUM_PATH=${checksum_path}
METADATA_PATH=${metadata_path}
QUICKSTART_PATH=${quickstart_path}
RELEASE_NOTES_PATH=${release_notes_path}
RELEASE_TAG=${release_tag}
RELEASE_CHANNEL=${release_channel}
COMMIT_SHA=${commit_sha}
SHORT_SHA=${short_sha}
BUILD_TIME=${build_time}
EOF2

echo "bundle_path=$bundle_path"
echo "checksum_path=$checksum_path"
echo "metadata_path=$metadata_path"
echo "quickstart_path=$quickstart_path"
echo "release_notes_path=$release_notes_path"
echo "manifest_env_path=$manifest_env_path"
