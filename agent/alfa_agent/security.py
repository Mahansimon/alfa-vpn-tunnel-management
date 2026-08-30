"""امنیت Agent: احراز هویت توکن، بررسی امضا، ضد Replay و Rate Limit."""
from __future__ import annotations

import hashlib
import hmac
import time
from collections import deque

MAX_SKEW_SECONDS = 300
_seen_requests: deque[tuple[float, str]] = deque(maxlen=5000)
_hits: deque[float] = deque(maxlen=10000)


def verify_bearer(header: str, expected_token: str) -> bool:
    if not header.lower().startswith("bearer ") or not expected_token:
        return False
    provided = header.split(" ", 1)[1].strip()
    return hmac.compare_digest(provided, expected_token)


def sign(secret: str, message: str) -> str:
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


def verify_signature(secret: str, message: str, signature: str) -> bool:
    if not secret:
        return True  # اگر کلید امضا تنظیم نشده باشد فقط توکن بررسی می‌شود
    return hmac.compare_digest(sign(secret, message), signature or "")


def check_replay(request_id: str, ts: int) -> tuple[bool, str]:
    """جلوگیری از تکرار درخواست (Replay) و درخواست‌های با زمان نامعتبر."""
    now = time.time()
    if ts and abs(now - ts) > MAX_SKEW_SECONDS:
        return False, "زمان درخواست خارج از محدوده مجاز است."
    while _seen_requests and now - _seen_requests[0][0] > MAX_SKEW_SECONDS * 2:
        _seen_requests.popleft()
    if request_id and any(request_id == rid for _, rid in _seen_requests):
        return False, "این درخواست قبلاً پردازش شده است."
    if request_id:
        _seen_requests.append((now, request_id))
    return True, ""


def rate_limit(limit: int = 120, window: int = 60) -> bool:
    now = time.time()
    while _hits and now - _hits[0] > window:
        _hits.popleft()
    if len(_hits) >= limit:
        return False
    _hits.append(now)
    return True
