"""Integration tests that drive a real Chromium browser against local pages.

Set PW_CHROMIUM_PATH to use a specific Chromium binary. If no browser can be
started, these tests are skipped instead of failing.
"""

import functools
import http.server
import os
import socket
import tempfile
import threading
import unittest
from pathlib import Path

from pricemonitor.config import Settings
from pricemonitor.exceptions import ScrapeError
from pricemonitor.models import Product
from pricemonitor.scraper import PriceScraper

FIXTURES = Path(__file__).parent / "fixtures"


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args) -> None:
        return None


class ScraperIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        handler = functools.partial(QuietHandler, directory=str(FIXTURES))
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.base_url = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

        cls._tmp = tempfile.TemporaryDirectory()
        cls.settings = Settings(
            headless=True,
            timeout_ms=4000,
            max_retries=2,
            retry_delay_s=0,
            screenshot_dir=Path(cls._tmp.name) / "shots",
            chromium_path=os.environ.get("PW_CHROMIUM_PATH") or None,
            chromium_args=("--no-sandbox",),
        )
        try:
            with PriceScraper(cls.settings):
                pass
        except ScrapeError as exc:
            cls.server.shutdown()
            cls._tmp.cleanup()
            raise unittest.SkipTest(f"No usable browser: {exc}")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls._tmp.cleanup()

    def product(self, page: str, selector: str = "p.price_color") -> Product:
        return Product("Test Book", f"{self.base_url}/{page}", selector)

    def test_reads_price_and_saves_screenshot(self) -> None:
        with PriceScraper(self.settings) as scraper:
            reading = scraper.check(self.product("product.html"))
        self.assertEqual(reading.price, 51.77)
        self.assertEqual(reading.raw_text, "£51.77")
        screenshot = Path(reading.screenshot)
        self.assertTrue(screenshot.exists())
        self.assertGreater(screenshot.stat().st_size, 1000)

    def test_waits_for_price_that_appears_late(self) -> None:
        with PriceScraper(self.settings) as scraper:
            reading = scraper.check(self.product("product_delayed.html"))
        self.assertEqual(reading.price, 49.99)

    def test_missing_selector_raises_scrape_error_and_saves_error_screenshot(self) -> None:
        with PriceScraper(self.settings) as scraper:
            with self.assertRaises(ScrapeError):
                scraper.check(self.product("product.html", selector=".does-not-exist"))
        errors = list(self.settings.screenshot_dir.glob("error_*.png"))
        self.assertTrue(errors)

    def test_unreachable_site_raises_scrape_error(self) -> None:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            closed_port = sock.getsockname()[1]
        product = Product("Offline", f"http://127.0.0.1:{closed_port}/nothing", ".price")
        with PriceScraper(self.settings) as scraper:
            with self.assertRaises(ScrapeError):
                scraper.check(product)

    def test_using_scraper_outside_with_block_raises(self) -> None:
        with self.assertRaises(ScrapeError):
            PriceScraper(self.settings).check(self.product("product.html"))


if __name__ == "__main__":
    unittest.main()
