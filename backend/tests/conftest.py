"""تنظیمات مشترک تست‌ها. تست‌ها روی SQLite حافظه‌ای اجرا می‌شوند."""
from __future__ import annotations

import os

os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-alfa-panel")
os.environ.setdefault("SECRETS_ENCRYPTION_KEY", "test-encryption-key-for-alfa-panel")
os.environ.setdefault("REDIS_ENABLED", "false")
os.environ.setdefault("SCHEDULER_ENABLED", "false")
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("MOCK_MODE", "false")

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.db.models import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services import bootstrap  # noqa: E402


@pytest_asyncio.fixture
async def engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def db(session_factory):
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def admin_password(session_factory):
    async with session_factory() as session:
        password = await bootstrap.run(session, create_admin=True)
    return password


@pytest_asyncio.fixture
async def client(session_factory, admin_password):
    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def logged_in(client, admin_password):
    response = await client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": admin_password}
    )
    assert response.status_code == 200, response.text
    csrf = response.json()["csrf_token"]
    client.headers.update({"X-CSRF-Token": csrf})
    return client
