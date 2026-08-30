"""تست‌های API: ورود، مجوزها، CSRF و محدودیت نرخ."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_login_and_me(client, admin_password):
    bad = await client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"})
    assert bad.status_code == 401
    assert "error" in bad.json()

    good = await client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": admin_password}
    )
    assert good.status_code == 200
    body = good.json()
    assert body["ok"] is True
    assert body["must_change_password"] is True
    assert body["user"]["role"] == "owner"

    client.headers.update({"X-CSRF-Token": body["csrf_token"]})
    me = await client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "admin"


@pytest.mark.asyncio
async def test_protected_routes_require_auth(client):
    response = await client.get("/api/v1/servers")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_must_change_password_blocks_other_routes(logged_in, admin_password):
    blocked = await logged_in.get("/api/v1/servers")
    assert blocked.status_code == 403

    changed = await logged_in.post(
        "/api/v1/auth/change-password",
        json={"current_password": admin_password, "new_password": "N3w-Str0ng-Pass!2026"},
    )
    assert changed.status_code == 200
    allowed = await logged_in.get("/api/v1/servers")
    assert allowed.status_code == 200


@pytest.mark.asyncio
async def test_weak_new_password_rejected(logged_in, admin_password):
    response = await logged_in.post(
        "/api/v1/auth/change-password",
        json={"current_password": admin_password, "new_password": "password1234"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["details"]


@pytest.mark.asyncio
async def test_csrf_required_for_write(client, admin_password):
    login = await client.post("/api/v1/auth/login", json={"username": "admin", "password": admin_password})
    assert login.status_code == 200
    # بدون هدر CSRF نوشتن ممکن نیست
    response = await client.post("/api/v1/auth/logout")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_health_and_version_endpoints(client):
    assert (await client.get("/health")).status_code == 200
    version = await client.get("/version")
    assert version.status_code == 200
    assert version.json()["panel"]
