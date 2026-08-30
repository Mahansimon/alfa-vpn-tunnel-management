"""معماری Adapter تونل‌ها.

قاعده مهم پروژه: هیچ آرگومان CLI یا فرمت config برای هیچ تونلی حدس زده نمی‌شود.
هر Adapter فقط «چه چیزی لازم است» را توصیف می‌کند و مقادیر واقعی از
Configuration پنل (یا .env) می‌آیند. رندر config با string.Template انجام
می‌شود، پس وقتی syntax واقعی برنامه مشخص شد، تنها کافی است در پنل
«قالب config» و «آرگومان‌ها» وارد شود؛ کد Adapter تغییر نمی‌کند.
"""
from __future__ import annotations

import shlex
import os
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from string import Template
from typing import Any

from app.core.errors import ValidationFailed


@dataclass(slots=True)
class ConfigField:
    key: str
    label_fa: str
    type: str = "string"  # string | text | int | port | bool | select | secret | list
    required: bool = False
    default: Any = None
    help_fa: str = ""
    options: list[str] = field(default_factory=list)
    minimum: int | None = None
    maximum: int | None = None
    advanced: bool = False
    secret: bool = False

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class AdapterMetadata:
    key: str
    display_name: str
    display_name_fa: str
    source_kind: str  # binary | repository
    summary_fa: str
    requires: list[str] = field(default_factory=list)  # iptables, nftables, sysctl, kernel modules...
    capabilities: list[str] = field(default_factory=list)  # start, stop, logs, metrics, health...
    architectures: list[str] = field(default_factory=lambda: ["amd64", "arm64"])
    env_keys: list[str] = field(default_factory=list)  # کلیدهای .env مربوط به این تونل
    docs_fa: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


# فیلدهای مشترک همه تونل‌ها. هیچ‌کدام مقدار پیش‌فرض «حدسی» برای CLI ندارند.
COMMON_FIELDS: list[ConfigField] = [
    ConfigField("role_source", "نقش سرور مبدأ", "select", True, "client",
                "نقش سرور مبدأ در این تونل", ["client", "server"]),
    ConfigField("role_destination", "نقش سرور مقصد", "select", True, "server",
                "نقش سرور مقصد در این تونل", ["client", "server"]),
    ConfigField("protocol", "پروتکل", "select", True, "tcp",
                "پروتکل انتقال؛ فقط مقادیری را انتخاب کنید که خود تونل پشتیبانی می‌کند",
                ["tcp", "udp", "tcp+udp", "icmp", "other"]),
    ConfigField("listen_port", "پورت شنونده (سرور مقصد)", "port", True, None,
                "پورتی که سمت مقصد گوش می‌دهد", minimum=1, maximum=65535),
    ConfigField("remote_port", "پورت مقصد/فورواردشده", "port", True, None,
                "پورتی که ترافیک به آن هدایت می‌شود", minimum=1, maximum=65535),
    ConfigField("local_port", "پورت محلی سرور مبدأ", "port", False, None,
                "در صورت نیاز، پورت محلی سمت مبدأ", minimum=1, maximum=65535),
    ConfigField("mtu", "MTU", "int", False, None, "در صورت نیاز مقدار MTU", minimum=576, maximum=9000,
                advanced=True),
    ConfigField("keepalive", "Keepalive (ثانیه)", "int", False, None, advanced=True, minimum=0, maximum=3600),
    ConfigField("timeout", "Timeout (ثانیه)", "int", False, None, advanced=True, minimum=0, maximum=3600),
    ConfigField("reconnect", "اتصال مجدد خودکار", "bool", False, True, advanced=True),
    ConfigField("bandwidth_limit_mbps", "محدودیت پهنای باند (Mbps)", "int", False, None, advanced=True,
                minimum=0, maximum=100000),
    ConfigField("dns", "DNS", "string", False, None, "در صورت نیاز، DNS اختصاصی تونل", advanced=True),
    ConfigField("routing_notes", "یادداشت مسیردهی", "text", False, None,
                "تغییرات مسیردهی مورد نیاز؛ در Audit ثبت می‌شود", advanced=True),
    ConfigField("auth_token", "توکن/رمز احراز هویت تونل", "secret", False, None,
                "به صورت رمزگذاری‌شده ذخیره می‌شود", advanced=False, secret=True),
    ConfigField("config_template", "قالب فایل Config تونل", "text", False, None,
                "متن خام config مطابق مستندات خود تونل. متغیرها با $listen_port و ... جایگزین می‌شوند",
                advanced=True),
    ConfigField("extra_args", "آرگومان‌های اجرای تونل", "text", False, None,
                "آرگومان‌های واقعی CLI مطابق مستندات تونل. پنل هیچ آرگومانی از خود اضافه نمی‌کند",
                advanced=True),
    ConfigField("health_check_command", "دستور بررسی سلامت", "string", False, None,
                "اختیاری؛ اگر خالی باشد از وضعیت سرویس systemd استفاده می‌شود", advanced=True),
]

