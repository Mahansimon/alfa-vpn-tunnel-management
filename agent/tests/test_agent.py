"""تست‌های Agent (بدون وابستگی خارجی: با unittest اجرا می‌شوند).

    cd agent && python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alfa_agent import metrics, security  # noqa: E402
from alfa_agent.actions import ActionError, _service_name, _tunnel_dir, capabilities  # noqa: E402
from alfa_agent.config import AgentConfig, State  # noqa: E402
from alfa_agent.handlers import ACTIONS, dispatch  # noqa: E402


class TestMetrics(unittest.TestCase):
    def test_collect_returns_expected_keys(self):
        payload = metrics.collect()
        for key in ("cpu_percent", "ram_total", "ram_used", "disk_total", "net_rx_bytes", "uptime_seconds"):
            self.assertIn(key, payload)
        self.assertGreaterEqual(payload["ram_total"], 0)

    def test_cpu_percent_is_bounded(self):
        metrics.cpu_percent()
        value = metrics.cpu_percent()
        self.assertGreaterEqual(value, 0.0)
        self.assertLessEqual(value, 100.0)

    def test_arch_normalisation(self):
        self.assertEqual(metrics.normalize_arch("x86_64"), "amd64")
        self.assertEqual(metrics.normalize_arch("aarch64"), "arm64")
        self.assertEqual(metrics.normalize_arch("AMD64"), "amd64")

    def test_system_info(self):
        info = metrics.system_info("1.0.0", capabilities())
        self.assertEqual(info["agent_version"], "1.0.0")
        self.assertTrue(info["hostname"])


class TestSecurity(unittest.TestCase):
    def test_bearer(self):
        self.assertTrue(security.verify_bearer("Bearer abc123", "abc123"))
        self.assertFalse(security.verify_bearer("Bearer abc123", "other"))
        self.assertFalse(security.verify_bearer("abc123", "abc123"))

    def test_signature(self):
        signature = security.sign("secret", "body")
        self.assertTrue(security.verify_signature("secret", "body", signature))
        self.assertFalse(security.verify_signature("secret", "tampered", signature))

    def test_replay_protection(self):
        import time

        now = int(time.time())
        ok, _ = security.check_replay("req-1", now)
        self.assertTrue(ok)
        again, reason = security.check_replay("req-1", now)
        self.assertFalse(again)
        self.assertIn("قبلاً", reason)
        stale, reason2 = security.check_replay("req-2", now - 10_000)
        self.assertFalse(stale)


class TestActionSafety(unittest.TestCase):
    def test_only_alfa_services_allowed(self):
        self.assertEqual(_service_name({"service": "alfa-tunnel-abc"}), "alfa-tunnel-abc.service")
        with self.assertRaises(ActionError):
            _service_name({"service": "sshd"})
        with self.assertRaises(ActionError):
            _service_name({"service": "alfa-tunnel-a; rm -rf /"})

    def test_path_traversal_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = AgentConfig()
            config.dirs = dict(config.dirs, tunnels=tmp)
            self.assertTrue(_tunnel_dir(config, "abc123").startswith(os.path.realpath(tmp)))
            with self.assertRaises(ActionError):
                _tunnel_dir(config, "../../etc")

    def test_no_arbitrary_command_action(self):
        forbidden = {"exec", "shell", "bash", "run", "command", "eval"}
        self.assertFalse(forbidden & set(ACTIONS))

    def test_unknown_action_rejected(self):
        with self.assertRaises(ActionError):
            dispatch(AgentConfig(), "definitely_not_allowed", {})

    def test_ping_action(self):
        result = dispatch(AgentConfig(), "ping", {})
        self.assertTrue(result["ok"])
        self.assertEqual(result["output"], "pong")


class TestState(unittest.TestCase):
    def test_state_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "state.json")
            state = State(path)
            self.assertFalse(state.registered)
            state.set_credentials("srv1", "token1", "secret1")
            self.assertTrue(State(path).registered)
            self.assertEqual(State(path).data["server_id"], "srv1")
            self.assertEqual(oct(os.stat(path).st_mode)[-3:], "600")


if __name__ == "__main__":
    unittest.main()
