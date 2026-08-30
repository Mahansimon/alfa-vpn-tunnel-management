"""اکشن‌های allowlist‌شده Agent.

هیچ endpointی برای اجرای دستور دلخواه (bash -c ...) وجود ندارد. تنها اکشن‌های
زیر پذیرفته می‌شوند و هرکدام ورودی خود را اعتبارسنجی می‌کنند. همه فرمان‌ها با
shell=False اجرا می‌شوند تا Command Injection ممکن نباشد.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time

from alfa_agent import __version__, metrics
from alfa_agent.config import AgentConfig

SAFE_NAME = re.compile(r"^[A-Za-z0-9._@-]+$")
SYSTEMCTL = shutil.which("systemctl") or "/bin/systemctl"
JOURNALCTL = shutil.which("journalctl") or "/bin/journalctl"
ALLOWED_SERVICE_PREFIXES = ("alfa-tunnel-", "alfa-agent")
BUILD_TIMEOUT = 1800


class ActionError(Exception):
    """خطای قابل نمایش برای پنل."""


def _run(argv: list[str], timeout: int = 60, check: bool = False, cwd: str | None = None) -> tuple[int, str]:
    """اجرای فرمان بدون shell. خروجی: (کد خروج، خروجی متنی)."""
    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout, cwd=cwd, shell=False
        )
    except FileNotFoundError as exc:
        raise ActionError(f"دستور مورد نیاز روی سرور نصب نیست: {argv[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise ActionError(f"اجرای «{argv[0]}» بیش از حد طول کشید.") from exc
    output = (proc.stdout or "") + (proc.stderr or "")
    if check and proc.returncode != 0:
        raise ActionError(output.strip()[-1500:] or f"کد خروج {proc.returncode}")
    return proc.returncode, output


def _sudo(argv: list[str], timeout: int = 60) -> tuple[int, str]:
    """اجرای فرمان با sudo محدود (فایل sudoers فقط همین دستورها را مجاز کرده)."""
    if os.geteuid() == 0:
        return _run(argv, timeout=timeout)
    sudo = shutil.which("sudo")
    if not sudo:
        raise ActionError("sudo روی سرور موجود نیست و Agent با کاربر غیرروت اجرا می‌شود.")
    return _run([sudo, "-n", *argv], timeout=timeout)


def _service_name(params: dict) -> str:
    name = str(params.get("service") or params.get("service_name") or "").strip()
    if not name:
        tunnel_id = str(params.get("tunnel_id", ""))
        if not SAFE_NAME.match(tunnel_id or ""):
            raise ActionError("شناسه تونل معتبر نیست.")
        name = f"alfa-tunnel-{tunnel_id[:8]}"
    if not SAFE_NAME.match(name):
        raise ActionError("نام سرویس معتبر نیست.")
    if not name.startswith(ALLOWED_SERVICE_PREFIXES):
        raise ActionError("مدیریت این سرویس مجاز نیست؛ فقط سرویس‌های alfa قابل کنترل هستند.")
    return name if name.endswith(".service") else f"{name}.service"


def _tunnel_dir(config: AgentConfig, tunnel_id: str) -> str:
    if not SAFE_NAME.match(tunnel_id or ""):
        raise ActionError("شناسه تونل معتبر نیست.")
    path = os.path.join(config.dirs["tunnels"], tunnel_id)
    # جلوگیری از Path Traversal
    root = os.path.realpath(config.dirs["tunnels"])
    resolved = os.path.realpath(path)
    if not resolved.startswith(root):
        raise ActionError("مسیر پیکربندی مجاز نیست.")
    return resolved


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


# --------------------------- اکشن‌های پایه ---------------------------


def action_ping(config: AgentConfig, params: dict) -> dict:
    return {"ok": True, "output": "pong", "data": {"version": __version__, "time": time.time()}}


def action_system_info(config: AgentConfig, params: dict) -> dict:
    return {"ok": True, "data": metrics.system_info(__version__, capabilities())}


def action_metrics(config: AgentConfig, params: dict) -> dict:
    return {"ok": True, "data": metrics.collect()}


def action_latency_probe(config: AgentConfig, params: dict) -> dict:
    host = str(params.get("probe_host") or params.get("host") or "")
    if host and not re.match(r"^[A-Za-z0-9.:_-]+$", host):
        raise ActionError("آدرس مقصد معتبر نیست.")
    return {"ok": True, "data": metrics.latency_probe(host)}


def action_service_status(config: AgentConfig, params: dict) -> dict:
    service = _service_name(params)
    code, output = _run([SYSTEMCTL, "status", service, "--no-pager", "--lines", "20"])
    active, _ = _run([SYSTEMCTL, "is-active", service])
    return {"ok": True, "output": output[-4000:], "data": {"active": active == 0, "exit_code": code}}


def action_service_start(config: AgentConfig, params: dict) -> dict:
    service = _service_name(params)
    code, output = _sudo([SYSTEMCTL, "start", service])
    return {"ok": code == 0, "output": output[-2000:], "error": "" if code == 0 else output[-500:]}


def action_service_stop(config: AgentConfig, params: dict) -> dict:
    service = _service_name(params)
    code, output = _sudo([SYSTEMCTL, "stop", service])
    return {"ok": code == 0, "output": output[-2000:], "error": "" if code == 0 else output[-500:]}


def action_service_restart(config: AgentConfig, params: dict) -> dict:
    service = _service_name(params)
    code, output = _sudo([SYSTEMCTL, "restart", service])
    return {"ok": code == 0, "output": output[-2000:], "error": "" if code == 0 else output[-500:]}


def action_logs(config: AgentConfig, params: dict) -> dict:
    kind = str(params.get("kind", "system"))
    lines = max(10, min(2000, int(params.get("lines", 200))))
    if kind == "processes":
        ps = shutil.which("ps")
        if not ps:
            raise ActionError("ابزار ps روی سرور موجود نیست.")
        _, output = _run([ps, "-eo", "pid,comm,pcpu,pmem,etime", "--sort=-pcpu"])
        rows = []
        for line in output.strip().split("\n")[1 : lines + 1]:
            parts = line.split(None, 4)
            if len(parts) == 5:
                rows.append(
                    {
                        "pid": parts[0],
                        "name": parts[1],
                        "cpu": parts[2],
                        "memory": parts[3],
                        "elapsed": parts[4],
                    }
                )
        return {"ok": True, "data": {"processes": rows}}
    if kind == "agent":
        _, output = _run([JOURNALCTL, "-u", "alfa-agent.service", "-n", str(lines), "--no-pager"])
        return {"ok": True, "output": output[-20000:]}
    _, output = _run([JOURNALCTL, "-n", str(lines), "--no-pager"])
    return {"ok": True, "output": output[-20000:]}


def action_agent_logs(config: AgentConfig, params: dict) -> dict:
    return action_logs(config, {"kind": "agent", "lines": params.get("lines", 300)})


def action_dependency_check(config: AgentConfig, params: dict) -> dict:
    """بررسی ابزارها/قابلیت‌های مورد نیاز یک تونل پیش از استقرار."""
    requires = [str(r) for r in (params.get("requires") or [])]
    missing: list[str] = []
    details: dict[str, str] = {}
    for requirement in requires:
        if requirement == "systemd":
            ok = os.path.isdir("/run/systemd/system")
            details[requirement] = "موجود" if ok else "systemd فعال نیست"
        elif requirement in ("iptables", "nftables", "ip", "tc"):
            path = shutil.which(requirement)
            ok = bool(path)
            details[requirement] = path or "نصب نشده"
        elif requirement == "sysctl":
            ok = bool(shutil.which("sysctl"))
            details[requirement] = "موجود" if ok else "نصب نشده"
        elif requirement == "cap_net_raw":
            ok = os.geteuid() == 0 or bool(shutil.which("setcap"))
            details[requirement] = "قابل تنظیم" if ok else "setcap موجود نیست"
        elif requirement.startswith("module:"):
            module = requirement.split(":", 1)[1]
            code, output = _run(["/sbin/modinfo", module])
            ok = code == 0
            details[requirement] = "موجود" if ok else output[-200:]
        else:
            path = shutil.which(requirement)
            ok = bool(path)
            details[requirement] = path or "نصب نشده"
        if not ok:
            missing.append(requirement)
    return {
        "ok": not missing,
        "output": json.dumps(details, ensure_ascii=False),
        "error": ("وابستگی‌های ناموجود: " + ", ".join(missing)) if missing else "",
        "data": {"details": details, "missing": missing},
    }


def action_firewall_plan(config: AgentConfig, params: dict) -> dict:
    """فقط «نقشه» تغییرات فایروال را برمی‌گرداند؛ چیزی اعمال نمی‌شود."""
    ports = [int(p) for p in (params.get("ports") or []) if str(p).isdigit()]
    protocol = str(params.get("protocol", "tcp"))
    ufw = shutil.which("ufw")
    plan = [f"allow {port}/{protocol}" for port in ports]
    current = ""
    if ufw:
        _, current = _sudo([ufw, "status"], timeout=20)
    return {"ok": True, "data": {"tool": "ufw" if ufw else "none", "plan": plan, "current": current[-2000:]}}


def capabilities() -> list[str]:
    caps = ["metrics", "tunnels", "logs", "services", "health"]
    if shutil.which("git"):
        caps.append("git")
    if shutil.which("docker"):
        caps.append("docker")
    if shutil.which("go"):
        caps.append("go")
    if shutil.which("cargo"):
        caps.append("rust")
    if shutil.which("make"):
        caps.append("make")
    if shutil.which("ping"):
        caps.append("latency")
    return caps
