"""مدیریت تونل روی سرور: نصب، پیکربندی، سرویس systemd، سلامت و بازگردانی.

نکته کلیدی: هیچ آرگومان یا فرمت configی حدس زده نمی‌شود. محتوای فایل config و
آرگومان‌های اجرا از پنل می‌آیند (که خود کاربر مطابق مستندات تونل وارد کرده است).
Agent فقط آن‌ها را با امنیت اجرا می‌کند.
"""
from __future__ import annotations

import json
import os
import shlex
import shutil
import stat
import tarfile
import time
import urllib.error
import urllib.request
import zipfile

from alfa_agent import metrics
from alfa_agent.actions import (
    BUILD_TIMEOUT,
    SAFE_NAME,
    SYSTEMCTL,
    ActionError,
    _run,
    _service_name,
    _sha256,
    _sudo,
    _tunnel_dir,
)
from alfa_agent.config import AgentConfig

UNIT_DIR = "/etc/systemd/system"
GITHUB_API = "https://api.github.com"


def _write_file(path: str, content: str, mode: int = 0o640) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        handle.write(content)
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def _backup_existing(directory: str) -> str | None:
    if not os.path.isdir(directory):
        return None
    target = f"{directory}.bak-{int(time.time())}"
    shutil.copytree(directory, target, dirs_exist_ok=True)
    return target


def _github_slug(url: str) -> str | None:
    if "github.com" not in url:
        return None
    cleaned = url.rstrip("/").removesuffix(".git")
    parts = cleaned.split("github.com")[-1].strip(":/").split("/")
    return f"{parts[0]}/{parts[1]}" if len(parts) >= 2 else None


def _download(url: str, target: str, token: str = "") -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "alfa-agent"})
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=120) as response, open(target, "wb") as handle:
            shutil.copyfileobj(response, handle)
    except (urllib.error.URLError, OSError) as exc:
        raise ActionError(f"دانلود ناموفق بود: {exc}") from exc


def _try_release_asset(slug: str, ref: str, arch: str, workdir: str, token: str = "") -> str | None:
    """در صورت وجود Release مناسب، artifact را دانلود و استخراج می‌کند."""
    endpoint = f"{GITHUB_API}/repos/{slug}/releases/{'tags/' + ref if ref else 'latest'}"
    request = urllib.request.Request(endpoint, headers={"User-Agent": "alfa-agent"})
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode())
    except Exception:
        return None
    assets = data.get("assets") or []
    if not assets:
        return None
    keywords = [arch, "linux"]
    scored = []
    for asset in assets:
        name = (asset.get("name") or "").lower()
        score = sum(1 for keyword in keywords if keyword in name)
        scored.append((score, asset))
    scored.sort(key=lambda item: item[0], reverse=True)
    best_score, best = scored[0]
    if best_score == 0:
        return None
    target = os.path.join(workdir, best.get("name"))
    _download(best.get("browser_download_url"), target, token)
    return _extract_if_needed(target, workdir)


def _extract_if_needed(path: str, workdir: str) -> str:
    extract_dir = os.path.join(workdir, "extracted")
    os.makedirs(extract_dir, exist_ok=True)
    if path.endswith((".tar.gz", ".tgz", ".tar.xz", ".tar.bz2", ".tar")):
        with tarfile.open(path) as archive:
            archive.extractall(extract_dir, filter="data")
        return extract_dir
    if path.endswith(".zip"):
        with zipfile.ZipFile(path) as archive:
            archive.extractall(extract_dir)
        return extract_dir
    return path


