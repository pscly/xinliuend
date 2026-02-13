# apidocs（接口文档与对接资料）

最后更新：2026-02-06

本目录用于集中存放 **Flow Backend 对外接口** 以及客户端/运维对接所需的“配套资料”，避免文档分散在仓库各处导致遗漏与版本不一致。

建议阅读顺序（从“怎么接入”到“细节”）：

1. 客户端对接总指南：[`to_app_plan.md`](to_app_plan.md)
2. API 总文档（字段/协议/错误结构）：[`api.zh-CN.md`](api.zh-CN.md)
2.1 Collections/锦囊（结构层，APK 对接版）：[`collections.zh-CN.md`](collections.zh-CN.md)
3. OpenAPI 快照（机器可读）：
   - 对外/生产快照（不含 debug）：[`openapi-v1.json`](openapi-v1.json)
   - 开发联调用快照（包含 debug）：[`openapi-v1.dev.json`](openapi-v1.dev.json)

工程/运维相关（与接口联调强相关）：

- Web 联调与部署形态（同源 Cookie / CSRF）：[`web-dev-and-deploy.md`](web-dev-and-deploy.md)
- 部署指南（Docker Compose + 宝塔 Nginx）：[`deploy.zh-CN.md`](deploy.zh-CN.md)
- 架构说明与路线图（维护者视角）：[`plan.md`](plan.md)

备注：

- 对外仅保留 `/api/v1/*`，`/api/v2/*` 已移除（访问会返回 JSON 404：`ErrorResponse`）。
- 若你需要把 OpenAPI 导出/刷新：在仓库根目录执行：
  - 仅导出对外快照：`UV_CACHE_DIR=/tmp/uv-cache uv run python scripts/export_openapi.py --out-dir apidocs`
  - 同时导出开发联调快照（含 debug）：`UV_CACHE_DIR=/tmp/uv-cache uv run python scripts/export_openapi.py --out-dir apidocs --include-dev`

维护者自检（避免 Markdown / OpenAPI 漂移）：

- 刷新 OpenAPI 后，建议做一次“条目覆盖度”对账（以 `api.zh-CN.md` 的 `#### METHOD /path` 为条目；以 OpenAPI 的 `paths` 为基准）：

```bash
python3 - <<'PY'
import json
import re
from pathlib import Path

md = Path("apidocs/api.zh-CN.md").read_text("utf-8")
pattern = re.compile(r"^####\\s+(GET|POST|PUT|PATCH|DELETE)\\s+([^\\s]+)\\s*$", re.M)
md_ops = {(m.group(1), m.group(2)) for m in pattern.finditer(md)}
print("Markdown ops:", len(md_ops))

for fname in ["apidocs/openapi-v1.json", "apidocs/openapi-v1.dev.json"]:
    obj = json.loads(Path(fname).read_text("utf-8"))
    ops = set()
    for path, methods in obj.get("paths", {}).items():
        for method in methods.keys():
            if method.lower() in {"get", "post", "put", "patch", "delete"}:
                ops.add((method.upper(), path))
    missing = sorted(md_ops - ops)
    extra = sorted(ops - md_ops)
    print(f"\\n{fname}")
    print("  openapi ops:", len(ops))
    print("  missing in openapi:", len(missing))
    print("  extra in openapi:", len(extra))
    if missing[:5]:
        print("  missing sample:", missing[:5])
PY
```
