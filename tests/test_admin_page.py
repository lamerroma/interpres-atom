import re
import unittest

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


if __name__ == "__main__":
    unittest.main()