def _find_executable(root: str, hint: str = "") -> str | None:
    """جستجوی فایل اجرایی در خروجی build/استخراج."""
    if os.path.isfile(root) and os.access(root, os.X_OK):
        return root
    candidates: list[tuple[int, str]] = []
    for base, _dirs, files in os.walk(root):
        for name in files:
            path = os.path.join(base, name)
            if not os.path.isfile(path):
                continue
            try:
                mode = os.stat(path).st_mode
            except OSError:
                continue
            executable = bool(mode & stat.S_IXUSR)
            score = 0
            if hint and hint.lower() == name.lower():
                score += 10
            if executable:
                score += 3
            if "/target/release/" in path or "/bin/" in path:
                score += 2
            if name.endswith((".so", ".a", ".txt", ".md", ".json", ".toml", ".yaml", ".sh")):
                score -= 5
            if score > 0:
                candidates.append((score, path))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _detect_and_build(workdir: str, source: dict) -> str:
    """تشخیص نوع پروژه و build آن. هیچ فرضی درباره ساختار Repository نداریم."""
    hint = source.get("binary_name_hint") or ""
    use_container = bool(source.get("build_in_container")) and shutil.which("docker")

    listing = os.listdir(workdir)
    if "Dockerfile" in listing and use_container:
        image = f"alfa-tunnel-build:{int(time.time())}"
        _run(["docker", "build", "-t", image, "."], timeout=BUILD_TIMEOUT, check=True, cwd=workdir)
        return f"docker:{image}"
    if "Makefile" in listing and shutil.which("make"):
        _run(["make"], timeout=BUILD_TIMEOUT, check=True, cwd=workdir)
    elif "go.mod" in listing and shutil.which("go"):
        # Prefer a single main package. This covers root-level Go apps (e.g.
        # BackPack) and cmd/main.go layouts (e.g. Paqet).
        if os.path.isfile(os.path.join(workdir, "main.go")):
            go_target = "."
        elif os.path.isfile(os.path.join(workdir, "cmd", "main.go")):
            go_target = "./cmd"
        else:
            go_target = None
            cmd_dir = os.path.join(workdir, "cmd")
            if os.path.isdir(cmd_dir):
                for name in sorted(os.listdir(cmd_dir)):
                    candidate = os.path.join(cmd_dir, name, "main.go")
                    if os.path.isfile(candidate):
                        go_target = f"./cmd/{name}"
                        break
            if go_target is None:
                go_target = "."
        _run(["go", "build", "-o", "alfa-build-output", go_target], timeout=BUILD_TIMEOUT, check=True, cwd=workdir)
    elif "Cargo.toml" in listing and shutil.which("cargo"):
        _run(["cargo", "build", "--release"], timeout=BUILD_TIMEOUT, check=True, cwd=workdir)
    elif any(name in listing for name in ("pyproject.toml", "setup.py", "requirements.txt")):
        venv = os.path.join(workdir, ".venv")
        _run(["python3", "-m", "venv", venv], timeout=300, check=True)
        pip = os.path.join(venv, "bin", "pip")
        if "requirements.txt" in listing:
            _run([pip, "install", "-r", "requirements.txt"], timeout=BUILD_TIMEOUT, cwd=workdir)
        else:
            _run([pip, "install", "."], timeout=BUILD_TIMEOUT, cwd=workdir)
        found = _find_executable(os.path.join(venv, "bin"), hint)
        if found:
            return found
    binary = _find_executable(workdir, hint)
    if not binary:
        raise ActionError(
            "فایل اجرایی تونل پیدا نشد. اگر نام Binary خروجی را می‌دانید، آن را در تنظیمات تونل "
            "(فیلد «نام Binary خروجی») وارد کنید."
        )
    return binary


