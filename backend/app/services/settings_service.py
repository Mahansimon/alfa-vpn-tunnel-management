"""تنظیمات runtime پنل (جدول settings) با پشتیبانی از مقادیر حساس."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings as env
from app.core.crypto import decrypt, encrypt, mask
from app.db.models.ops import Setting

SECRET_KEYS = {"github_token", "smtp_password", "telegram_bot_token", "webhook_secret", "backup_password"}

DEFAULTS: dict[str, dict[str, Any]] = {
    # general
    "panel_name": {"value": env.PANEL_NAME, "category": "general", "description_fa": "نام نمایشی پنل"},
    "timezone": {"value": env.TIMEZONE, "category": "general", "description_fa": "منطقه زمانی پیش‌فرض"},
    "locale": {"value": "fa", "category": "general", "description_fa": "زبان پیش‌فرض"},
    "digits": {"value": "fa", "category": "general", "description_fa": "نمایش اعداد: fa یا en"},
    "calendar": {"value": "jalali", "category": "general", "description_fa": "تقویم: jalali یا gregorian"},
    # appearance / branding
    "theme": {"value": "dark", "category": "appearance", "description_fa": "تم پیش‌فرض"},
    "accent_color": {"value": "#7C5CFF", "category": "appearance", "description_fa": "رنگ تأکیدی"},
    "logo_url": {"value": "", "category": "appearance", "description_fa": "آدرس لوگو"},
    "favicon_url": {"value": "", "category": "appearance", "description_fa": "آدرس Favicon"},
    # security
    "session_ttl_minutes": {"value": env.SESSION_TTL_MINUTES, "category": "security",
                            "description_fa": "مدت اعتبار نشست (دقیقه)"},
    "force_2fa_for_admins": {"value": False, "category": "security",
                             "description_fa": "اجبار ۲FA برای مدیران"},
    "https_enabled": {"value": False, "category": "security",
                      "description_fa": "آیا پنل با HTTPS سرو می‌شود"},
    # monitoring
    "metrics_interval_seconds": {"value": env.METRICS_INTERVAL_SECONDS, "category": "monitoring",
                                 "description_fa": "فاصله جمع‌آوری متریک"},
    "heartbeat_interval_seconds": {"value": env.AGENT_HEARTBEAT_INTERVAL, "category": "monitoring",
                                   "description_fa": "فاصله Heartbeat"},
    "offline_after_missed": {"value": env.AGENT_OFFLINE_AFTER_MISSED, "category": "monitoring",
                             "description_fa": "تعداد Heartbeat ازدست‌رفته تا Offline شدن"},
    "metric_retention_days": {"value": env.METRIC_RETENTION_DAYS, "category": "monitoring",
                              "description_fa": "نگهداشت متریک خام (روز)"},
    "log_retention_days": {"value": env.LOG_RETENTION_DAYS, "category": "monitoring",
                           "description_fa": "نگهداشت لاگ (روز)"},
    "traffic_retention_days": {"value": env.TRAFFIC_RETENTION_DAYS, "category": "traffic",
                               "description_fa": "نگهداشت ترافیک (روز)"},
    # notifications
    "notify_channels": {"value": ["inapp"], "category": "notifications",
                        "description_fa": "کانال‌های فعال اعلان"},
    "smtp_host": {"value": "", "category": "notifications", "description_fa": "میزبان SMTP"},
    "smtp_port": {"value": 587, "category": "notifications", "description_fa": "پورت SMTP"},
    "smtp_user": {"value": "", "category": "notifications", "description_fa": "کاربر SMTP"},
    "smtp_password": {"value": "", "category": "notifications", "description_fa": "رمز SMTP (رمزگذاری‌شده)"},
    "smtp_from": {"value": "", "category": "notifications", "description_fa": "فرستنده ایمیل"},
    "telegram_bot_token": {"value": "", "category": "notifications",
                           "description_fa": "توکن ربات تلگرام (رمزگذاری‌شده)"},
    "telegram_chat_id": {"value": "", "category": "notifications", "description_fa": "شناسه چت تلگرام"},
    "webhook_url": {"value": "", "category": "notifications", "description_fa": "آدرس Webhook"},
    "webhook_secret": {"value": "", "category": "notifications",
                       "description_fa": "کلید امضای Webhook (رمزگذاری‌شده)"},
    # agent / tunnel defaults
    "agent_port": {"value": env.AGENT_PORT, "category": "agent", "description_fa": "پورت پیش‌فرض Agent"},
    "agent_auto_update": {"value": False, "category": "agent",
                          "description_fa": "به‌روزرسانی خودکار Agent"},
    "tunnel_default_protocol": {"value": "tcp", "category": "tunnel", "description_fa": "پروتکل پیش‌فرض"},
    "tunnel_binary_dir": {"value": env.TUNNEL_BINARY_DIR, "category": "tunnel",
                          "description_fa": "مسیر نگهداری Binaryهای تونل"},
    # backup / update
    "backup_enabled": {"value": True, "category": "backup", "description_fa": "پشتیبان‌گیری خودکار"},
    "backup_interval_hours": {"value": 24, "category": "backup", "description_fa": "فاصله پشتیبان‌گیری"},
    "backup_keep": {"value": 14, "category": "backup", "description_fa": "تعداد نسخه‌های نگه‌داشته‌شده"},
    "backup_encrypt": {"value": True, "category": "backup", "description_fa": "رمزگذاری فایل پشتیبان"},
    "github_repository": {"value": "", "category": "update",
                          "description_fa": "Repository پنل برای بررسی به‌روزرسانی"},
    "github_branch": {"value": "main", "category": "update", "description_fa": "شاخه گیت"},
    "github_release": {"value": "", "category": "update", "description_fa": "نسخه/Release هدف"},
    "github_token": {"value": env.GITHUB_TOKEN, "category": "update",
                     "description_fa": "توکن GitHub برای Repository خصوصی (رمزگذاری‌شده)"},
}


async def ensure_defaults(db: AsyncSession) -> None:
    existing = {row.key for row in (await db.execute(select(Setting))).scalars()}
    for key, spec in DEFAULTS.items():
        if key in existing:
            continue
        is_secret = key in SECRET_KEYS
        raw = spec["value"]
        db.add(
            Setting(
                key=key,
                value=encrypt(str(raw)) if is_secret and raw else (None if is_secret else raw),
                is_secret=is_secret,
                category=spec["category"],
                description_fa=spec["description_fa"],
            )
        )
    await db.flush()


async def get_all(db: AsyncSession, *, reveal: bool = False) -> list[dict]:
    rows = (await db.execute(select(Setting).order_by(Setting.category, Setting.key))).scalars().all()
    out = []
    for row in rows:
        value = row.value
        if row.is_secret:
            plain = decrypt(value) if isinstance(value, str) else None
            value = (plain if reveal else mask(plain or "")) or ""
        out.append(
            {
                "key": row.key,
                "value": value,
                "category": row.category,
                "is_secret": row.is_secret,
                "description_fa": row.description_fa,
            }
        )
    return out


async def get(db: AsyncSession, key: str, default: Any = None) -> Any:
    row = (await db.execute(select(Setting).where(Setting.key == key))).scalar_one_or_none()
    if row is None:
        return DEFAULTS.get(key, {}).get("value", default)
    if row.is_secret and isinstance(row.value, str):
        return decrypt(row.value)
    return row.value if row.value is not None else default


async def set_many(db: AsyncSession, values: dict[str, Any]) -> list[str]:
    changed: list[str] = []
    for key, value in values.items():
        if key not in DEFAULTS:
            continue
        row = (await db.execute(select(Setting).where(Setting.key == key))).scalar_one_or_none()
        is_secret = key in SECRET_KEYS
        stored = encrypt(str(value)) if is_secret and value not in (None, "") else value
        if row is None:
            spec = DEFAULTS[key]
            db.add(
                Setting(
                    key=key,
                    value=stored,
                    is_secret=is_secret,
                    category=spec["category"],
                    description_fa=spec["description_fa"],
                )
            )
        else:
            if is_secret and value in (None, "", "***"):
                continue  # مقدار ماسک‌شده را بازنویسی نکن
            row.value = stored
        changed.append(key)
    await db.flush()
    return changed
