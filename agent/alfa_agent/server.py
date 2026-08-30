"""سرور HTTPS سبک Agent برای اجرای اکشن‌های پنل.

مسیرها:
    GET  /v1/health   → بررسی سلامت (بدون احراز هویت، فقط وضعیت ساده)
    POST /v1/actions  → اجرای اکشن allowlist‌شده (نیازمند توکن + امضا)
"""
from __future__ import annotations

import json
import logging
import ssl
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from alfa_agent import __version__
from alfa_agent.actions import ActionError
from alfa_agent.config import AgentConfig, State
from alfa_agent.handlers import dispatch
from alfa_agent.security import check_replay, rate_limit, verify_bearer, verify_signature

log = logging.getLogger("alfa-agent.server")
MAX_BODY = 4 * 1024 * 1024


class Handler(BaseHTTPRequestHandler):
    server_version = f"alfa-agent/{__version__}"
    config: AgentConfig
    state: State

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:  # لاگ ساخت‌یافته به جای stderr خام
        log.info("http %s", fmt % args)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/v1/health"):
            self._json(200, {"ok": True, "version": __version__, "registered": self.state.registered})
            return
        self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if not self.path.startswith("/v1/actions"):
            self._json(404, {"ok": False, "error": "not found"})
            return
        if not rate_limit():
            self._json(429, {"ok": False, "error": "تعداد درخواست‌ها بیش از حد مجاز است."})
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY:
            self._json(400, {"ok": False, "error": "بدنه درخواست معتبر نیست."})
            return
        raw = self.rfile.read(length).decode("utf-8", errors="replace")

        token = self.state.data.get("agent_token", "")
        secret = self.state.data.get("signing_secret", "")
        if not verify_bearer(self.headers.get("Authorization", ""), token):
            self._json(401, {"ok": False, "error": "توکن معتبر نیست."})
            return
        if not verify_signature(secret, raw, self.headers.get("X-Alfa-Signature", "")):
            self._json(401, {"ok": False, "error": "امضای درخواست معتبر نیست."})
            return
        try:
            payload = json.loads(raw)
        except ValueError:
            self._json(400, {"ok": False, "error": "JSON نامعتبر."})
            return

        ok, reason = check_replay(str(payload.get("request_id", "")), int(payload.get("ts", 0) or 0))
        if not ok:
            self._json(400, {"ok": False, "error": reason})
            return

        action = str(payload.get("action", ""))
        params = payload.get("params") or {}
        started = time.time()
        try:
            result = dispatch(self.config, action, params)
            result.setdefault("ok", True)
        except ActionError as exc:
            result = {"ok": False, "error": str(exc)}
        except Exception as exc:  # pragma: no cover
            log.exception("action_failed")
            result = {"ok": False, "error": f"خطای اجرای اکشن: {exc}"}
        result["action"] = action
        result["duration_ms"] = int((time.time() - started) * 1000)
        self._json(200, result)


def build_server(config: AgentConfig, state: State) -> ThreadingHTTPServer:
    Handler.config = config
    Handler.state = state
    httpd = ThreadingHTTPServer((config.listen_host, config.listen_port), Handler)
    if config.use_tls:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(certfile=config.tls_cert, keyfile=config.tls_key)
        httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    return httpd