def _install_from_source(config: AgentConfig, type_key: str, source: dict) -> str:
    """آماده‌سازی Binary تونل و برگرداندن مسیر نهایی اجرا."""
    arch = metrics.normalize_arch(os.uname().machine)
    if arch not in ("amd64", "arm64"):
        raise ActionError(f"معماری «{arch}» پشتیبانی نمی‌شود. فقط amd64 و arm64 پشتیبانی می‌شوند.")
    destination_dir = config.dirs["binaries"]
    os.makedirs(destination_dir, exist_ok=True)
    destination = os.path.join(destination_dir, type_key)

    # Assets bundled with the panel are fetched directly from the configured panel URL.
    # They are not executed as shell scripts; archives are extracted and the expected
    # architecture-specific executable is selected.
    if source.get("kind") in ("bundled_binary", "bundled_archive"):
        asset_url = source.get("asset_url") or ""
        if not asset_url.startswith(("https://", "http://")):
            raise ActionError("آدرس Asset داخلی پنل معتبر نیست.")
        workroot = os.path.join(config.dirs["build"], type_key)
        shutil.rmtree(workroot, ignore_errors=True)
        os.makedirs(workroot, exist_ok=True)
        asset_name = os.path.basename(source.get("asset_name") or "asset")
        asset_path = os.path.join(workroot, asset_name)
        _download(asset_url, asset_path)
        if source.get("kind") == "bundled_archive":
            extracted = _extract_if_needed(asset_path, workroot)
            arch = metrics.normalize_arch(os.uname().machine)
            wanted = os.path.join(extracted, "BrokenNode", f"brokennode-linux-{arch}")
            if not os.path.isfile(wanted):
                wanted = _find_executable(extracted, f"brokennode-linux-{arch}") or ""
            if not wanted:
                raise ActionError(f"Binary بروکن نود برای معماری {arch} در بسته پیدا نشد.")
            shutil.copy2(wanted, destination)
        else:
            shutil.copy2(asset_path, destination)
        os.chmod(destination, 0o750)
        return destination

    if source.get("kind") == "direct_asset":
        asset_urls = source.get("asset_url_by_arch") or {}
        asset_url = asset_urls.get(arch) or source.get("asset_url") or ""
        if not asset_url.startswith(("https://", "http://")):
            raise ActionError("آدرس مستقیم Binary معتبر نیست.")
        workroot = os.path.join(config.dirs["build"], type_key)
        shutil.rmtree(workroot, ignore_errors=True)
        os.makedirs(workroot, exist_ok=True)
        asset_name = os.path.basename(asset_url.split("?", 1)[0]) or "asset"
        asset_path = os.path.join(workroot, asset_name)
        _download(asset_url, asset_path)
        extracted = _extract_if_needed(asset_path, workroot)
        binary = _find_executable(extracted, source.get("binary_name_hint", ""))
        if not binary:
            raise ActionError(f"Binary تونل برای معماری {arch} در Asset پیدا نشد.")
        shutil.copy2(binary, destination)
        os.chmod(destination, 0o750)
        return destination

    if source.get("kind") == "binary":
        path = source.get("binary_path") or ""
        if not path:
            raise ActionError("مسیر Binary این تونل در پنل تنظیم نشده است.")
        if not os.path.isfile(path):
            raise ActionError(
                f"فایل Binary در مسیر «{path}» روی این سرور وجود ندارد. آن را کپی کنید یا "
                "مسیر صحیح را در تنظیمات پنل وارد کنید."
            )
        checksum = source.get("checksum") or ""
        if checksum and _sha256(path) != checksum:
            raise ActionError("Checksum فایل Binary مطابقت ندارد؛ فایل ممکن است دستکاری شده باشد.")
        if os.path.realpath(path) != os.path.realpath(destination):
            shutil.copy2(path, destination)
        os.chmod(destination, 0o750)
        return destination

    repository = source.get("repository_url") or ""
    if not repository:
        raise ActionError("آدرس Repository این تونل در پنل تنظیم نشده است.")
    if not repository.startswith(("https://", "git@", "ssh://")):
        raise ActionError("آدرس Repository معتبر نیست.")
    ref = source.get("repository_ref") or ""
    workroot = os.path.join(config.dirs["build"], type_key)
    shutil.rmtree(workroot, ignore_errors=True)
    os.makedirs(workroot, exist_ok=True)

    slug = _github_slug(repository)
    if slug and source.get("prefer_release_asset", True):
        extracted = _try_release_asset(slug, ref, arch, workroot, os.environ.get("GITHUB_TOKEN", ""))
        if extracted:
            binary = _find_executable(extracted, source.get("binary_name_hint", ""))
            if binary:
                shutil.copy2(binary, destination)
                os.chmod(destination, 0o750)
                return destination

    git = shutil.which("git")
    if not git:
        raise ActionError("git روی سرور نصب نیست؛ نصب از Repository ممکن نیست.")
    clone_dir = os.path.join(workroot, "src")
    argv = [git, "clone", "--depth", "1"]
    if ref:
        argv += ["--branch", ref]
    argv += [repository, clone_dir]
    code, output = _run(argv, timeout=600)
    if code != 0:
        raise ActionError(f"clone کردن Repository ناموفق بود: {output[-400:]}")
    built = _detect_and_build(clone_dir, source)
    if built.startswith("docker:"):
        # اجرای تونل از طریق کانتینر: یک wrapper اجرایی ساخته می‌شود
        image = built.split(":", 1)[1]
        wrapper = destination
        _write_file(
            wrapper,
            "#!/bin/sh\n"
            f'exec docker run --rm --network host --name {type_key}-$$ {image} "$@"\n',
            0o750,
        )
        return wrapper
    shutil.copy2(built, destination)
    os.chmod(destination, 0o750)
    return destination


