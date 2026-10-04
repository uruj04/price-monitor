"""Playwright browser automation that reads a product's price."""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from .config import Settings
from .exceptions import PriceParseError, ScrapeError
from .models import PriceReading, Product
from .parsing import parse_price

logger = logging.getLogger("pricemonitor")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "product"


class PriceScraper:
    """Owns one browser for a whole run. Use it as a context manager."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._playwright = None
        self._browser = None
        self._context = None

    def __enter__(self) -> "PriceScraper":
        s = self.settings
        try:
            self._playwright = sync_playwright().start()
            launch_options = {"headless": s.headless, "args": list(s.chromium_args)}
            if s.chromium_path:
                launch_options["executable_path"] = s.chromium_path
            self._browser = self._playwright.chromium.launch(**launch_options)
            self._context = self._browser.new_context(
                user_agent=s.user_agent, viewport={"width": 1280, "height": 900}
            )
        except PlaywrightError as exc:
            self.close()
            raise ScrapeError(
                "Could not start the browser. Run 'playwright install chromium' first."
            ) from exc
        logger.info("Browser started (headless=%s)", s.headless)
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def close(self) -> None:
        """Release every browser resource, even if an earlier step failed."""
        for name in ("_context", "_browser"):
            resource = getattr(self, name)
            if resource is not None:
                try:
                    resource.close()
                except PlaywrightError as exc:
                    logger.warning("Error closing %s: %s", name.strip("_"), exc)
                setattr(self, name, None)
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except PlaywrightError as exc:
                logger.warning("Error stopping Playwright: %s", exc)
            self._playwright = None

    def check(self, product: Product) -> PriceReading:
        """Read the current price, retrying on network and timeout errors."""
        if self._context is None:
            raise ScrapeError("The scraper is not started. Use it in a 'with' block.")

        s = self.settings
        last_error: Exception | None = None
        for attempt in range(1, s.max_retries + 1):
            try:
                return self._fetch_once(product)
            except PriceParseError:
                raise
            except PlaywrightError as exc:
                last_error = exc
                reason = str(exc).strip().splitlines()[0] if str(exc).strip() else "unknown error"
                logger.warning(
                    "Attempt %d/%d for '%s' failed: %s", attempt, s.max_retries, product.name, reason
                )
                if attempt < s.max_retries:
                    time.sleep(s.retry_delay_s * attempt)

        raise ScrapeError(
            f"Could not read the price for '{product.name}' after {s.max_retries} attempt(s)."
        ) from last_error

    def _fetch_once(self, product: Product) -> PriceReading:
        page = self._context.new_page()
        page.set_default_timeout(self.settings.timeout_ms)
        try:
            page.goto(product.url, wait_until="domcontentloaded")
            price_element = page.locator(product.price_selector).first
            price_element.wait_for(state="visible")
            raw_text = price_element.inner_text().strip()
            price = parse_price(raw_text)
            screenshot = self._save_screenshot(page, product, prefix="")
            return PriceReading(
                timestamp=datetime.now().isoformat(timespec="seconds"),
                name=product.name,
                url=product.url,
                price=price,
                raw_text=raw_text,
                screenshot=str(screenshot),
            )
        except PlaywrightError:
            self._save_screenshot(page, product, prefix="error_", ignore_errors=True)
            raise
        finally:
            page.close()

    def _save_screenshot(
        self, page, product: Product, prefix: str, ignore_errors: bool = False
    ) -> Path:
        directory = self.settings.screenshot_dir
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = directory / f"{prefix}{_slug(product.name)}_{stamp}.png"
        try:
            directory.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(path))
        except (PlaywrightError, OSError) as exc:
            if not ignore_errors:
                raise ScrapeError(f"Could not save screenshot: {exc}") from exc
            logger.warning("Could not save error screenshot: %s", exc)
        return path
