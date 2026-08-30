"""اسکیماهای مدیریت کاربران و توکن API."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import ORMModel

ROLE_PATTERN = "^(owner|admin|operator|viewer)$"


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    full_name: str = ""
    email: EmailStr | None = None
    role: str = Field(default="viewer", pattern=ROLE_PATTERN)
    password: str | None = Field(default=None, min_length=12, max_length=256)
    is_active: bool = True


class UserUpdate(BaseModel):
    full_name: str | None = None
    email: EmailStr | None = None
    role: str | None = Field(default=None, pattern=ROLE_PATTERN)
    is_active: bool | None = None
    timezone: str | None = None
    locale: str | None = Field(default=None, pattern="^(fa|en)$")
    theme: str | None = Field(default=None, pattern="^(dark|light)$")


class UserOut(ORMModel):
    id: str
    username: str
    full_name: str
    email: str | None
    role: str
    is_active: bool
    totp_enabled: bool
    must_change_password: bool
    last_login_at: datetime | None
    created_at: datetime


class UserCreated(BaseModel):
    user: UserOut
    generated_password: str | None = None


class ApiTokenCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    permissions: list[str] = []
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)


class ApiTokenOut(ORMModel):
    id: str
    name: str
    prefix: str
    permissions_json: list = []
    expires_at: datetime | None
    last_used_at: datetime | None
    revoked: bool
    created_at: datetime


class ApiTokenCreated(BaseModel):
    token: str  # فقط یک بار نمایش داده می‌شود
    item: ApiTokenOut