def _unit_content(name: str, binary: str, args: list[str], workdir: str, env: dict) -> str:
    exec_start = " ".join([binary, *args]) if args else binary
    env_lines = "\n".join(f'Environment="{key}={value}"' for key, value in (env or {}).items())
    return f"""[Unit]
Description=Alfa Tunnel {name}
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory={workdir}
ExecStart={exec_start}
Restart=always
RestartSec=5
LimitNOFILE=1048576
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=full
{env_lines}

[Install]
WantedBy=multi-user.target
"""


def install(config: AgentConfig, params: dict) -> dict:
    """نصب کامل تونل: آماده‌سازی Binary، نوشتن config و ساخت سرویس systemd."""
    tunnel_id = str(params.get("tunnel_id", ""))
    type_key = str(params.get("type_key", ""))
    if not SAFE_NAME.match(tunnel_id or "") or not SAFE_NAME.match(type_key or ""):
        raise ActionError("پارامترهای تونل معتبر نیستند.")
    directory = _tunnel_dir(config, tunnel_id)
    service = _service_name(params)
    dry_run = bool(params.get("dry_run"))

    binary_path = os.path.join(config.dirs["binaries"], type_key)
    steps: list[str] = []
    if dry_run:
        steps.append(f"آماده‌سازی Binary از منبع: {params.get('source', {}).get('kind')}")
        steps.append(f"نوشتن config در {directory}")
        steps.append(f"ساخت سرویس {service}")
        return {"ok": True, "output": "\n".join(steps), "data": {"dry_run": True}}

    backup = _backup_existing(directory)
    binary_path = _install_from_source(config, type_key, params.get("source") or {})
    steps.append(f"Binary آماده شد: {binary_path}")

    config_name = str(params.get("config_file_name") or "config.conf")
    if not SAFE_NAME.match(config_name):
        raise ActionError("نام فایل config معتبر نیست.")
    config_body = params.get("config_file") or ""
    os.makedirs(directory, exist_ok=True)
    if config_body:
        _write_file(os.path.join(directory, config_name), config_body, 0o640)
        steps.append(f"فایل config نوشته شد: {os.path.join(directory, config_name)}")

    raw_args = [str(a) for a in (params.get("args") or [])]
    config_path = os.path.join(directory, config_name)
    args = [a.replace("$CONFIG_PATH", config_path) for a in raw_args]
    unit = _unit_content(tunnel_id, binary_path, args, directory, params.get("env") or {})
    unit_path = os.path.join(UNIT_DIR, service)
    if os.geteuid() == 0:
        _write_file(unit_path, unit, 0o644)
    else:
        tmp_unit = os.path.join(config.dirs["state"], service)
        _write_file(tmp_unit, unit, 0o644)
        code, output = _sudo(["/bin/cp", tmp_unit, unit_path])
        if code != 0:
            raise ActionError(f"نوشتن سرویس systemd ناموفق بود: {output[-300:]}")
    steps.append(f"سرویس systemd ساخته شد: {service}")
    _sudo([SYSTEMCTL, "daemon-reload"])
    _sudo([SYSTEMCTL, "enable", service])
    steps.append("سرویس فعال شد.")
    if backup:
        steps.append(f"نسخه پشتیبان پیکربندی قبلی: {backup}")
    return {"ok": True, "output": "\n".join(steps), "data": {"binary": binary_path, "service": service}}


