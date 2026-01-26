from __future__ import annotations

import json

from sqlmodel import Session, select

from flow_backend.config import settings
from flow_backend.db import engine
from flow_backend.memos_client import MemosClient
from flow_backend.models import User


def main() -> None:
    with Session(engine) as session:
        user = session.exec(select(User).order_by(User.id.desc())).first()
        if not user:
            print("no users in db")
            return
        if not user.memos_id or not user.memos_token:
            print("missing memos_id/token on user")
            return
        client = MemosClient(
            base_url=settings.memos_base_url,
            admin_token=settings.memos_admin_token,
            timeout_seconds=settings.memos_request_timeout_seconds,
        )
        new_token = __import__("asyncio").run(
            client.create_access_token_with_bearer(
                user_id=int(user.memos_id),
                bearer_token=user.memos_token,
                token_name=f"flow-reset-test-{user.username}",
            )
        )
        print(json.dumps({"ok": True, "new_token_len": len(new_token)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

