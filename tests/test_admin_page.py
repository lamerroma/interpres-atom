import re
import asyncio
import io
import json
import os
import tempfile
import threading
import time
import unittest
import subprocess
import zipfile
from unittest.mock import Mock, patch

from fastapi import Request, UploadFile
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
        "max_upload_mb": 50,
        "temperature": 0.7,
        "retry": 2,
        "insert_mode": "replace",
        "separator": "\n",
        "custom_prompt": "",
    }
    values.update(overrides)
    return values


class AdminPageTests(unittest.TestCase):
    def test_file_translation_uses_queue_and_cached_download(self):
        request = Request({
            "type": "http",
            "client": ("203.0.113.7", 4321),
            "headers": [],
        })
        upload = UploadFile(
            file=io.BytesIO(b"Hello"),
            filename="sample.txt",
        )
        with (
            patch.object(server, "_translate_unit", return_value="Переклад"),
            patch.object(server, "log_stat"),
        ):
            response = asyncio.run(server.translate_file_endpoint(
                request,
                upload,
                lang_from="English",
                lang_to="Ukrainian",
            ))

            async def collect_body():
                return b"".join([
                    chunk.encode("utf-8") if isinstance(chunk, str) else chunk
                    async for chunk in response.body_iterator
                ])

            body = asyncio.run(collect_body()).decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers.get("X-Request-ID"))
        events = [
            json.loads(line[6:])
            for line in body.splitlines()
            if line.startswith("data: ")
        ]
        self.assertTrue(any(event.get("type") == "queue" for event in events))
        download = next(event for event in events if event.get("type") == "download")
        downloaded = server.download_file(download["url"].rsplit("/", 1)[-1])
        self.assertEqual(downloaded.status_code, 200)
        self.assertEqual(downloaded.body, "Переклад".encode("utf-8"))

    def test_queue_watchdog_releases_stalled_job(self):
        request_id = str(time.time_ns())
        job = server._ActiveJob(
            threading.Event(), threading.Event(), threading.Event()
        )
        with (
            patch.object(server, "_job_stall_timeout", return_value=0),
            patch.object(server.log, "error"),
        ):
            self.assertIsNotNone(server._enqueue_job(request_id, job))
            self.assertTrue(job.start_event.wait(1))
            self.assertTrue(job.done_event.wait(2))

        self.assertTrue(job.stop_event.is_set())
        self.assertIsNone(server._get_job(request_id))

    def test_preview_html_removes_scripts_and_javascript_links(self):
        unsafe = (
            '<script>alert(1)</script>'
            '<a href="javascript:alert(document.domain)">click</a>'
        )

        safe = server._sanitize_preview_html(unsafe)

        self.assertNotIn("<script", safe)
        self.assertNotIn("javascript:", safe)
        self.assertIn("<a>click</a>", safe)
        self.assertNotIn("allow-scripts", server.USER_HTML)
        self.assertIn("DOMPurify.sanitize(marked.parse(text))", server.USER_HTML)
        self.assertIn("resultEl.textContent = text", server.USER_HTML)

    def test_office_archive_rejects_large_uncompressed_content(self):
        content = io.BytesIO()
        with zipfile.ZipFile(content, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("word/document.xml", b"12345")

        with patch.object(server, "_MAX_OFFICE_UNCOMPRESSED_BYTES", 4):
            error = server._validate_office_archive(content.getvalue())

        self.assertIn("після розпакування", error)

    def test_result_cache_expires_and_evicts_oldest_entries(self):
        with server._result_cache_lock:
            original = server._result_cache.copy()
            server._result_cache.clear()
        try:
            with (
                patch.object(server, "_RESULT_MAX_ITEMS", 2),
                patch.object(server, "_RESULT_MAX_BYTES", 100),
                patch.object(server, "_RESULT_TTL_SECONDS", 10),
            ):
                self.assertTrue(server._cache_result("one", "1.txt", b"1", "text/plain"))
                self.assertTrue(server._cache_result("two", "2.txt", b"2", "text/plain"))
                self.assertTrue(server._cache_result("three", "3.txt", b"3", "text/plain"))
                self.assertIsNone(server._get_cached_result("one"))

                with server._result_cache_lock:
                    server._result_cache["two"].created_at = time.time() - 11
                self.assertIsNone(server._get_cached_result("two"))
                self.assertIsNotNone(server._get_cached_result("three"))
        finally:
            with server._result_cache_lock:
                server._result_cache.clear()
                server._result_cache.update(original)

    def test_cancelled_queued_job_releases_queue_slot(self):
        job = server._ActiveJob(
            threading.Event(), threading.Event(), threading.Event()
        )

        self.assertTrue(job.cancel())
        self.assertTrue(job.stop_event.is_set())
        self.assertTrue(job.done_event.is_set())
        self.assertFalse(job.begin_execution())

    def test_cancelled_running_job_waits_for_generator_cleanup(self):
        job = server._ActiveJob(
            threading.Event(), threading.Event(), threading.Event()
        )

        self.assertTrue(job.begin_execution())
        self.assertFalse(job.cancel())
        self.assertTrue(job.stop_event.is_set())
        self.assertFalse(job.done_event.is_set())

    def test_cancelled_streaming_job_closes_backend_and_releases_queue(self):
        job = server._ActiveJob(
            threading.Event(), threading.Event(), threading.Event()
        )
        response = Mock()

        self.assertTrue(job.begin_execution())
        self.assertTrue(job.attach_backend_response(response))
        self.assertTrue(job.cancel())

        response.close.assert_called_once_with()
        self.assertTrue(job.stop_event.is_set())
        self.assertTrue(job.done_event.is_set())

    def test_backend_response_is_closed_if_stop_won_the_race(self):
        job = server._ActiveJob(
            threading.Event(), threading.Event(), threading.Event()
        )
        response = Mock()
        job.stop_event.set()

        self.assertFalse(job.attach_backend_response(response))
        response.close.assert_called_once_with()

    def test_text_stop_reaches_server_before_stream_is_aborted(self):
        self.assertIn("resp.headers.get('X-Request-ID')", server.USER_HTML)
        self.assertIn("if (_textController === controller)", server.USER_HTML)
        stop_function = server.USER_HTML.split(
            "async function doStop() {", 1
        )[1].split("//", 1)[0]
        self.assertLess(
            stop_function.index("fetch('/stop/'"),
            stop_function.index("controller.abort()"),
        )

    def test_file_stop_reaches_server_before_stream_is_aborted(self):
        self.assertIn("resp.headers.get('X-Request-ID')", server.USER_HTML)
        self.assertIn("if (_fileController === controller)", server.USER_HTML)
        stop_function = server.USER_HTML.split(
            "async function doFileStop() {", 1
        )[1].split("//", 1)[0]
        self.assertLess(
            stop_function.index("fetch('/stop/'"),
            stop_function.index("controller.abort()"),
        )


    def test_translation_defaults_use_primary_model_settings(self):
        self.assertEqual(server.DEFAULTS["model"], "rinex20/translategemma3:12b")
        self.assertEqual(server.DEFAULTS["max_tokens"], 4096)
        self.assertEqual(server.DEFAULTS["temperature"], 0.1)
        self.assertEqual(server.DEFAULTS["max_upload_mb"], 50)
        self.assertIn("cfg.max_tokens    ?? 4096", server.ADMIN_HTML)
        self.assertIn("cfg.temperature   ?? 0.1", server.ADMIN_HTML)

    def test_packaged_config_uses_local_primary_model(self):
        config_path = os.path.join(os.path.dirname(server.__file__), "translator_config.json")
        with open(config_path, encoding="utf-8") as config_file:
            config = json.load(config_file)

        self.assertEqual(config["base_url"], "http://127.0.0.1:11434/v1")
        self.assertEqual(config["model"], "rinex20/translategemma3:12b")
        self.assertEqual(config["max_tokens"], 4096)

    def test_user_page_uses_only_local_javascript(self):
        self.assertIn('src="/static/vendor/marked.min.js"', server.USER_HTML)
        self.assertIn('src="/static/vendor/purify.min.js"', server.USER_HTML)
        self.assertNotIn("cdn.jsdelivr.net", server.USER_HTML)
        self.assertNotRegex(server.USER_HTML, r'<script[^>]+src="https?://')

        static_dir = os.path.join(os.path.dirname(server.__file__), "static", "vendor")
        self.assertTrue(os.path.isfile(os.path.join(static_dir, "marked.min.js")))
        self.assertTrue(os.path.isfile(os.path.join(static_dir, "purify.min.js")))

    def test_user_page_shows_simple_server_status(self):
        self.assertIn("Сервер працює", server.USER_HTML)
        self.assertIn("Сервер недоступний", server.USER_HTML)
        self.assertNotIn("мовна модель", server.USER_HTML)
        self.assertNotIn("Ollama підключена", server.USER_HTML)
        self.assertIn("system-model", server.ADMIN_HTML)

    def test_text_workspace_fits_viewport_and_scrolls_editors(self):
        self.assertIn("body { height: 100vh", server.USER_HTML)
        self.assertIn("overflow: hidden; flex: 1 1 auto", server.USER_HTML)
        self.assertIn("#panel-text.active { overflow: hidden; }", server.USER_HTML)
        self.assertIn("overflow-y: auto;", server.USER_HTML)

    def test_text_editors_share_height_and_have_clipboard_actions(self):
        self.assertIn("grid-template-rows: minmax(0, 1fr) auto", server.USER_HTML)
        self.assertIn('class="actions text-actions"', server.USER_HTML)
        self.assertIn("async function pasteInput()", server.USER_HTML)
        self.assertIn("async function copyResult()", server.USER_HTML)
        self.assertIn('aria-label="Вставити з буфера"', server.USER_HTML)
        self.assertIn('aria-label="Копіювати переклад"', server.USER_HTML)

    def test_valid_config_is_accepted(self):
        config = server.ConfigUpdate(**valid_config())
        self.assertEqual(config.chunk_size, 3000)

    def test_invalid_numeric_config_is_rejected(self):
        for field, value in (
            ("chunk_size", 0),
            ("retry", None),
            ("temperature", 3),
            ("max_pdf_pages", 0),
            ("max_upload_mb", 0),
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
            "cfg_max_upload_mb",
            "cfg_temperature", "cfg_retry",
        ):
            pattern = rf'<input[^>]*id="{element_id}"[^>]*required'
            self.assertRegex(server.ADMIN_HTML, pattern)

    def test_upload_reader_stops_at_configured_limit(self):
        accepted = UploadFile(file=io.BytesIO(b"1234"), filename="small.txt")
        rejected = UploadFile(file=io.BytesIO(b"12345"), filename="large.txt")

        self.assertEqual(
            asyncio.run(server._read_upload_limited(accepted, 4)),
            b"1234",
        )
        self.assertIsNone(
            asyncio.run(server._read_upload_limited(rejected, 4)),
        )

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
            self.assertEqual(count, 2)
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
            second = server.heartbeat({"sid": "second-tab"}, request)
            self.assertEqual(json.loads(second.body)["online"], 1)
            invalid = server.heartbeat({"sid": []}, request)
            self.assertEqual(invalid.status_code, 400)
        finally:
            with server._sessions_lock:
                server._sessions.clear()
                server._sessions.update(original)

    def test_multiple_tabs_from_same_ip_count_as_one_user(self):
        now = time.time()
        with server._sessions_lock:
            original = dict(server._sessions)
            server._sessions.clear()
            server._sessions.update({
                "tab-1": (now, "203.0.113.7"),
                "tab-2": (now, "203.0.113.7"),
            })
        try:
            self.assertEqual(server._online_session_count(now), 1)
            count, clients = server._online_sessions_snapshot(now)
            self.assertEqual(count, 1)
            self.assertEqual(clients[0]["sessions"], 2)
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
