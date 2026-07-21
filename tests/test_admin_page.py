import re
import json
import os
import tempfile
import time
import unittest
import subprocess
from unittest.mock import Mock, patch

from fastapi import Request
from pydantic import ValidationError

import translate_server as server


def valid_config(**overrides):
    values = {
        "base_url": "http://127.0.0.1:11434/v1",
        "model": "test-model",
        "max_tokens": 2048,
        "llm_timeout": 180,
        "chunk_size": 3000,
        "max_pdf_pages": 10,
        "max_chars": 30000,
        "temperature": 0.7,
        "retry": 2,
        "insert_mode": "replace",
        "separator": "\n",
        "custom_prompt": "",
    }
    values.update(overrides)
    return values


class AdminPageTests(unittest.TestCase):
    def test_translation_defaults_use_primary_model_settings(self):
        self.assertEqual(server.DEFAULTS["model"], "rinex20/translategemma3:12b")
        self.assertEqual(server.DEFAULTS["max_tokens"], 4096)
        self.assertEqual(server.DEFAULTS["temperature"], 0.1)
        self.assertIn("cfg.max_tokens    ?? 4096", server.ADMIN_HTML)
        self.assertIn("cfg.temperature   ?? 0.1", server.ADMIN_HTML)

    def test_valid_config_is_accepted(self):
        config = server.ConfigUpdate(**valid_config())
        self.assertEqual(config.chunk_size, 3000)

    def test_invalid_numeric_config_is_rejected(self):
        for field, value in (
            ("chunk_size", 0),
            ("retry", None),
            ("temperature", 3),
            ("max_pdf_pages", 0),
        ):
            with self.subTest(field=field, value=value):
                with self.assertRaises(ValidationError):
                    server.ConfigUpdate(**valid_config(**{field: value}))

    def test_invalid_insert_mode_is_rejected(self):
        with self.assertRaises(ValidationError):
            server.ConfigUpdate(**valid_config(insert_mode="invalid"))

    def test_admin_dom_references_existing_ids(self):
        element_ids = set(re.findall(r'id="([^"]+)"', server.ADMIN_HTML))
        referenced_ids = set(re.findall(
            r"getElementById\('([^']+)'\)", server.ADMIN_HTML
        ))
        self.assertFalse(referenced_ids - element_ids)

    def test_stats_values_are_html_escaped(self):
        self.assertIn("${escapeHtml(r.filename)}", server.ADMIN_HTML)
        self.assertIn("${escapeHtml(r.error)}", server.ADMIN_HTML)
        self.assertNotIn("${r.filename||''}", server.ADMIN_HTML)
        self.assertNotIn(">${r.error||''}</td>", server.ADMIN_HTML)

    def test_required_settings_fields_are_marked_required(self):
        for element_id in (
            "cfg_base_url", "cfg_model", "cfg_max_tokens", "cfg_llm_timeout",
            "cfg_chunk_size", "cfg_max_pdf_pages", "cfg_max_chars",
            "cfg_temperature", "cfg_retry",
        ):
            pattern = rf'<input[^>]*id="{element_id}"[^>]*required'
            self.assertRegex(server.ADMIN_HTML, pattern)

    @patch.object(server.req_lib, "get")
    def test_admin_status_reports_ollama_and_model(self, get):
        response = Mock(status_code=200)
        response.json.return_value = {
            "models": [{"name": server.CFG.get("model", "")}]
        }
        get.return_value = response

        payload = json.loads(server.admin_status().body)

        self.assertTrue(payload["ollama_ok"])
        self.assertTrue(payload["model_available"])
        self.assertEqual(payload["version"], server.APP_VERSION)
        self.assertIn("online_clients", payload)
        self.assertIn("gpu", payload)
        self.assertIn("active_jobs", payload)
        self.assertIn("queued_jobs", payload)

    @patch.object(server.req_lib, "get", side_effect=OSError("offline"))
    def test_admin_status_reports_offline_ollama(self, _get):
        payload = json.loads(server.admin_status().body)

        self.assertFalse(payload["ollama_ok"])
        self.assertFalse(payload["model_available"])
        self.assertIn("offline", payload["ollama_error"])

    def test_online_count_removes_stale_sessions(self):
        now = time.time()
        with server._sessions_lock:
            original = dict(server._sessions)
            server._sessions.clear()
            server._sessions.update({
                "current": (now, "192.0.2.10"),
                "stale": (now - 100, "192.0.2.20"),
            })
        try:
            self.assertEqual(server._online_session_count(now), 1)
            with server._sessions_lock:
                self.assertNotIn("stale", server._sessions)
        finally:
            with server._sessions_lock:
                server._sessions.clear()
                server._sessions.update(original)

    def test_online_clients_are_grouped_by_ip(self):
        now = time.time()
        with server._sessions_lock:
            original = dict(server._sessions)
            server._sessions.clear()
            server._sessions.update({
                "tab-1": (now - 2, "192.0.2.10"),
                "tab-2": (now - 4, "192.0.2.10"),
                "tab-3": (now - 1, "198.51.100.5"),
            })
        try:
            count, clients = server._online_sessions_snapshot(now)
            self.assertEqual(count, 3)
            self.assertEqual(clients, [
                {"ip": "192.0.2.10", "sessions": 2, "last_seen_seconds": 2},
                {"ip": "198.51.100.5", "sessions": 1, "last_seen_seconds": 1},
            ])
        finally:
            with server._sessions_lock:
                server._sessions.clear()
                server._sessions.update(original)

    def test_heartbeat_records_client_ip_and_rejects_invalid_sid(self):
        request = Request({
            "type": "http",
            "client": ("203.0.113.7", 4321),
            "headers": [],
        })
        with server._sessions_lock:
            original = dict(server._sessions)
            server._sessions.clear()
        try:
            response = server.heartbeat({"sid": "test-session"}, request)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                server._online_sessions_snapshot()[1][0]["ip"],
                "203.0.113.7",
            )
            invalid = server.heartbeat({"sid": []}, request)
            self.assertEqual(invalid.status_code, 400)
        finally:
            with server._sessions_lock:
                server._sessions.clear()
                server._sessions.update(original)

    @patch.object(server.subprocess, "run")
    def test_gpu_status_parses_nvidia_smi_output(self, run):
        run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="0, NVIDIA RTX 4090, 72, 10240, 24564, 61, 318.5\n",
            stderr="",
        )

        status = server._gpu_status()

        self.assertTrue(status["available"])
        self.assertEqual(status["gpus"][0]["utilization_percent"], 72.0)
        self.assertEqual(status["gpus"][0]["memory_used_mib"], 10240.0)

    @patch.object(server.subprocess, "run", side_effect=FileNotFoundError())
    def test_gpu_status_is_optional(self, _run):
        self.assertFalse(server._gpu_status()["available"])

    def test_gpu_history_is_stored_in_stats_database(self):
        status = {
            "available": True,
            "gpus": [{
                "index": 0,
                "name": "Test GPU",
                "utilization_percent": 42.0,
                "memory_used_mib": 4096.0,
                "memory_total_mib": 8192.0,
                "temperature_c": 55.0,
                "power_w": 120.0,
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            database = os.path.join(directory, "stats.db")
            with patch.object(server, "STATS_DB", database):
                server.init_stats_db()
                server._store_gpu_metrics(status)
                history = server.get_gpu_history(1)

        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["utilization_percent"], 42.0)
        self.assertEqual(history[0]["name"], "Test GPU")

    def test_admin_contains_status_filters_and_dirty_state(self):
        for element_id in (
            "system-ollama", "system-model", "system-jobs", "system-users",
            "system-version", "system-gpu", "system-user-ips",
            "gpu-history-chart", "gpu-history-device", "gpu-history-range",
            "gpu-chart-axis-label", "gpu-chart-latest",
            "stats-filter-kind", "stats-filter-status",
            "stats-filter-search", "settings-dirty-badge",
        ):
            self.assertIn(f'id="{element_id}"', server.ADMIN_HTML)
        self.assertIn("function refreshSystemStatus", server.ADMIN_HTML)
        self.assertIn("function drawGpuHistory", server.ADMIN_HTML)
        self.assertIn("function setGpuHistoryMetric", server.ADMIN_HTML)
        for metric in ("utilization", "memory", "temperature", "power"):
            self.assertIn(f'data-metric="{metric}"', server.ADMIN_HTML)
        self.assertIn("function renderStatsRows", server.ADMIN_HTML)
        self.assertIn("beforeunload", server.ADMIN_HTML)


if __name__ == "__main__":
    unittest.main()
