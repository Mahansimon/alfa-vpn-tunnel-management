"""آماده‌سازی اولیه: نقش‌ها، دسترسی‌ها، تنظیمات، رجیستری تونل‌ها و کاربر Admin."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.rbac import ROLE_LABELS_FA, ROLE_PERMISSIONS, Role
from app.core.security import generate_password, hash_password
from app.db.models.user import Permission, Role as RoleRow, RolePermission, User
from app.services import alerting, mock, settings_service
from app.tunnel_adapters.registry import sync_registry

log = get_logger("bootstrap")

PERMISSION_LABELS_FA = {
    "servers.read": "مشاهده سرورها",
    "servers.write": "ایجاد و ویرایش سرور",
    "servers.delete": "حذف سرور",
    "tunnels.read": "مشاهده تونل‌ها",
    "tunnels.create": "ایجاد تونل",
    "tunnels.modify": "ویرایش و کنترل تونل",
    "tunnels.delete": "حذف تونل",
    "metrics.read": "مشاهده متریک‌ها",
    "traffic.read": "مشاهده ترافیک",
    "logs.read": "مشاهده لاگ‌ها",
    "alerts.manage": "مدیریت هشدارها",
    "settings.read": "مشاهده تنظیمات",
    "settings.write": "تغییر تنظیمات",
    "users.manage": "مدیریت کاربران",
    "backup.manage": "مدیریت پشتیبان‌گیری",
    "update.manage": "مدیریت به‌روزرسانی",
    "audit.read": "مشاهده Audit Log",
    "tokens.manage": "مدیریت توکن‌های API",
}


async def sync_roles(db: AsyncSession) -> None:
    existing_roles = {r.name for r in (await db.execute(select(RoleRow))).scalars()}
    for role, perms in ROLE_PERMISSIONS.items():
        if role.value not in existing_roles:
            db.add(RoleRow(name=role.value, label_fa=ROLE_LABELS_FA[role], is_system=True))
        for perm in perms:
            exists = (
                await db.execute(
                    select(RolePermission).where(
                        RolePermission.role_name == role.value,
                        RolePermission.permission_code == perm.value,
                    )
                )
            ).scalar_one_or_none()
            if not exists:
                db.add(RolePermission(role_name=role.value, permission_code=perm.value))
    existing_perms = {p.code for p in (await db.execute(select(Permission))).scalars()}
    for code, label in PERMISSION_LABELS_FA.items():
        if code not in existing_perms:
            db.add(Permission(code=code, description_fa=label))
    await db.flush()


async def ensure_admin(db: AsyncSession, username: str = "admin") -> tuple[User, str | None]:
    """اگر هیچ کاربری وجود ندارد، Admin با پسورد تصادفی امن ساخته می‌شود."""
    count = (await db.execute(select(func.count()).select_from(User))).scalar() or 0
    if count:
        user = (await db.execute(select(User).order_by(User.created_at.asc()).limit(1))).scalar_one()
        return user, None
    password = generate_password(24)
    user = User(
        username=username,
        full_name="مدیر سیستم",
        role=Role.OWNER.value,
        password_hash=hash_password(password),
        is_active=True,
        must_change_password=True,
        password_changed_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.flush()
    log.info("admin_created", username=username)
    return user, password


async def run(db: AsyncSession, *, create_admin: bool = True) -> str | None:
    await sync_roles(db)
    await settings_service.ensure_defaults(db)
    await sync_registry(db)
    await alerting.default_rules(db)
    password: str | None = None
    if create_admin:
        _, password = await ensure_admin(db)
    await mock.seed_demo(db)
    await db.commit()
    return password
