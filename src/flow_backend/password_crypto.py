from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from flow_backend.config import settings


def _get_fernet() -> Fernet:
    key = settings.user_password_encryption_key.strip()
    if not key:
        raise ValueError("USER_PASSWORD_ENCRYPTION_KEY 未配置")
    try:
        return Fernet(key.encode("utf-8"))
    except Exception as e:  # pragma: no cover
        raise ValueError("USER_PASSWORD_ENCRYPTION_KEY 非法（必须是 Fernet key）") from e


def encrypt_password(password: str) -> str:
    """加密明文密码，返回可存储到数据库的 token（字符串）。"""

    token = _get_fernet().encrypt(password.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_password(token: str) -> str:
    """解密数据库中存储的 token，返回明文密码。"""

    try:
        raw = _get_fernet().decrypt(token.encode("utf-8"))
    except InvalidToken as e:
        raise ValueError("密码密文无法解密（密钥不匹配或数据已损坏）") from e
    return raw.decode("utf-8")
