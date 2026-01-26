from __future__ import annotations

import bcrypt

_MAX_BCRYPT_PASSWORD_BYTES = 72


def hash_password(password: str) -> str:
    pw_bytes = password.encode("utf-8")
    if len(pw_bytes) > _MAX_BCRYPT_PASSWORD_BYTES:
        raise ValueError("密码过长（bcrypt 只支持最多 72 字节）")
    hashed = bcrypt.hashpw(pw_bytes, bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        pw_bytes = password.encode("utf-8")
        if len(pw_bytes) > _MAX_BCRYPT_PASSWORD_BYTES:
            return False
        return bcrypt.checkpw(pw_bytes, password_hash.encode("utf-8"))
    except Exception:
        return False
