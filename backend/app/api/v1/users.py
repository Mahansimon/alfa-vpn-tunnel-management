"""مدیریت کاربران و توکن‌های API."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import hash_token, new_token
from app.core.deps import Principal, client_ip, current_principal, require
from app.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.core.rbac import Perm, permissions_for
from app.core.security import generate_password, hash_password, password_problems
from app.db.models.user import ApiToken, User, UserSession
from app.db.session import get_db
from app.schemas.common import OkResponse, Page, PageParams, paginate
from app.schemas.users import (
    ApiTokenCreate,
    ApiTokenCreated,
    ApiTokenOut,
    UserCreate,
    UserCreated,
    UserOut,
    UserUpdate,
)
from app.services.audit import record_audit, record_security_event

router = APIRouter(tags=["users"])

ROLE_RANK = {"viewer": 1, "operator": 2, "admin": 3, "owner": 4}


def _assert_can_manage(actor: Principal, target_role: str) -> None:
    """کاربر نمی‌تواند نقشی بالاتر یا هم‌سطح خودش (به جز Owner) بسازد یا تغییر دهد."""
    if ROLE_RANK.get(target_role, 0) > ROLE_RANK.get(actor.user.role, 0):
        raise Forbidden("نمی‌توانید نقشی بالاتر از نقش خودتان تعیین کنید.")


@router.get("/users", response_model=Page[UserOut])
async def list_users(
    params: PageParams = Depends(),
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require(Perm.USERS_MANAGE.value)),
):
    query = select(User)
    if params.search:
        term = f"%{params.search}%"
        query = query.where(or_(User.username.ilike(term), User.full_name.ilike(term)))
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    rows = (
        await db.execute(query.order_by(User.created_at.desc()).offset(params.offset).limit(params.per_page))
    ).scalars().all()
    return paginate([UserOut.model_validate(r) for r in rows], total, params)


@router.post("/users", response_model=UserCreated, status_code=201)
async def create_user(
    payload: UserCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: Principal = Depends(require(Perm.USERS_MANAGE.value)),
):
    _assert_can_manage(actor, payload.role)
    exists = (
        await db.execute(select(User).where(User.username == payload.username))
    ).scalar_one_or_none()
    if exists:
        raise Conflict("این نام کاربری قبلاً استفاده شده است.")
    generated = None
    password = payload.password
    if not password:
        password = generate_password(20)
        generated = password
    problems = password_problems(password)
    if problems:
        raise ValidationFailed("پسورد قابل قبول نیست.", details=problems)
    user = User(
        username=payload.username,
        full_name=payload.full_name,
        email=payload.email,
        role=payload.role,
        password_hash=hash_password(password),
        is_active=payload.is_active,
        must_change_password=True,
        password_changed_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.flush()
    await record_audit(
        db, action="user_created", user=actor.user, target=user.username, ip=client_ip(request)
    )
    return UserCreated(user=UserOut.model_validate(user), generated_password=generated)


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: str,
    payload: UserUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: Principal = Depends(require(Perm.USERS_MANAGE.value)),
):
    user = await db.get(User, user_id)
    if user is None:
        raise NotFound("کاربر یافت نشد.")
    if payload.role and payload.role != user.role:
        _assert_can_manage(actor, payload.role)
        if user.role == "owner" and actor.user.role != "owner":
            raise Forbidden("تغییر نقش مالک فقط توسط مالک ممکن است.")
        await record_security_event(
            db,
            "role_changed",
            username=user.username,
            user_id=user.id,
            ip=client_ip(request),
            detail=f"{user.role} → {payload.role}",
            severity="warning",
        )
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    await db.flush()
    await record_audit(
        db, action="user_updated", user=actor.user, target=user.username, ip=client_ip(request)
    )
    return UserOut.model_validate(user)


@router.post("/users/{user_id}/reset-password", response_model=UserCreated)
async def reset_password(
    user_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: Principal = Depends(require(Perm.USERS_MANAGE.value)),
):
    user = await db.get(User, user_id)
    if user is None:
        raise NotFound("کاربر یافت نشد.")
    password = generate_password(20)
    user.password_hash = hash_password(password)
    user.must_change_password = True
    user.failed_logins = 0
    user.locked_until = None
    sessions = (await db.execute(select(UserSession).where(UserSession.user_id == user.id))).scalars().all()
    for session in sessions:
        session.revoked = True
    await record_audit(
        db, action="password_reset", user=actor.user, target=user.username, ip=client_ip(request)
    )
    return UserCreated(user=UserOut.model_validate(user), generated_password=password)


@router.delete("/users/{user_id}", response_model=OkResponse)
async def delete_user(
    user_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: Principal = Depends(require(Perm.USERS_MANAGE.value)),
):
    user = await db.get(User, user_id)
    if user is None:
        raise NotFound("کاربر یافت نشد.")
    if user.id == actor.id:
        raise Conflict("نمی‌توانید حساب خودتان را حذف کنید.")
    if user.role == "owner":
        owners = (
            await db.execute(select(func.count()).select_from(User).where(User.role == "owner"))
        ).scalar() or 0
        if owners <= 1:
            raise Conflict("آخرین مالک سیستم قابل حذف نیست.")
    username = user.username
    await db.delete(user)
    await record_audit(db, action="user_deleted", user=actor.user, target=username, ip=client_ip(request))
    return OkResponse(message=f"کاربر «{username}» حذف شد.")


@router.get("/permissions")
async def list_permissions(_: Principal = Depends(current_principal)):
    """لیست کامل دسترسی‌ها به تفکیک نقش (برای صفحه کاربران و توکن‌ها)."""
    return {
        "roles": {
            role: sorted(permissions_for(role)) for role in ("owner", "admin", "operator", "viewer")
        },
        "all": sorted(p.value for p in Perm),
    }


# ---------------- API Tokens ----------------


@router.get("/api-tokens", response_model=Page[ApiTokenOut])
async def list_tokens(
    params: PageParams = Depends(),
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require(Perm.TOKENS_MANAGE.value)),
):
    query = select(ApiToken).where(ApiToken.user_id == principal.id)
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    rows = (
        await db.execute(
            query.order_by(ApiToken.created_at.desc()).offset(params.offset).limit(params.per_page)
        )
    ).scalars().all()
    return paginate([ApiTokenOut.model_validate(r) for r in rows], total, params)


@router.post("/api-tokens", response_model=ApiTokenCreated, status_code=201)
async def create_token(
    payload: ApiTokenCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require(Perm.TOKENS_MANAGE.value)),
):
    raw = new_token(32)
    allowed = set(principal.permissions)
    requested = set(payload.permissions) or allowed
    invalid = requested - allowed
    if invalid:
        raise Forbidden("این دسترسی‌ها در اختیار شما نیست: " + "، ".join(sorted(invalid)))
    row = ApiToken(
        user_id=principal.id,
        name=payload.name,
        token_hash=hash_token(raw),
        prefix=raw[:8],
        permissions_json=sorted(requested),
        expires_at=(
            datetime.now(timezone.utc) + timedelta(days=payload.expires_in_days)
            if payload.expires_in_days
            else None
        ),
    )
    db.add(row)
    await db.flush()
    await record_audit(
        db, action="api_token_created", user=principal.user, target=payload.name, ip=client_ip(request)
    )
    # توکن خام فقط همین یک بار برگردانده می‌شود
    return ApiTokenCreated(token=raw, item=ApiTokenOut.model_validate(row))


@router.delete("/api-tokens/{token_id}", response_model=OkResponse)
async def revoke_token(
    token_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require(Perm.TOKENS_MANAGE.value)),
):
    row = await db.get(ApiToken, token_id)
    if row is None or (row.user_id != principal.id and principal.user.role not in ("owner", "admin")):
        raise NotFound("توکن یافت نشد.")
    row.revoked = True
    await record_security_event(
        db, "token_revoked", username=principal.username, user_id=principal.id, ip=client_ip(request)
    )
    await record_audit(db, action="api_token_revoked", user=principal.user, target=row.name)
    return OkResponse(message="توکن باطل شد.")


@router.get("/sessions")
async def my_sessions(
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(current_principal),
    active_only: bool = Query(default=True),
):
    query = select(UserSession).where(UserSession.user_id == principal.id)
    if active_only:
        query = query.where(UserSession.revoked.is_(False))
    rows = (await db.execute(query.order_by(UserSession.created_at.desc()).limit(50))).scalars().all()
    return [
        {
            "id": r.id,
            "ip": r.ip,
            "user_agent": r.user_agent,
            "created_at": r.created_at,
            "expires_at": r.expires_at,
            "current": bool(principal.session and principal.session.id == r.id),
        }
        for r in rows
    ]
