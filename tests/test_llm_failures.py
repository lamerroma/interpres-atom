import json
import io
import threading
import unittest
from unittest.mock import patch

import translate_server as server


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text="", lines=None):
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self._lines = lines or []
        self.closed = False

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    def iter_lines(self):
        yield from self._lines

    def close(self):
        self.closed = True


class LlmFailureTests(unittest.TestCase):
    def setUp(self):
        self.original_cfg = dict(server.CFG)
        server.CFG.update({
            "base_url": "http://ollama.test/v1",
            "model": "test-model",
            "llm_timeout": 1,
            "retry": 2,
            "temperature": 0,
            "max_tokens": 4096,
        })
        self.stop_event = threading.Event()

    def tearDown(self):
        server.CFG.clear()
        server.CFG.update(self.original_cfg)

    @patch.object(server.req_lib, "post")
    def test_unit_returns_valid_translation(self, post):
        post.return_value = FakeResponse(
            payload={"message": {"content": "Переклад"}}
        )

        result = server._translate_unit(
            "Original", "English", "Ukrainian", self.stop_event
        )

        self.assertEqual(result, "Переклад")
        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args.kwargs["json"]["options"], {
            "temperature": 0.0,
            "num_predict": 4096,
        })

    @patch.object(server.req_lib, "post")
    def test_unit_http_failure_retries_then_raises(self, post):
        post.return_value = FakeResponse(status_code=500, text="backend failed")

        with self.assertRaisesRegex(server.TranslationError, "HTTP 500"):
            server._translate_unit(
                "Original", "English", "Ukrainian", self.stop_event
            )

        self.assertEqual(post.call_count, 2)

    @patch.object(server.req_lib, "post")
    def test_unit_empty_response_is_not_reported_as_success(self, post):
        post.return_value = FakeResponse(payload={"message": {"content": "  "}})

        with self.assertRaisesRegex(server.TranslationError, "порожню відповідь"):
            server._translate_unit(
                "Original", "English", "Ukrainian", self.stop_event
            )

    @patch.object(server.req_lib, "post")
    def test_json_batch_returns_complete_translation(self, post):
        post.return_value = FakeResponse(payload={
            "message": {"content": json.dumps({"0": "Один", "1": "Два"})},
            "prompt_eval_count": 10,
            "eval_count": 5,
        })
        token_stats = {}

        result = server._translate_json_segments(
            {"0": "One", "1": "Two"}, "Ukrainian", self.stop_event,
            token_stats=token_stats,
        )

        self.assertEqual(result, {"0": "Один", "1": "Два"})
        self.assertEqual(token_stats, {"tok_in": 10, "tok_out": 5})
        self.assertEqual(post.call_args.kwargs["json"]["options"], {
            "temperature": 0.0,
            "num_predict": 4096,
        })

    @patch.object(server.req_lib, "post")
    def test_json_batch_missing_key_retries_then_raises(self, post):
        post.return_value = FakeResponse(payload={
            "message": {"content": json.dumps({"0": "Один"})}
        })

        with self.assertRaisesRegex(server.TranslationError, "коректний JSON"):
            server._translate_json_segments(
                {"0": "One", "1": "Two"}, "Ukrainian", self.stop_event
            )

        self.assertEqual(post.call_count, 2)

    @patch.object(server.req_lib, "post")
    def test_json_batch_malformed_response_retries_then_raises(self, post):
        post.return_value = FakeResponse(payload={
            "message": {"content": "not-json"}
        })

        with self.assertRaises(server.TranslationError):
            server._translate_json_segments(
                {"0": "One"}, "Ukrainian", self.stop_event
            )

        self.assertEqual(post.call_count, 2)

    @patch.object(server.req_lib, "post")
    def test_stream_failure_does_not_yield_original_text(self, post):
        post.return_value = FakeResponse(status_code=503)

        with self.assertRaisesRegex(server.TranslationError, "HTTP 503"):
            list(server._translate_unit_streaming(
                "Original", "English", "Ukrainian", self.stop_event
            ))

        self.assertEqual(post.call_count, 2)

    @patch.object(server.req_lib, "post")
    def test_incomplete_stream_raises_instead_of_reporting_partial_success(self, post):
        post.return_value = FakeResponse(lines=[
            json.dumps({"message": {"content": "Частина"}, "done": False}).encode()
        ])

        stream = server._translate_unit_streaming(
            "Original", "English", "Ukrainian", self.stop_event
        )
        self.assertEqual(next(stream), "Частина")
        with self.assertRaisesRegex(server.TranslationError, "обірвався"):
            next(stream)

        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args.kwargs["json"]["options"], {
            "temperature": 0.0,
            "num_predict": 4096,
        })

    def test_docx_backend_failure_does_not_create_download(self):
        from docx import Document

        document = Document()
        document.add_paragraph("Text to translate")
        content = io.BytesIO()
        document.save(content)

        with patch.object(
            server,
            "_translate_json_segments",
            side_effect=server.TranslationError("Ollama unavailable"),
        ):
            events = list(server.translate_docx_bytes(
                content.getvalue(), "sample", "English", "Ukrainian",
                self.stop_event,
            ))

        self.assertTrue(any(event[0] == "error" for event in events))
        self.assertFalse(any(event[0] == "done" for event in events))

    def test_version_is_rendered_on_user_and_admin_pages(self):
        version_label = f"Interpres-Atom v{server.APP_VERSION}"
        self.assertIn(version_label, server.USER_HTML)
        self.assertIn(version_label, server.ADMIN_HTML)
        self.assertNotIn("__APP_VERSION__", server.USER_HTML)
        self.assertNotIn("__APP_VERSION__", server.ADMIN_HTML)


if __name__ == "__main__":
    unittest.main()
