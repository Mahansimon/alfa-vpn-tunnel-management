"""Dependencyهای مشترک API: احراز هویت، مجوز، CSRF و Rate Limit."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import hash_token
from app.core.errors import Forbidden, Unauthorized
from app.core.rbac import permissions_for
from app.core.ratelimit import check as rate_check
from app.core.security import csrf_ok, decode_jwt
from app.db.models.user import ApiToken, User, UserSession
from app.db.session import get_db

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class Principal:
    """کاربر یا توکن API که درخواست را انجام می‌دهد."""

    def __init__(self, user: User, *, via_token: ApiToken | None = None, session: UserSession | None = None):
        self.user = user
        self.token = via_token
        self.session = session
        base = permissions_for(user.role)
        if via_token and via_token.permissions_json:
            # توکن API نمی‌تواند دسترسی بیشتر از کاربرش داشته باشد
            base = base & set(via_token.permissions_json)
        self.permissions: set[str] = base

    @property
    def id(self) -> str:
        return self.user.id

    @property
    def username(self) -> str:
        return self.user.username

    def can(self, permission: str) -> bool:
        return permission in self.permissions


async def _from_cookie(request: Request, db: AsyncSession) -> Principal | None:
    raw = request.cookies.get(settings.COOKIE_NAME)
    if not raw:
        return None
    payload = decode_jwt(raw)
    if not payload:
        return None
    session = (
        await db.execute(
            select(UserSession).where(
                UserSession.id == payload.get("sid"), UserSession.revoked.is_(False)
            )
        )
    ).scalar_one_or_none()
    if session is None or session.expires_at < datetime.now(timezone.utc):
        return None
    if session.token_hash != hash_token(raw):
        return None
    user = await db.get(User, session.user_id)
    if user is None or not user.is_active:
        return None
    if request.method not in SAFE_METHODS:
        header = request.headers.get("x-csrf-token")
        if not csrf_ok(header, request.cookies.get(settings.CSRF_COOKIE_NAME)):
            raise Forbidden("توکن CSRF نامعتبر است. صفحه را بازخوانی کنید.")
    return Principal(user, session=session)


async def _from_bearer(request: Request, db: AsyncSession) -> Principal | None:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return None
    raw = header.split(" ", 1)[1].strip()
    token = (
        await db.execute(
            select(ApiToken).where(ApiToken.token_hash == hash_token(raw), ApiToken.revoked.is_(False))
        )
    ).scalar_one_or_none()
    if token is None:
        return None
    if token.expires_at and token.expires_at < datetime.now(timezone.utc):
        return None
    user = await db.get(User, token.user_id)
    if user is None or not user.is_active:
        return None
    token.last_used_at = datetime.now(timezone.utc)
    return Principal(user, via_token=token)


async def current_principal(request: Request, db: AsyncSession = Depends(get_db)) -> Principal:
    await rate_check(f"api:{client_ip(request)}", settings.API_RATE_LIMIT)
    principal = await _from_cookie(request, db) or await _from_bearer(request, db)
    if principal is None:
        raise Unauthorized()
    if principal.user.must_change_password and request.url.path not in (
        "/api/v1/auth/change-password",
        "/api/v1/auth/me",
        "/api/v1/auth/logout",
    ):
        raise Forbidden("قبل از ادامه باید پسورد خود را تغییر دهید.")
    request.state.principal = principal
    return principal


def require(*permissions: str) -> Callable:
    """Dependency ساخت مجوز: require('servers.write')"""

    async def _dep(principal: Principal = Depends(current_principal)) -> Principal:
        missing = [p for p in permissions if not principal.can(p)]
        if missing:
            raise Forbidden(f"برای این کار به دسترسی «{'، '.join(missing)}» نیاز دارید.")
        return principal

    return _dep


async def optional_principal(request: Request, db: AsyncSession = Depends(get_db)) -> Principal | None:
    try:
        return await _from_cookie(request, db) or await _from_bearer(request, db)
    except Forbidden:
        return None
