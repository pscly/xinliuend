from __future__ import annotations

import re

_LOCAL_DT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")


def validate_local_dt(value: str | None, field_name: str) -> str | None:
    if value is None or value == "":
        return None
    if not _LOCAL_DT_RE.match(value):
        raise ValueError(f"{field_name} must be YYYY-MM-DDTHH:mm:ss")
    return value
