"""اسکیماهای احراز هویت."""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    totp_code: str | None = Field(default=None, max_length=8)


class LoginResponse(BaseModel):
    ok: bool = True
    must_change_password: bool = False
    totp_required: bool = False
    csrf_token: str | None = None
    user: MeResponse | None = None


class MeResponse(ORMModel):
    id: str
    username: str
    full_name: str = ""
    email: str | None = None
    role: str
    permissions: list[str] = []
    must_change_password: bool = False
    totp_enabled: bool = False
    theme: str = "dark"
    locale: str = "fa"
    timezone: str = "Asia/Tehran"


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=12, max_length=256)


class TotpSetupResponse(BaseModel):
    secret: str
    otpauth_url: str


class TotpVerifyRequest(BaseModel):
    code: str = Field(min_length=6, max_length=8)
