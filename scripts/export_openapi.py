from __future__ import annotations

import argparse
import json
from pathlib import Path


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Keep ASCII-only output for repo diffs; non-ASCII will be \u-escaped.
    payload = json.dumps(data, ensure_ascii=True, indent=2, sort_keys=True)
    path.write_text(payload + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export FastAPI OpenAPI spec to apidocs/ as a JSON snapshot."
    )
    parser.add_argument(
        "--out-dir",
        default="apidocs",
        help="Output directory (default: apidocs)",
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir)

    # Import apps lazily so argparse --help stays fast.
    from flow_backend.main import app as main_app

    openapi_v1 = main_app.openapi()
    _write_json(out_dir / "openapi-v1.json", openapi_v1)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
