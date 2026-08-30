"""نقطه ورود بک‌اند Alfa VpnTunnel Managment."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api.v1.router import api_router
from app.api.v1.ws import router as ws_router
from app.core.config import API_PREFIX, APP_VERSION, settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.db.session import SessionLocal, engine
from app.services import bootstrap, scheduler

configure_logging()
log = get_logger("main")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "X-XSS-Protection": "1; mode=block",
}

CSP = (
    "default-src 'self'; "
    "img-src 'self' data: blob:; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' data: https://fonts.gstatic.com; "
    "script-src 'self'; "
    "connect-src 'self' ws: wss:; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("panel_starting", version=APP_VERSION, environment=settings.ENVIRONMENT)
    async with SessionLocal() as db:
        try:
            await bootstrap.run(db, create_admin=False)
        except Exception as exc:
            log.warning("bootstrap_skipped", error=str(exc))
    scheduler.start()
    yield
    await scheduler.stop()
    await engine.dispose()
    log.info("panel_stopped")


app = FastAPI(
    title="Alfa VpnTunnel Managment API",
    description="API مدیریت سرورها و تونل‌ها",
    version=APP_VERSION,
    docs_url=f"{API_PREFIX}/docs" if settings.ENABLE_DOCS else None,
    redoc_url=f"{API_PREFIX}/redoc" if settings.ENABLE_DOCS else None,
    openapi_url=f"{API_PREFIX}/openapi.json" if settings.ENABLE_DOCS else None,
    lifespan=lifespan,
)

app.add_middleware(GZipMiddleware, minimum_size=1024)
if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"],
    )

register_exception_handlers(app)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    for key, value in SECURITY_HEADERS.items():
        response.headers.setdefault(key, value)
    response.headers.setdefault("Content-Security-Policy", CSP)
    if settings.COOKIE_SECURE:
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    return response


app.include_router(api_router, prefix=API_PREFIX)
app.include_router(ws_router, prefix=API_PREFIX)


@app.get("/health", tags=["system"])
async def health():
    return {"status": "ok", "version": APP_VERSION, "time": datetime.now(timezone.utc)}


@app.get("/ready", tags=["system"])
async def ready():
    try:
        async with SessionLocal() as db:
            await db.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception as exc:
        return JSONResponse(
            status_code=503, content={"status": "not_ready", "detail": str(exc)[:200]}
        )


@app.get("/version", tags=["system"])
async def version():
    return {
        "panel": APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "mock_mode": settings.MOCK_MODE and not settings.is_production,
    }


# در Production فایل‌های ساخته‌شده فرانت‌اند از همین سرویس سرو می‌شوند
FRONTEND_DIST = os.getenv("FRONTEND_DIST", "/app/frontend-dist")
if os.path.isdir(FRONTEND_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        candidate = os.path.join(FRONTEND_DIST, full_path)
        if full_path and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))
