import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pricemonitor.config import Settings, load_products
from pricemonitor.exceptions import ConfigError


class SettingsTests(unittest.TestCase):
    def test_defaults_when_env_is_empty(self) -> None:
        settings = Settings.from_env({})
        self.assertTrue(settings.headless)
        self.assertEqual(settings.timeout_ms, 15000)
        self.assertEqual(settings.max_retries, 3)
        self.assertFalse(settings.email_enabled)

    def test_values_are_read_and_converted(self) -> None:
        settings = Settings.from_env(
            {
                "HEADLESS": "false",
                "TIMEOUT_MS": "5000",
                "MAX_RETRIES": "5",
                "CHROMIUM_ARGS": "--no-sandbox --disable-gpu",
                "SMTP_HOST": "smtp.example.com",
                "SMTP_USER": "me@example.com",
                "SMTP_PASSWORD": "secret",
                "ALERT_EMAIL_TO": "you@example.com",
            }
        )
        self.assertFalse(settings.headless)
        self.assertEqual(settings.timeout_ms, 5000)
        self.assertEqual(settings.max_retries, 5)
        self.assertEqual(settings.chromium_args, ("--no-sandbox", "--disable-gpu"))
        self.assertTrue(settings.email_enabled)

    def test_invalid_values_raise(self) -> None:
        for env in (
            {"HEADLESS": "maybe"},
            {"TIMEOUT_MS": "fast"},
            {"MAX_RETRIES": "0"},
        ):
            with self.subTest(env=env):
                with self.assertRaises(ConfigError):
                    Settings.from_env(env)


class EnvFileTests(unittest.TestCase):
    def test_env_file_in_current_folder_is_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, ".env").write_text("TIMEOUT_MS=4321\nMAX_RETRIES=7\n", encoding="utf-8")
            previous = Path.cwd()
            clean_env = {k: v for k, v in os.environ.items() if k not in ("TIMEOUT_MS", "MAX_RETRIES")}
            try:
                os.chdir(tmp)
                with mock.patch.dict(os.environ, clean_env, clear=True):
                    settings = Settings.from_env()
            finally:
                os.chdir(previous)
        self.assertEqual(settings.timeout_ms, 4321)
        self.assertEqual(settings.max_retries, 7)


class LoadProductsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "products.json"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write(self, data) -> None:
        self.path.write_text(json.dumps(data), encoding="utf-8")

    def test_valid_file(self) -> None:
        self.write(
            [{"name": "Book", "url": "https://x.test/a", "price_selector": ".p", "target_price": 10}]
        )
        products = load_products(self.path)
        self.assertEqual(products[0].name, "Book")
        self.assertEqual(products[0].target_price, 10.0)

    def test_target_price_is_optional(self) -> None:
        self.write([{"name": "Book", "url": "https://x.test/a", "price_selector": ".p"}])
        self.assertIsNone(load_products(self.path)[0].target_price)

    def test_missing_file_raises(self) -> None:
        with self.assertRaises(ConfigError):
            load_products(self.path)

    def test_invalid_json_raises(self) -> None:
        self.path.write_text("{not json", encoding="utf-8")
        with self.assertRaises(ConfigError):
            load_products(self.path)

    def test_bad_entries_raise(self) -> None:
        bad_files = [
            [],
            {"name": "not a list"},
            [{"url": "https://x.test", "price_selector": ".p"}],
            [{"name": "A", "url": "ftp://x.test", "price_selector": ".p"}],
            [{"name": "A", "url": "https://x.test", "price_selector": ".p", "target_price": "cheap"}],
            [{"name": "A", "url": "https://x.test", "price_selector": ".p", "target_price": -5}],
        ]
        for data in bad_files:
            with self.subTest(data=data):
                self.write(data)
                with self.assertRaises(ConfigError):
                    load_products(self.path)


if __name__ == "__main__":
    unittest.main()
