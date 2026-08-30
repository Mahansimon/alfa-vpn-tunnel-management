"""تست جریان کامل: ثبت سرور، ثبت Agent، Heartbeat، ساخت تونل، ترافیک و Audit."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from app.core.crypto import sign_payload


@pytest.fixture
async def ready_client(logged_in, admin_password):
    await logged_in.post(
        "/api/v1/auth/change-password",
        json={"current_password": admin_password, "new_password": "N3w-Str0ng-Pass!2026"},
    )
    return logged_in


@pytest.mark.asyncio
async def test_server_lifecycle_and_agent_registration(ready_client):
    client = ready_client
    created = await client.post(
        "/api/v1/servers",
        json={"name": "سرور تست", "ip_address": "10.10.10.10", "country": "Iran", "agent_port": 9443},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    server_id = body["server"]["id"]
    token = body["enrollment_token"]
    assert "install-agent.sh" in body["install_command"]
    assert token

    duplicate = await client.post(
        "/api/v1/servers", json={"name": "تکراری", "ip_address": "10.10.10.10"}
    )
    assert duplicate.status_code == 409

    register = await client.post(
        "/api/v1/agent/register",
        json={
            "enrollment_token": token,
            "system": {
                "hostname": "test-node",
                "os": "Ubuntu 24.04",
                "kernel": "6.8.0",
                "architecture": "amd64",
                "cpu_cores": 4,
                "cpu_model": "EPYC",
                "ram_total": 8 * 1024**3,
                "disk_total": 100 * 1024**3,
                "private_ip": "192.168.1.10",
                "uptime_seconds": 1000,
                "agent_version": "1.0.0",
                "capabilities": ["metrics", "tunnels"],
            },
        },
    )
    assert register.status_code == 200, register.text
    creds = register.json()
    assert creds["server_id"] == server_id
    agent_token = creds["agent_token"]
    signing_secret = creds["signing_secret"]

    payload = {
        "agent_version": "1.0.0",
        "metrics": {
            "ts": datetime.now(timezone.utc).isoformat(),
            "cpu_percent": 42.5,
            "load": [1.0, 0.8, 0.5],
            "ram_total": 8 * 1024**3,
            "ram_used": 4 * 1024**3,
            "disk_total": 100 * 1024**3,
            "disk_used": 40 * 1024**3,
            "net_rx_bytes": 1000,
            "net_tx_bytes": 2000,
            "net_rx_rate": 1024.0,
            "net_tx_rate": 2048.0,
            "uptime_seconds": 1020,
        },
        "tunnels": [],
        "logs": [{"source": "agent", "level": "info", "message": "سلام از Agent"}],
    }
    raw = json.dumps(payload)
    heartbeat = await client.post(
        "/api/v1/agent/heartbeat",
        content=raw,
        headers={
            "Authorization": f"Bearer {agent_token}",
            "X-Alfa-Server-Id": server_id,
            "X-Alfa-Signature": sign_payload(signing_secret, raw),
            "Content-Type": "application/json",
        },
    )
    assert heartbeat.status_code == 200, heartbeat.text
    assert heartbeat.json()["server_status"] == "online"

    # امضای نامعتبر باید رد شود
    bad = await client.post(
        "/api/v1/agent/heartbeat",
        content=raw,
        headers={
            "Authorization": f"Bearer {agent_token}",
            "X-Alfa-Server-Id": server_id,
            "X-Alfa-Signature": "deadbeef",
            "Content-Type": "application/json",
        },
    )
    assert bad.status_code == 401

    metrics = await client.get(f"/api/v1/servers/{server_id}/metrics?range=1h")
    assert metrics.status_code == 200
    assert metrics.json()["latest"]["cpu_percent"] == 42.5

    dashboard = await client.get("/api/v1/dashboard")
    assert dashboard.status_code == 200
    data = dashboard.json()
    assert data["servers_total"] == 1
    assert data["servers_online"] == 1
    assert data["mock_mode"] is False

    logs = await client.get("/api/v1/logs")
    assert logs.status_code == 200
    assert logs.json()["total"] >= 1

    audit = await client.get("/api/v1/audit-logs")
    assert audit.status_code == 200
    actions = [item["action"] for item in audit.json()["items"]]
    assert "server_created" in actions


@pytest.mark.asyncio
async def test_tunnel_requires_configured_type(ready_client):
    client = ready_client
    types = await client.get("/api/v1/tunnel-types")
    assert types.status_code == 200
    items = types.json()
    assert len(items) == 6
    assert all(item["configured"] is False for item in items)

    servers = []
    for index, ip in enumerate(("10.20.0.1", "10.20.0.2")):
        response = await client.post(
            "/api/v1/servers", json={"name": f"سرور {index}", "ip_address": ip}
        )
        servers.append(response.json()["server"]["id"])

    payload = {
        "name": "تونل تست",
        "type_key": "rathole2",
        "source_server_id": servers[0],
        "destination_server_id": servers[1],
        "config": {"role_source": "client", "role_destination": "server", "protocol": "tcp",
                   "listen_port": 2333, "remote_port": 8080},
    }
    blocked = await client.post("/api/v1/tunnels", json=payload)
    assert blocked.status_code == 422
    assert any("تنظیم نشده" in d for d in blocked.json()["error"]["details"])

    configured = await client.patch(
        "/api/v1/tunnel-types/rathole2",
        json={"repository_url": "https://github.com/example/rathole", "repository_ref": "v2.0.0"},
    )
    assert configured.status_code == 200
    assert configured.json()["configured"] is True

    validation = await client.post("/api/v1/tunnels/validate", json=payload)
    assert validation.status_code == 200
    result = validation.json()
    assert result["valid"] is False  # Agent روی سرورها نصب نشده است
    assert any("Agent" in e for e in result["errors"])

    created = await client.post("/api/v1/tunnels", json=payload)
    assert created.status_code == 201, created.text
    tunnel = created.json()
    assert tunnel["state"] == "draft"
    assert tunnel["config"]["listen_port"] == 2333

    clone = await client.post(f"/api/v1/tunnels/{tunnel['id']}/clone")
    assert clone.status_code == 201
    assert "کپی" in clone.json()["name"]

    topology = await client.get("/api/v1/topology")
    assert topology.status_code == 200
    assert len(topology.json()["nodes"]) == 2
    assert len(topology.json()["edges"]) == 2

    revisions = await client.get(f"/api/v1/tunnels/{tunnel['id']}/config-revisions")
    assert revisions.status_code == 200
    assert revisions.json()[0]["revision"] == 1


@pytest.mark.asyncio
async def test_rbac_viewer_cannot_write(ready_client):
    client = ready_client
    created = await client.post(
        "/api/v1/users",
        json={"username": "viewer1", "role": "viewer", "password": "V13wer-Strong!2026"},
    )
    assert created.status_code == 201

    # ورود با کاربر جدید در همان کلاینت (کوکی جایگزین می‌شود)
    login = await client.post(
        "/api/v1/auth/login", json={"username": "viewer1", "password": "V13wer-Strong!2026"}
    )
    assert login.status_code == 200
    client.headers.update({"X-CSRF-Token": login.json()["csrf_token"]})
    change = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "V13wer-Strong!2026", "new_password": "V13wer-Str0ng!2027"},
    )
    assert change.status_code == 200

    read = await client.get("/api/v1/servers")
    assert read.status_code == 200
    write = await client.post("/api/v1/servers", json={"name": "x", "ip_address": "10.30.0.1"})
    assert write.status_code == 403
    users = await client.get("/api/v1/users")
    assert users.status_code == 403


@pytest.mark.asyncio
async def test_api_token_lifecycle(ready_client):
    client = ready_client
    created = await client.post(
        "/api/v1/api-tokens", json={"name": "توکن تست", "permissions": ["servers.read"]}
    )
    assert created.status_code == 201
    body = created.json()
    raw_token = body["token"]
    assert body["item"]["prefix"] == raw_token[:8]

    listed = await client.get("/api/v1/api-tokens")
    assert listed.json()["total"] == 1
    assert "token" not in json.dumps(listed.json()["items"][0])

    revoked = await client.delete(f"/api/v1/api-tokens/{body['item']['id']}")
    assert revoked.status_code == 200


@pytest.mark.asyncio
async def test_settings_and_secret_masking(ready_client):
    client = ready_client
    updated = await client.put(
        "/api/v1/settings",
        json={"values": {"panel_name": "پنل من", "telegram_bot_token": "12345:secret-token"}},
    )
    assert updated.status_code == 200
    listed = await client.get("/api/v1/settings")
    values = {row["key"]: row["value"] for row in listed.json()}
    assert values["panel_name"] == "پنل من"
    assert "secret-token" not in str(values["telegram_bot_token"])