def configure(config: AgentConfig, params: dict) -> dict:
    """فقط بازنویسی فایل config و بازخوانی سرویس."""
    tunnel_id = str(params.get("tunnel_id", ""))
    directory = _tunnel_dir(config, tunnel_id)
    config_name = str(params.get("config_file_name") or "config.conf")
    if not SAFE_NAME.match(config_name):
        raise ActionError("نام فایل config معتبر نیست.")
    body = params.get("config_file") or ""
    backup = _backup_existing(directory)
    if body:
        _write_file(os.path.join(directory, config_name), body, 0o640)
    return {
        "ok": True,
        "output": f"پیکربندی به‌روزرسانی شد. نسخه پشتیبان: {backup or 'ندارد'}",
        "data": {"backup": backup},
    }


def remove(config: AgentConfig, params: dict) -> dict:
    """توقف سرویس، حذف unit و پاک کردن پیکربندی تونل."""
    tunnel_id = str(params.get("tunnel_id", ""))
    service = _service_name(params)
    _sudo([SYSTEMCTL, "stop", service])
    _sudo([SYSTEMCTL, "disable", service])
    unit_path = os.path.join(UNIT_DIR, service)
    if os.path.exists(unit_path):
        if os.geteuid() == 0:
            os.remove(unit_path)
        else:
            _sudo(["/bin/rm", "-f", unit_path])
    _sudo([SYSTEMCTL, "daemon-reload"])
    directory = _tunnel_dir(config, tunnel_id)
    if os.path.isdir(directory):
        shutil.rmtree(directory, ignore_errors=True)
    return {"ok": True, "output": f"تونل {tunnel_id} حذف شد."}


def rollback(config: AgentConfig, params: dict) -> dict:
    """بازگردانی آخرین پیکربندی پشتیبان‌گرفته‌شده و توقف سرویس ناقص."""
    tunnel_id = str(params.get("tunnel_id", ""))
    service = _service_name(params)
    _sudo([SYSTEMCTL, "stop", service])
    directory = _tunnel_dir(config, tunnel_id)
    parent = os.path.dirname(directory)
    backups = sorted(
        (name for name in os.listdir(parent) if name.startswith(f"{tunnel_id}.bak-")),
        reverse=True,
    ) if os.path.isdir(parent) else []
    if not backups:
        return {"ok": True, "output": "نسخه پشتیبانی برای بازگردانی وجود نداشت؛ سرویس متوقف شد."}
    latest = os.path.join(parent, backups[0])
    shutil.rmtree(directory, ignore_errors=True)
    shutil.copytree(latest, directory, dirs_exist_ok=True)
    _sudo([SYSTEMCTL, "start", service])
    return {"ok": True, "output": f"پیکربندی از {latest} بازگردانی شد."}


def status(config: AgentConfig, params: dict) -> dict:
    service = _service_name(params)
    code, _ = _run([SYSTEMCTL, "is-active", service])
    _, detail = _run([SYSTEMCTL, "show", service, "--property=ActiveState,SubState,ExecMainStartTimestamp"])
    running = code == 0
    return {
        "ok": True,
        "output": detail.strip(),
        "data": {"running": running, "health": "up" if running else "down"},
    }


