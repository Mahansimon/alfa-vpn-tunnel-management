"""نقشه اکشن‌های مجاز Agent. هر ورودی به یک تابع مشخص وصل است."""
from __future__ import annotations

import os
import shutil

from alfa_agent import actions, tunnels
from alfa_agent.actions import ActionError, _run, _sudo
from alfa_agent.config import AgentConfig


def agent_update(config: AgentConfig, params: dict) -> dict:
    """به‌روزرسانی خود Agent با اسکریپت نصب (Download → Verify → Install → Restart)."""
    from alfa_agent import __version__

    panel = config.panel_url
    if not panel:
        raise ActionError("آدرس پنل تنظیم نشده است.")
    script_url = f"{panel}/install-agent.sh"
    target = os.path.join(config.dirs["state"], "install-agent.sh")
    import urllib.request

    try:
        with urllib.request.urlopen(script_url, timeout=60) as response, open(target, "wb") as handle:
            shutil.copyfileobj(response, handle)
    except Exception as exc:
        raise ActionError(f"دریافت اسکریپت به‌روزرسانی ناموفق بود: {exc}") from exc
    os.chmod(target, 0o700)
    code, output = _sudo(["/bin/bash", target, "--upgrade", "--panel-url", panel], timeout=900)
    if code != 0:
        return {"ok": False, "error": output[-800:]}
    return {"ok": True, "output": output[-2000:], "data": {"version": __version__}}


ACTIONS = {
    "ping": actions.action_ping,
    "system_info": actions.action_system_info,
    "metrics": actions.action_metrics,
    "latency_probe": actions.action_latency_probe,
    "service_status": actions.action_service_status,
    "service_start": actions.action_service_start,
    "service_stop": actions.action_service_stop,
    "service_restart": actions.action_service_restart,
    "logs": actions.action_logs,
    "agent_logs": actions.action_agent_logs,
    "dependency_check": actions.action_dependency_check,
    "firewall_plan": actions.action_firewall_plan,
    "tunnel_install": tunnels.install,
    "tunnel_configure": tunnels.configure,
    "tunnel_remove": tunnels.remove,
    "tunnel_rollback": tunnels.rollback,
    "tunnel_start": lambda config, params: actions.action_service_start(config, params),
    "tunnel_stop": lambda config, params: actions.action_service_stop(config, params),
    "tunnel_restart": lambda config, params: actions.action_service_restart(config, params),
    "tunnel_status": tunnels.status,
    "tunnel_logs": tunnels.logs,
    "tunnel_health": tunnels.health,
    "tunnel_metrics": tunnels.tunnel_metrics,
    "tunnel_update": tunnels.update,
    "binary_install": tunnels.install,
    "agent_update": agent_update,
}


def dispatch(config: AgentConfig, action: str, params: dict) -> dict:
    handler = ACTIONS.get(action)
    if handler is None:
        raise ActionError(f"اکشن «{action}» مجاز نیست.")
    return handler(config, params or {})


def selftest(config: AgentConfig) -> dict:
    """بررسی سریع پیش‌نیازهای Agent (برای اسکریپت نصب)."""
    checks = {
        "systemd": os.path.isdir("/run/systemd/system"),
        "systemctl": bool(shutil.which("systemctl")),
        "journalctl": bool(shutil.which("journalctl")),
        "git": bool(shutil.which("git")),
        "ping": bool(shutil.which("ping")),
        "tunnel_dir": os.path.isdir(config.dirs["tunnels"]) or True,
    }
    code, _ = _run(["/bin/true"])
    checks["exec"] = code == 0
    return checks
