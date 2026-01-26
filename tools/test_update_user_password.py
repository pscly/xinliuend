from __future__ import annotations

import json

import httpx
from sqlmodel import Session, select

from flow_backend.config import settings
from flow_backend.db import engine
from flow_backend.models import User


def main() -> None:
    with Session(engine) as session:
        user = session.exec(select(User).order_by(User.id.desc())).first()
        if not user or not user.memos_id:
            print("no user/memos_id")
            return

        base = settings.memos_base_url.rstrip("/")
        url = f"{base}/api/v1/users/{int(user.memos_id)}"
        headers = {"Authorization": f"Bearer {settings.memos_admin_token.strip()}"}

        # 尝试用 update_mask 更新密码（这里用同样的 123456，避免产生实际变更）
        params = {"update_mask": "password"}
        payload = {"name": f"users/{int(user.memos_id)}", "password": "123456"}
        r = httpx.patch(url, headers=headers, params=params, json=payload, timeout=20.0)
        out = {"status_code": r.status_code}
        try:
            out["json"] = r.json()
        except Exception:
            out["text"] = r.text[:500]
        print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

