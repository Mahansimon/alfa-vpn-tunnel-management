"""هش پسورد، سیاست پسورد، تولید پسورد امن، JWT و CSRF."""
from __future__ import annotations

import re
import secrets
import string
from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)

WEAK_PASSWORDS = {
    "password",
    "12345678",
    "123456789",
    "qwertyuiop",
    "administrator",
    "adminadmin",
    "letmein123",
    "alfa12345678",
}


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return pwd_context.verify(password, password_hash)
    except Exception:
        return False


def password_problems(password: str) -> list[str]:
    """سیاست پسورد. خروجی خالی یعنی پسورد قابل قبول است."""
    problems: list[str] = []
    if len(password) < settings.PASSWORD_MIN_LENGTH:
        problems.append(f"پسورد باید حداقل {settings.PASSWORD_MIN_LENGTH} کاراکتر باشد.")
    if not re.search(r"[a-z]", password):
        problems.append("پسورد باید حرف کوچک انگلیسی داشته باشد.")
    if not re.search(r"[A-Z]", password):
        problems.append("پسورد باید حرف بزرگ انگلیسی داشته باشد.")
    if not re.search(r"\d", password):
        problems.append("پسورد باید عدد داشته باشد.")
    if not re.search(r"[^A-Za-z0-9]", password):
        problems.append("پسورد باید کاراکتر ویژه داشته باشد.")
    if password.lower() in WEAK_PASSWORDS:
        problems.append("این پسورد بسیار ضعیف و قابل حدس است.")
    return problems


def generate_password(length: int = 24) -> str:
    """پسورد تصادفی cryptographically secure با تضمین وجود همه دسته‌ها."""
    if length < 12:
        length = 12
    specials = "!@#$%^&*()-_=+[]{}?"
    pools = [string.ascii_lowercase, string.ascii_uppercase, string.digits, specials]
    chars = [secrets.choice(p) for p in pools]
    everything = "".join(pools)
    chars += [secrets.choice(everything) for _ in range(length - len(chars))]
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def create_jwt(subject: str, session_id: str, extra: dict | None = None, minutes: int | None = None) -> str:
    now = datetime.now(timezone.utc)
    ttl = minutes if minutes is not None else settings.SESSION_TTL_MINUTES
    payload = {
        "sub": subject,
        "sid": session_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ttl)).timestamp()),
        "iss": "alfa-panel",
        **(extra or {}),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_jwt(token: str) -> dict | None:
    try:
        return jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM], issuer="alfa-panel"
        )
    except jwt.PyJWTError:
        return None


def new_csrf_token() -> str:
    return secrets.token_urlsafe(24)


def csrf_ok(header_value: str | None, cookie_value: str | None) -> bool:
    return bool(header_value) and bool(cookie_value) and secrets.compare_digest(header_value, cookie_value)
