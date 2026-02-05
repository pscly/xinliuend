from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
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
    parser.add_argument(
        "--include-dev",
        action="store_true",
        help="Also export a dev OpenAPI snapshot (includes debug endpoints).",
    )
    # Internal use: export variant in a clean process to avoid import caching.
    parser.add_argument(
        "--variant",
        choices=["prod", "dev"],
        default="prod",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir)

    # Keep the default snapshot "production-safe": never include debug in the public snapshot,
    # even if the caller has FLOW_OPENAPI_INCLUDE_DEBUG set in their shell.
    if args.variant == "prod":
        os.environ.pop("FLOW_OPENAPI_INCLUDE_DEBUG", None)

    if args.variant == "dev":
        # Ensure debug routes are both mounted (ENVIRONMENT != production) and included in schema.
        os.environ["ENVIRONMENT"] = "development"
        os.environ["FLOW_OPENAPI_INCLUDE_DEBUG"] = "1"

    # Import apps lazily so argparse --help stays fast.
    from flow_backend.main import app as main_app

    openapi_v1 = main_app.openapi()
    if args.variant == "prod":
        _write_json(out_dir / "openapi-v1.json", openapi_v1)
    else:
        _write_json(out_dir / "openapi-v1.dev.json", openapi_v1)

    if args.variant == "prod" and args.include_dev:
        # Export dev snapshot in a separate process so that the OpenAPI schema is generated from
        # a fresh import with different env vars (debug schema inclusion toggle).
        cmd = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--out-dir",
            str(out_dir),
            "--variant",
            "dev",
        ]
        env = os.environ.copy()
        env["ENVIRONMENT"] = "development"
        env["FLOW_OPENAPI_INCLUDE_DEBUG"] = "1"
        subprocess.run(cmd, check=True, env=env)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
