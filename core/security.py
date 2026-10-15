"""Ядро: пароли."""
from __future__ import annotations

import hashlib
import hmac
import os

ITERATIONS = 120_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return f"pbkdf2${ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt_hex, digest_hex = stored.split("$")
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                     bytes.fromhex(salt_hex), int(iters))
        return hmac.compare_digest(digest.hex(), digest_hex)
    except Exception:                                   # noqa: BLE001
        return False


def password_problems(password: str) -> list:
    """Требования к паролю администратора: возвращает список замечаний."""
    problems = []
    # РЕЖИМ РАЗРАБОТКИ (стенд): требования упрощены по решению заказчика.
    # На боевой версии вернуть: минимум 8 символов, буквы и цифры, запрет простых.
    if len(password or "") < 6:
        problems.append("минимум 6 символов")
    if (password or "").strip().lower() in {"123", "admin", "password", "qwerty", "111111"}:
        problems.append("слишком простой пароль")
    return problems
