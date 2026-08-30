"""ورود، خروج، پروفایل، تغییر پسورد و ۲FA."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pyotp
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import decrypt, encrypt, hash_token, new_token
from app.core.deps import Principal, client_ip, current_principal
from app.core.errors import Forbidden, Unauthorized, ValidationFailed
from app.core.ratelimit import check as rate_check
from app.core.ratelimit import reset as rate_reset
from app.core.security import (
    create_jwt,
    hash_password,
    new_csrf_token,
    password_problems,
    verify_password,
)
from app.db.models.user import User, UserSession
from app.db.session import get_db
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    MeResponse,
    TotpSetupResponse,
    TotpVerifyRequest,
)
from app.schemas.common import OkResponse
from app.services.audit import record_audit, record_security_event

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_cookies(response: Response, token: str, csrf: str) -> None:
    response.set_cookie(
        settings.COOKIE_NAME,
        token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=settings.SESSION_TTL_MINUTES * 60,
        path="/",
    )
    # CSRF cookie باید توسط جاوااسکریپت خوانده شود، پس httponly ندارد
    response.set_cookie(
        settings.CSRF_COOKIE_NAME,
        csrf,
        httponly=False,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=settings.SESSION_TTL_MINUTES * 60,
        path="/",
    )


def _me(principal_user: User, permissions: set[str]) -> MeResponse:
    return MeResponse(
        id=principal_user.id,
        username=principal_user.username,
        full_name=principal_user.full_name,
        email=principal_user.email,
        role=principal_user.role,
        permissions=sorted(permissions),
        must_change_password=principal_user.must_change_password,
        totp_enabled=principal_user.totp_enabled,
        theme=principal_user.theme,
        locale=principal_user.locale,
        timezone=principal_user.timezone,
    )


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    ip = client_ip(request)
    await rate_check(f"login:{ip}", settings.LOGIN_RATE_LIMIT)
    await rate_check(f"login-user:{payload.username}", settings.LOGIN_RATE_LIMIT)

    user = (
        await db.execute(select(User).where(User.username == payload.username))
    ).scalar_one_or_none()
    generic = Unauthorized("نام کاربری یا پسورد اشتباه است.")

    if user is None:
        await record_security_event(
            db, "failed_login", username=payload.username, ip=ip, detail="کاربر وجود ندارد", severity="warning"
        )
        raise generic
    if user.locked_until and user.locked_until > datetime.now(timezone.utc):
        raise Forbidden("حساب شما موقتاً قفل شده است. چند دقیقه بعد تلاش کنید.")
    if not user.is_active:
        raise Forbidden("حساب شما غیرفعال است.")
    if not verify_password(payload.password, user.password_hash):
        user.failed_logins += 1
        if user.failed_logins >= settings.MAX_FAILED_LOGINS:
            user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=settings.LOCKOUT_MINUTES)
            user.failed_logins = 0
            await record_security_event(
                db, "account_locked", username=user.username, user_id=user.id, ip=ip, severity="critical"
            )
        await record_security_event(
            db, "failed_login", username=user.username, user_id=user.id, ip=ip, severity="warning"
        )
        raise generic

    if user.totp_enabled:
        if not payload.totp_code:
            return LoginResponse(ok=False, totp_required=True)
        secret = decrypt(user.totp_secret_enc) or ""
        if not pyotp.TOTP(secret).verify(payload.totp_code, valid_window=1):
            await record_security_event(
                db, "failed_2fa", username=user.username, user_id=user.id, ip=ip, severity="warning"
            )
            raise Unauthorized("کد دو مرحله‌ای معتبر نیست.")

    raw = new_token(40)
    csrf = new_csrf_token()
    session = UserSession(
        user_id=user.id,
        token_hash="pending",
        csrf_token=csrf,
        ip=ip,
        user_agent=request.headers.get("user-agent", "")[:255],
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.SESSION_TTL_MINUTES),
    )
    db.add(session)
    await db.flush()
    jwt_token = create_jwt(user.id, session.id, {"role": user.role})
    session.token_hash = hash_token(jwt_token)
    user.failed_logins = 0
    user.last_login_at = datetime.now(timezone.utc)
    user.last_login_ip = ip
    await db.flush()

    await rate_reset(f"login-user:{payload.username}")
    await record_audit(db, action="login", user=user, ip=ip, user_agent=request.headers.get("user-agent"))
    await record_security_event(db, "login", username=user.username, user_id=user.id, ip=ip)
    _set_cookies(response, jwt_token, csrf)

    from app.core.rbac import permissions_for

    return LoginResponse(
        ok=True,
        must_change_password=user.must_change_password,
        csrf_token=csrf,
        user=_me(user, permissions_for(user.role)),
    )


@router.post("/logout", response_model=OkResponse)
async def logout(
    request: Request,
    response: Response,
    principal: Principal = Depends(current_principal),
    db: AsyncSession = Depends(get_db),
):
    if principal.session:
        principal.session.revoked = True
    await record_audit(db, action="logout", user=principal.user, ip=client_ip(request))
    response.delete_cookie(settings.COOKIE_NAME, path="/")
    response.delete_cookie(settings.CSRF_COOKIE_NAME, path="/")
    return OkResponse(message="از حساب خارج شدید.")


@router.get("/me", response_model=MeResponse)
async def me(principal: Principal = Depends(current_principal)):
    return _me(principal.user, principal.permissions)


@router.post("/change-password", response_model=OkResponse)
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    principal: Principal = Depends(current_principal),
    db: AsyncSession = Depends(get_db),
):
    user = principal.user
    if not verify_password(payload.current_password, user.password_hash):
        raise Unauthorized("پسورد فعلی درست نیست.")
    problems = password_problems(payload.new_password)
    if problems:
        raise ValidationFailed("پسورد جدید قابل قبول نیست.", details=problems)
    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    user.password_changed_at = datetime.now(timezone.utc)
    # همه نشست‌های دیگر باطل می‌شوند
    sessions = (
        await db.execute(select(UserSession).where(UserSession.user_id == user.id))
    ).scalars().all()
    for session in sessions:
        if not principal.session or session.id != principal.session.id:
            session.revoked = True
    await record_audit(db, action="password_changed", user=user, ip=client_ip(request))
    await record_security_event(
        db, "password_changed", username=user.username, user_id=user.id, ip=client_ip(request)
    )
    return OkResponse(message="پسورد با موفقیت تغییر کرد.")


@router.post("/2fa/setup", response_model=TotpSetupResponse)
async def setup_2fa(principal: Principal = Depends(current_principal), db: AsyncSession = Depends(get_db)):
    if not settings.ENABLE_2FA:
        raise Forbidden("ورود دو مرحله‌ای در این نصب غیرفعال است.")
    secret = pyotp.random_base32()
    principal.user.totp_secret_enc = encrypt(secret)
    principal.user.totp_enabled = False
    await db.flush()
    url = pyotp.TOTP(secret).provisioning_uri(
        name=principal.username, issuer_name=settings.PANEL_NAME
    )
    return TotpSetupResponse(secret=secret, otpauth_url=url)


@router.post("/2fa/enable", response_model=OkResponse)
async def enable_2fa(
    payload: TotpVerifyRequest,
    request: Request,
    principal: Principal = Depends(current_principal),
    db: AsyncSession = Depends(get_db),
):
    secret = decrypt(principal.user.totp_secret_enc) or ""
    if not secret:
        raise ValidationFailed("ابتدا مرحله راه‌اندازی ۲FA را انجام دهید.")
    if not pyotp.TOTP(secret).verify(payload.code, valid_window=1):
        raise ValidationFailed("کد وارد‌شده درست نیست.")
    principal.user.totp_enabled = True
    await record_audit(db, action="2fa_enabled", user=principal.user, ip=client_ip(request))
    return OkResponse(message="ورود دو مرحله‌ای فعال شد.")


@router.post("/2fa/disable", response_model=OkResponse)
async def disable_2fa(
    payload: TotpVerifyRequest,
    request: Request,
    principal: Principal = Depends(current_principal),
    db: AsyncSession = Depends(get_db),
):
    secret = decrypt(principal.user.totp_secret_enc) or ""
    if secret and not pyotp.TOTP(secret).verify(payload.code, valid_window=1):
        raise ValidationFailed("کد وارد‌شده درست نیست.")
    principal.user.totp_enabled = False
    principal.user.totp_secret_enc = None
    await record_audit(db, action="2fa_disabled", user=principal.user, ip=client_ip(request))
    return OkResponse(message="ورود دو مرحله‌ای غیرفعال شد.")


@router.patch("/preferences", response_model=MeResponse)
async def update_preferences(
    payload: dict,
    principal: Principal = Depends(current_principal),
    db: AsyncSession = Depends(get_db),
):
    """ذخیره تم، زبان و منطقه زمانی کاربر."""
    user = principal.user
    if payload.get("theme") in ("dark", "light"):
        user.theme = payload["theme"]
    if payload.get("locale") in ("fa", "en"):
        user.locale = payload["locale"]
    if isinstance(payload.get("timezone"), str) and payload["timezone"]:
        user.timezone = payload["timezone"][:64]
    await db.flush()
    return _me(user, principal.permissions)
