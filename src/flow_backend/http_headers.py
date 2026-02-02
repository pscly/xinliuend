from __future__ import annotations

from urllib.parse import quote


def sanitize_filename(filename: str | None, *, fallback: str = "download") -> str:
    v = (filename or "").strip()
    # Defend against client-supplied paths.
    v = v.split("/")[-1].split("\\")[-1]
    # Defend against header injection.
    v = v.replace("\r", "").replace("\n", "").replace("\x00", "")
    if not v:
        v = fallback
    # Keep headers reasonably small.
    if len(v) > 150:
        v = v[:150]
    return v


def build_content_disposition_attachment(filename: str) -> str:
    """Build a safe Content-Disposition header value for attachments.

    Includes both `filename=` (ASCII fallback) and RFC 5987 `filename*=` (UTF-8).
    """

    name = sanitize_filename(filename)
    ascii_name = name.encode("ascii", errors="ignore").decode("ascii") or "download"
    ascii_name = ascii_name.replace('"', "'")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name, safe='')}"
