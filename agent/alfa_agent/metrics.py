"""جمع‌آوری متریک از /proc و /sys بدون هیچ وابستگی خارجی (سبک و کم‌هزینه)."""
from __future__ import annotations

import os
import platform
import shutil
import socket
import subprocess
import time
from datetime import datetime, timezone

_prev_cpu: tuple[int, int] | None = None
_prev_net: tuple[float, int, int, int, int] | None = None

SKIP_INTERFACES = ("lo", "docker", "br-", "veth", "virbr")


def _read(path: str, default: str = "") -> str:
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return default


def cpu_percent() -> float:
    """درصد مصرف CPU بر اساس اختلاف دو نمونه /proc/stat."""
    global _prev_cpu
    line = _read("/proc/stat").split("\n")[0]
    parts = [int(v) for v in line.split()[1:] if v.isdigit()]
    if not parts:
        return 0.0
    idle = parts[3] + (parts[4] if len(parts) > 4 else 0)
    total = sum(parts)
    if _prev_cpu is None:
        _prev_cpu = (idle, total)
        return 0.0
    prev_idle, prev_total = _prev_cpu
    _prev_cpu = (idle, total)
    delta_total = total - prev_total
    delta_idle = idle - prev_idle
    if delta_total <= 0:
        return 0.0
    return round(max(0.0, min(100.0, (1 - delta_idle / delta_total) * 100)), 2)


def load_average() -> list[float]:
    try:
        return [round(v, 2) for v in os.getloadavg()]
    except OSError:
        return [0.0, 0.0, 0.0]


def memory() -> dict:
    info: dict[str, int] = {}
    for line in _read("/proc/meminfo").split("\n"):
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        digits = value.strip().split(" ")[0]
        if digits.isdigit():
            info[key.strip()] = int(digits) * 1024
    total = info.get("MemTotal", 0)
    available = info.get("MemAvailable", info.get("MemFree", 0))
    swap_total = info.get("SwapTotal", 0)
    swap_free = info.get("SwapFree", 0)
    return {
        "ram_total": total,
        "ram_used": max(0, total - available),
        "swap_total": swap_total,
        "swap_used": max(0, swap_total - swap_free),
    }


def disk(path: str = "/") -> dict:
    try:
        usage = shutil.disk_usage(path)
        return {"disk_total": usage.total, "disk_used": usage.used}
    except OSError:
        return {"disk_total": 0, "disk_used": 0}


def _net_counters() -> tuple[int, int, int, int]:
    rx = tx = prx = ptx = 0
    for line in _read("/proc/net/dev").split("\n")[2:]:
        if ":" not in line:
            continue
        name, _, rest = line.partition(":")
        name = name.strip()
        if name.startswith(SKIP_INTERFACES):
            continue
        fields = rest.split()
        if len(fields) < 10:
            continue
        rx += int(fields[0])
        prx += int(fields[1])
        tx += int(fields[8])
        ptx += int(fields[9])
    return rx, tx, prx, ptx


def network() -> dict:
    """شمارنده‌های شبکه + نرخ لحظه‌ای (بایت بر ثانیه)."""
    global _prev_net
    now = time.time()
    rx, tx, prx, ptx = _net_counters()
    result = {
        "net_rx_bytes": rx,
        "net_tx_bytes": tx,
        "net_rx_rate": 0.0,
        "net_tx_rate": 0.0,
        "packets_rx_rate": 0.0,
        "packets_tx_rate": 0.0,
    }
    if _prev_net is not None:
        prev_ts, prev_rx, prev_tx, prev_prx, prev_ptx = _prev_net
        elapsed = max(0.001, now - prev_ts)
        result["net_rx_rate"] = round(max(0, rx - prev_rx) / elapsed, 2)
        result["net_tx_rate"] = round(max(0, tx - prev_tx) / elapsed, 2)
        result["packets_rx_rate"] = round(max(0, prx - prev_prx) / elapsed, 2)
        result["packets_tx_rate"] = round(max(0, ptx - prev_ptx) / elapsed, 2)
    _prev_net = (now, rx, tx, prx, ptx)
    return result


def uptime_seconds() -> int:
    raw = _read("/proc/uptime").split(" ")
    try:
        return int(float(raw[0]))
    except (ValueError, IndexError):
        return 0


def collect() -> dict:
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "cpu_percent": cpu_percent(),
        "load": load_average(),
        "uptime_seconds": uptime_seconds(),
    }
    payload.update(memory())
    payload.update(disk())
    payload.update(network())
    return payload


def _cpu_model() -> str:
    for line in _read("/proc/cpuinfo").split("\n"):
        if "model name" in line:
            return line.split(":", 1)[1].strip()
    return platform.processor() or "unknown"


def _os_pretty_name() -> str:
    for line in _read("/etc/os-release").split("\n"):
        if line.startswith("PRETTY_NAME="):
            return line.split("=", 1)[1].strip().strip('"')
    return platform.system()


def _private_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(1)
            sock.connect(("10.255.255.255", 1))
            return sock.getsockname()[0]
    except OSError:
        return ""


def system_info(agent_version: str, capabilities: list[str]) -> dict:
    memory_info = memory()
    disk_info = disk()
    return {
        "hostname": socket.gethostname(),
        "os": _os_pretty_name(),
        "kernel": platform.release(),
        "architecture": normalize_arch(platform.machine()),
        "cpu_cores": os.cpu_count() or 1,
        "cpu_model": _cpu_model(),
        "ram_total": memory_info["ram_total"],
        "disk_total": disk_info["disk_total"],
        "public_ip": "",
        "private_ip": _private_ip(),
        "uptime_seconds": uptime_seconds(),
        "agent_version": agent_version,
        "capabilities": capabilities,
    }


def normalize_arch(machine: str) -> str:
    mapping = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}
    return mapping.get(machine.lower(), machine.lower())


def latency_probe(host: str, count: int = 4) -> dict:
    """اندازه‌گیری تأخیر، Packet Loss و Jitter با ابزار ping در صورت وجود."""
    binary = shutil.which("ping")
    if not binary or not host:
        return {"available": False, "reason": "ابزار ping روی سرور موجود نیست."}
    try:
        proc = subprocess.run(
            [binary, "-n", "-c", str(count), "-w", "6", host],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        return {"available": False, "reason": str(exc)}
    output = proc.stdout
    latency = loss = jitter = None
    for line in output.split("\n"):
        if "packet loss" in line:
            for token in line.split(","):
                if "packet loss" in token:
                    loss = float(token.strip().split("%")[0])
        if line.startswith(("rtt", "round-trip")):
            try:
                values = line.split("=")[1].strip().split(" ")[0].split("/")
                latency = float(values[1])
                jitter = float(values[3]) if len(values) > 3 else None
            except (IndexError, ValueError):
                pass
    return {
        "available": True,
        "latency_ms": latency,
        "packet_loss": loss,
        "jitter_ms": jitter,
        "output": output[-2000:],
    }