def logs(config: AgentConfig, params: dict) -> dict:
    service = _service_name(params)
    lines = max(10, min(2000, int(params.get("lines", 200))))
    journalctl = shutil.which("journalctl") or "/bin/journalctl"
    _, output = _run([journalctl, "-u", service, "-n", str(lines), "--no-pager"])
    return {"ok": True, "output": output[-40000:]}


def _safe_health_command(command: str) -> list[str]:
    """دستور بررسی سلامت باید مسیر مطلق و قابل اجرا باشد؛ بدون shell اجرا می‌شود."""
    argv = shlex.split(command)
    if not argv:
        raise ActionError("دستور بررسی سلامت خالی است.")
    if not argv[0].startswith("/") or not os.access(argv[0], os.X_OK):
        raise ActionError("دستور بررسی سلامت باید مسیر مطلق یک فایل اجرایی باشد.")
    return argv


def health(config: AgentConfig, params: dict) -> dict:
    service = _service_name(params)
    code, _ = _run([SYSTEMCTL, "is-active", service])
    running = code == 0
    result = {"health": "up" if running else "down", "running": running}
    command = str(params.get("check_command") or "")
    if command:
        try:
            argv = _safe_health_command(command)
            check_code, output = _run(argv, timeout=20)
            result["check_output"] = output[-1000:]
            if check_code != 0:
                result["health"] = "degraded" if running else "down"
        except ActionError as exc:
            result["check_error"] = str(exc)
    probe_host = str(params.get("probe_host") or "")
    if probe_host and running:
        probe = metrics.latency_probe(probe_host, count=3)
        if probe.get("available"):
            result.update(
                {
                    "latency_ms": probe.get("latency_ms"),
                    "packet_loss": probe.get("packet_loss"),
                    "jitter_ms": probe.get("jitter_ms"),
                }
            )
            if (probe.get("packet_loss") or 0) > 20:
                result["health"] = "degraded"
    return {"ok": True, "data": result, "output": json.dumps(result, ensure_ascii=False)}


def tunnel_metrics(config: AgentConfig, params: dict) -> dict:
    """ترافیک سرویس تونل از cgroup/ss در صورت دسترس بودن."""
    service = _service_name(params)
    data: dict = {}
    _, output = _run([SYSTEMCTL, "show", service, "--property=MainPID"])
    pid = output.strip().split("=")[-1] if "=" in output else ""
    if pid.isdigit() and pid != "0":
        io_stat = f"/proc/{pid}/io"
        if os.path.exists(io_stat):
            for line in open(io_stat, encoding="utf-8"):
                key, _, value = line.partition(":")
                if key in ("read_bytes", "write_bytes") and value.strip().isdigit():
                    data[key] = int(value.strip())
        status_path = f"/proc/{pid}/status"
        if os.path.exists(status_path):
            for line in open(status_path, encoding="utf-8"):
                if line.startswith("VmRSS"):
                    data["rss_kb"] = int(line.split()[1])
    return {"ok": True, "data": data}


def update(config: AgentConfig, params: dict) -> dict:
    """به‌روزرسانی Binary تونل با نگه‌داشتن نسخه قبلی برای Rollback."""
    type_key = str(params.get("type_key", ""))
    if not SAFE_NAME.match(type_key or ""):
        raise ActionError("نوع تونل معتبر نیست.")
    destination = os.path.join(config.dirs["binaries"], type_key)
    if os.path.exists(destination):
        shutil.copy2(destination, f"{destination}.bak")
    binary = _install_from_source(config, type_key, params.get("source") or {})
    service = _service_name(params)
    _sudo([SYSTEMCTL, "restart", service])
    code, _ = _run([SYSTEMCTL, "is-active", service])
    if code != 0 and os.path.exists(f"{destination}.bak"):
        shutil.copy2(f"{destination}.bak", destination)
        _sudo([SYSTEMCTL, "restart", service])
        return {"ok": False, "error": "نسخه جدید بالا نیامد؛ به نسخه قبلی بازگردانده شد."}
    return {"ok": True, "output": f"تونل به‌روزرسانی شد: {binary}"}
