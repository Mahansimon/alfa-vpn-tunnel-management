"""تست معماری Adapter تونل‌ها."""
from __future__ import annotations

import pytest

from app.tunnel_adapters import ADAPTERS, adapter_class
from app.tunnel_adapters.base import TunnelAdapter


class DummyRow:
    binary_path = "/opt/alfa/tunnel-binaries/example"
    repository_url = "https://github.com/example/example"
    repository_ref = "v1.2.3"
    binary_checksum = ""
    version = "1.2.3"


class DummyTunnel:
    id = "abcdef1234567890"
    name = "تونل تست"
    service_name = "alfa-tunnel-abcdef12"


def test_registry_has_all_six_tunnels():
    assert set(ADAPTERS) == {
        "premium_backhaul",
        "broken_node",
        "packet_tunnel",
        "backpack",
        "ping_tunnel",
        "rathole2",
    }


@pytest.mark.parametrize("key", list(ADAPTERS))
def test_adapter_implements_interface(key):
    cls = adapter_class(key)
    assert issubclass(cls, TunnelAdapter)
    for method in (
        "install",
        "uninstall",
        "configure",
        "start",
        "stop",
        "restart",
        "status",
        "logs",
        "health_check",
        "metrics",
        "generate_config",
        "validate_config",
    ):
        assert hasattr(cls, method), f"{key} متد {method} را ندارد"
    meta = cls.describe()
    assert meta.key == key
    assert meta.source_kind in ("binary", "repository")
    assert meta.display_name_fa


def test_unconfigured_adapter_reports_error():
    cls = adapter_class("premium_backhaul")
    adapter = cls(agent_client=None, tunnel_type_row=None)
    errors, _ = adapter.validate_config({})
    assert any("تنظیم نشده" in e for e in errors)
    assert not adapter.is_configured()


def test_config_validation_and_rendering():
    cls = adapter_class("rathole2")
    adapter = cls(agent_client=None, tunnel_type_row=DummyRow())
    config = {
        "role_source": "client",
        "role_destination": "server",
        "protocol": "tcp",
        "listen_port": 2333,
        "remote_port": 8080,
        "config_template": "port = $listen_port\nname = $tunnel_name\ntoken = $auth_token",
        "extra_args": "--config /etc/alfa/$service_name.toml",
        "auth_token": "s3cr3t",
    }
    errors, warnings = adapter.validate_config(config)
    assert errors == []
    rendered = adapter.generate_config(DummyTunnel(), config, {"auth_token": "s3cr3t"})
    assert "port = 2333" in rendered
    assert "token = s3cr3t" in rendered
    args = adapter.render_args(DummyTunnel(), config)
    assert args == ["--config", "/etc/alfa/alfa-tunnel-abcdef12.toml"]
    assert warnings == []


def test_dangerous_port_warns():
    cls = adapter_class("rathole2")
    adapter = cls(agent_client=None, tunnel_type_row=DummyRow())
    _, warnings = adapter.validate_config(
        {
            "role_source": "client",
            "role_destination": "server",
            "protocol": "tcp",
            "listen_port": 22,
            "remote_port": 8080,
        }
    )
    assert any("SSH" in w for w in warnings)


def test_missing_required_field_fails():
    cls = adapter_class("backpack")
    adapter = cls(agent_client=None, tunnel_type_row=DummyRow())
    errors, _ = adapter.validate_config({"role_source": "client", "role_destination": "server"})
    assert errors