SECRET_KEYS = {f.key for f in COMMON_FIELDS if f.secret} | {"auth_token", "private_key", "certificate"}

DANGEROUS_PORTS = {22, 80, 443}


class TunnelAdapter(ABC):
    """Interface استاندارد همه تونل‌ها."""

    metadata: AdapterMetadata
    extra_fields: list[ConfigField] = []

    def __init__(self, agent_client, tunnel_type_row=None):
        self.agent = agent_client
        self.type_row = tunnel_type_row

    # ---------- توصیف ----------
    @property
    def key(self) -> str:
        return self.metadata.key

    def config_schema(self) -> list[dict]:
        return [f.as_dict() for f in [*COMMON_FIELDS, *self.extra_fields]]

    def is_configured(self) -> bool:
        """آیا منبع (Binary یا Repository) این تونل تنظیم شده است؟"""
        if not self.type_row:
            return False
        if self.metadata.source_kind == "binary":
            return bool(self.type_row.binary_path)
        return bool(self.type_row.repository_url)

    # ---------- اعتبارسنجی ----------
    def validate_config(self, config: dict) -> tuple[list[str], list[str]]:
        """خروجی: (errors, warnings)"""
        errors: list[str] = []
        warnings: list[str] = []
        fields = {f.key: f for f in [*COMMON_FIELDS, *self.extra_fields]}

        for key, f in fields.items():
            value = config.get(key)
            if f.required and value in (None, ""):
                errors.append(f"مقدار «{f.label_fa}» الزامی است.")
                continue
            if value in (None, ""):
                continue
            if f.type in ("int", "port"):
                try:
                    ivalue = int(value)
                except (TypeError, ValueError):
                    errors.append(f"«{f.label_fa}» باید عدد باشد.")
                    continue
                if f.minimum is not None and ivalue < f.minimum:
                    errors.append(f"«{f.label_fa}» نباید کمتر از {f.minimum} باشد.")
                if f.maximum is not None and ivalue > f.maximum:
                    errors.append(f"«{f.label_fa}» نباید بیشتر از {f.maximum} باشد.")
            if f.type == "select" and f.options and str(value) not in f.options:
                errors.append(f"مقدار «{f.label_fa}» معتبر نیست.")

        unknown = set(config) - set(fields) - {"secrets"}
        if unknown:
            warnings.append("کلیدهای ناشناخته نادیده گرفته می‌شوند: " + ", ".join(sorted(unknown)))

        for port_key in ("listen_port", "remote_port", "local_port"):
            port = config.get(port_key)
            if port and int(port) in DANGEROUS_PORTS:
                warnings.append(
                    f"پورت {port} برای مدیریت سرور (SSH/HTTP/HTTPS) استفاده می‌شود؛ "
                    "استفاده از آن ممکن است دسترسی شما را قطع کند."
                )

        args = config.get("extra_args")
        if args:
            try:
                shlex.split(str(args))
            except ValueError:
                errors.append("آرگومان‌های اجرای تونل قابل تفسیر نیستند (کوتیشن ناقص).")

        if not self.is_configured():
            errors.append(
                f"منبع تونل «{self.metadata.display_name_fa}» تنظیم نشده است. "
                "ابتدا در تنظیمات ← انواع تونل، مسیر Binary یا آدرس Repository را وارد کنید."
            )
        return errors, warnings

    # ---------- تولید config ----------
    def generate_config(self, tunnel, config: dict, secrets: dict | None = None) -> str:
        """قالب داده‌شده توسط کاربر را با مقادیر واقعی رندر می‌کند."""
        template = config.get("config_template") or ""
        if not template:
            return ""
        values: dict[str, Any] = {
            "tunnel_id": tunnel.id,
            "tunnel_name": tunnel.name,
            "service_name": tunnel.service_name or f"alfa-tunnel-{tunnel.id[:8]}",
            **{k: v for k, v in config.items() if k not in ("config_template",)},
            **(secrets or {}),
        }
        try:
            return Template(template).safe_substitute(values)
        except Exception as exc:  # pragma: no cover
            raise ValidationFailed(f"رندر قالب config ناموفق بود: {exc}") from exc

    def render_args(self, tunnel, config: dict, secrets: dict | None = None) -> list[str]:
        raw = config.get("extra_args") or ""
        if not raw:
            return []
        values = {
            "tunnel_id": tunnel.id,
            "service_name": tunnel.service_name or f"alfa-tunnel-{tunnel.id[:8]}",
            **{k: v for k, v in config.items() if k != "extra_args"},
            **(secrets or {}),
        }
        return shlex.split(Template(str(raw)).safe_substitute(values))

    # ---------- بسته ارسالی به Agent ----------
    def source_spec(self) -> dict:
        row = self.type_row
        spec = {
            "kind": self.metadata.source_kind,
            "binary_path": getattr(row, "binary_path", "") or "",
            "checksum": getattr(row, "binary_checksum", "") or "",
            "repository_url": getattr(row, "repository_url", "") or "",
            "repository_ref": getattr(row, "repository_ref", "") or "",
            "version": getattr(row, "version", "") or "",
        }
        panel_url = os.getenv("PANEL_URL", "").rstrip("/")
        bundled = {
            "broken_node": ("BrokenNode.tar.gz", "bundled_archive"),
            "premium_backhaul": ("backhaul_premium", "bundled_binary"),
        }.get(self.key)
        if bundled and panel_url:
            name, kind = bundled
            spec.update({"kind": kind, "asset_url": f"{panel_url}/tunnel-assets/{name}", "asset_name": name})
        return spec

    def build_payload(self, tunnel, config: dict, secrets: dict | None = None) -> dict:
        return {
            "tunnel_id": tunnel.id,
            "type_key": self.key,
            "service_name": tunnel.service_name or f"alfa-tunnel-{tunnel.id[:8]}",
            "source": self.source_spec(),
            "config_file": self.generate_config(tunnel, config, secrets),
            "args": self.render_args(tunnel, config, secrets),
            "requires": self.metadata.requires,
            "env": {k: str(v) for k, v in (config.get("env") or {}).items()},
            "health_check_command": config.get("health_check_command") or "",
        }

    # ---------- عملیات (همه از طریق اکشن‌های allowlist‌شده Agent) ----------
    async def install(self, server, tunnel, config: dict, secrets: dict | None = None, dry_run=False):
        payload = self.build_payload(tunnel, config, secrets)
        payload["dry_run"] = dry_run
        return await self.agent.call(server, "tunnel_install", payload)

    async def configure(self, server, tunnel, config: dict, secrets: dict | None = None):
        return await self.agent.call(server, "tunnel_configure", self.build_payload(tunnel, config, secrets))

    async def uninstall(self, server, tunnel):
        return await self.agent.call(
            server, "tunnel_remove", {"tunnel_id": tunnel.id, "service_name": tunnel.service_name}
        )

    async def start(self, server, tunnel):
        return await self.agent.call(server, "tunnel_start", {"tunnel_id": tunnel.id})

    async def stop(self, server, tunnel):
        return await self.agent.call(server, "tunnel_stop", {"tunnel_id": tunnel.id})

    async def restart(self, server, tunnel):
        return await self.agent.call(server, "tunnel_restart", {"tunnel_id": tunnel.id})

    async def status(self, server, tunnel):
        return await self.agent.call(server, "tunnel_status", {"tunnel_id": tunnel.id})

    async def logs(self, server, tunnel, lines: int = 200):
        return await self.agent.call(server, "tunnel_logs", {"tunnel_id": tunnel.id, "lines": lines})

    async def health_check(self, server, tunnel, config: dict | None = None):
        return await self.agent.call(
            server,
            "tunnel_health",
            {
                "tunnel_id": tunnel.id,
                "check_command": (config or {}).get("health_check_command") or "",
                "probe_host": server.ip_address,
            },
        )

    async def metrics(self, server, tunnel):
        return await self.agent.call(server, "tunnel_metrics", {"tunnel_id": tunnel.id})

    async def dependency_check(self, server):
        return await self.agent.call(server, "dependency_check", {"requires": self.metadata.requires})

    @staticmethod
    @abstractmethod
    def describe() -> AdapterMetadata:  # pragma: no cover - در هر Adapter پیاده می‌شود
        ...
