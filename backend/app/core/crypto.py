"""رمزنگاری Secretها در حالت At-Rest + پشتیبانی از Key Rotation.

کلیدها از SECRETS_ENCRYPTION_KEY خوانده می‌شوند و می‌توانند چند کلید با
جداکننده «,» باشند: کلید اول برای رمزگذاری، بقیه فقط برای رمزگشایی
(یعنی چرخش کلید بدون از دست رفتن داده قدیمی).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.core.config import settings

_PREFIX = "enc:v1:"


def _normalize(raw: str) -> bytes:
    """هر رشته‌ای را به کلید معتبر Fernet تبدیل می‌کند."""
    raw = raw.strip()
    try:
        if len(base64.urlsafe_b64decode(raw.encode())) == 32:
            return raw.encode()
    except Exception:
        pass
    digest = hashlib.sha256(raw.encode()).digest()
    return base64.urlsafe_b64encode(digest)


def _keys() -> list[bytes]:
    source = settings.SECRETS_ENCRYPTION_KEY or settings.SECRET_KEY
    return [_normalize(k) for k in source.split(",") if k.strip()]


def _engine() -> MultiFernet:
    return MultiFernet([Fernet(k) for k in _keys()])


def encrypt(plaintext: str | None) -> str | None:
    if plaintext is None or plaintext == "":
        return plaintext
    return _PREFIX + _engine().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str | None) -> str | None:
    if not ciphertext:
        return ciphertext
    if not ciphertext.startswith(_PREFIX):
        # داده قدیمی/غیررمزگذاری‌شده: همان‌طور برگردان تا مهاجرت ممکن باشد
        return ciphertext
    try:
        return _engine().decrypt(ciphertext[len(_PREFIX) :].encode()).decode()
    except InvalidToken as exc:  # pragma: no cover - وابسته به کلید نامعتبر
        raise ValueError("رمزگشایی Secret ناموفق بود؛ کلید رمزنگاری اشتباه است.") from exc


def rotate(ciphertext: str | None) -> str | None:
    """رمزگذاری مجدد با کلید فعال فعلی."""
    if not ciphertext:
        return ciphertext
    return encrypt(decrypt(ciphertext))


def mask(value: str | None, keep: int = 4) -> str:
    if not value:
        return ""
    if len(value) <= keep:
        return "*" * len(value)
    return value[:keep] + "*" * (len(value) - keep)


def new_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    """توکن‌ها فقط به صورت hash ذخیره می‌شوند."""
    return hashlib.sha256((settings.SECRET_KEY + token).encode()).hexdigest()


def verify_token(token: str, token_hash: str) -> bool:
    return hmac.compare_digest(hash_token(token), token_hash)


def sign_payload(secret: str, message: str) -> str:
    """امضای درخواست‌ها بین پنل و Agent (HMAC-SHA256)."""
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


def verify_signature(secret: str, message: str, signature: str) -> bool:
    return hmac.compare_digest(sign_payload(secret, message), signature)


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
