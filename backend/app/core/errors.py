"""خطاهای استاندارد و ساخت‌یافته. پیام‌ها فارسی و قابل نمایش به کاربر هستند."""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("errors")


class AppError(Exception):
    """خطای پایه برنامه."""

    status_code = status.HTTP_400_BAD_REQUEST
    code = "app_error"
    message = "خطای نامشخص رخ داد."

    def __init__(self, message: str | None = None, *, details: Any = None, code: str | None = None):
        self.message = message or self.message
        self.details = details
        if code:
            self.code = code
        super().__init__(self.message)

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class NotFound(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"
    message = "موردی یافت نشد."


class Conflict(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"
    message = "تضاد در داده‌ها."


class ValidationFailed(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "validation_failed"
    message = "اطلاعات ورودی معتبر نیست."


class Unauthorized(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthorized"
    message = "ابتدا وارد حساب خود شوید."


class Forbidden(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"
    message = "دسترسی لازم را ندارید."


class RateLimited(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "rate_limited"
    message = "تعداد درخواست‌ها بیش از حد مجاز است. کمی بعد تلاش کنید."


class AgentUnreachable(AppError):
    status_code = status.HTTP_502_BAD_GATEWAY
    code = "agent_unreachable"
    message = "ارتباط با Agent سرور برقرار نشد."


class DeploymentFailed(AppError):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    code = "deployment_failed"
    message = "اجرای عملیات استقرار با خطا متوقف شد."


def register_exception_handlers(app) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        return JSONResponse(status_code=exc.status_code, content=exc.to_dict())

    @app.exception_handler(HTTPException)
    async def _http_error(_: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": "http_error", "message": str(exc.detail), "details": None}},
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_failed",
                    "message": "اطلاعات ارسال‌شده معتبر نیست.",
                    "details": [
                        {"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]}
                        for e in exc.errors()
                    ],
                }
            },
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        # در Production هیچ stack trace حساسی به کلاینت داده نمی‌شود
        log.error("unhandled_error", path=str(request.url.path), error=str(exc), exc_info=True)
        details = None if settings.is_production else str(exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "خطای داخلی سرور. لطفاً لاگ‌ها را بررسی کنید.",
                    "details": details,
                }
            },
        )
