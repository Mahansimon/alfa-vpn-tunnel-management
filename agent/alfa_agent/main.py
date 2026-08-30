"""نقطه ورود Agent.

    python3 -m alfa_agent.main --register <TOKEN>   ثبت‌نام در پنل
    python3 -m alfa_agent.main --serve              اجرای سرویس (پیش‌فرض)
    python3 -m alfa_agent.main --selftest           بررسی پیش‌نیازها
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
import threading
import time

from alfa_agent import __version__
from alfa_agent.config import AgentConfig, State
from alfa_agent.handlers import selftest
from alfa_agent.server import build_server

log = logging.getLogger("alfa-agent")
_stop = threading.Event()


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


def heartbeat_loop(config: AgentConfig, state: State) -> None:
    """ارسال دوره‌ای Heartbeat + وضعیت تونل‌ها. در برابر خطای شبکه مقاوم است."""
    from alfa_agent import tunnels as tunnel_ops
    from alfa_agent.client import PanelClient

    client = PanelClient(config, state)
    interval = int(state.data.get("heartbeat_interval", config.heartbeat_interval))
    failures = 0
    while not _stop.is_set():
        statuses = []
        try:
            tunnels_root = config.dirs["tunnels"]
            if os.path.isdir(tunnels_root):
                for tunnel_id in os.listdir(tunnels_root):
                    if tunnel_id.endswith(".bak") or ".bak-" in tunnel_id:
                        continue
                    try:
                        health = tunnel_ops.health(config, {"tunnel_id": tunnel_id})
                        data = health.get("data", {})
                        statuses.append(
                            {
                                "tunnel_id": tunnel_id,
                                "running": bool(data.get("running")),
                                "health": data.get("health", "unknown"),
                                "latency_ms": data.get("latency_ms"),
                                "packet_loss": data.get("packet_loss"),
                                "jitter_ms": data.get("jitter_ms"),
                                "detail": (data.get("check_output") or "")[:300],
                            }
                        )
                    except Exception as exc:
                        log.debug("tunnel status failed for %s: %s", tunnel_id, exc)
            response = client.heartbeat(statuses)
            interval = int(response.get("heartbeat_interval", interval) or interval)
            failures = 0
        except Exception as exc:
            failures += 1
            wait = min(120, interval * min(failures, 6))
            log.warning("heartbeat failed (%s). retry in %ss", exc, wait)
            _stop.wait(wait)
            continue
        _stop.wait(interval)


def do_register(config: AgentConfig, state: State, token: str) -> int:
    from alfa_agent.client import PanelClient

    if not config.panel_url:
        print("خطا: آدرس پنل (PANEL_URL) تنظیم نشده است.", file=sys.stderr)
        return 2
    client = PanelClient(config, state)
    try:
        data = client.register(token)
    except Exception as exc:
        print(f"ثبت‌نام ناموفق بود: {exc}", file=sys.stderr)
        return 1
    print(f"ثبت‌نام موفق. server_id={data['server_id']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Alfa Agent")
    parser.add_argument("--register", metavar="TOKEN", help="ثبت‌نام با توکن نصب")
    parser.add_argument("--serve", action="store_true", help="اجرای سرویس Agent")
    parser.add_argument("--selftest", action="store_true", help="بررسی پیش‌نیازها")
    parser.add_argument("--version", action="store_true", help="نمایش نسخه")
    args = parser.parse_args(argv)

    config = AgentConfig.load()
    configure_logging(config.log_level)
    state = State()

    if args.version:
        print(__version__)
        return 0
    if args.selftest:
        print(json.dumps(selftest(config), ensure_ascii=False, indent=2))
        return 0
    if args.register:
        return do_register(config, state, args.register)

    if not state.registered:
        log.error("Agent ثبت نشده است. ابتدا با --register <TOKEN> ثبت‌نام کنید.")
        return 3

    def _shutdown(*_args):
        log.info("shutting down")
        _stop.set()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    thread = threading.Thread(target=heartbeat_loop, args=(config, state), daemon=True)
    thread.start()

    httpd = build_server(config, state)
    log.info(
        "agent %s listening on %s:%s (tls=%s)",
        __version__,
        config.listen_host,
        config.listen_port,
        config.use_tls,
    )
    server_thread = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 1}, daemon=True)
    server_thread.start()
    try:
        while not _stop.is_set():
            time.sleep(1)
    finally:
        httpd.shutdown()
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
