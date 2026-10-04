"""Runs one full monitoring pass over every configured product."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable

from .alerts import EmailNotifier, build_alerts
from .config import Settings
from .exceptions import PriceMonitorError
from .models import Product
from .scraper import PriceScraper
from .storage import PriceHistory

logger = logging.getLogger("pricemonitor")


@dataclass
class RunSummary:
    checked: int = 0
    succeeded: int = 0
    failed: int = 0
    alerts: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class PriceMonitor:
    """Checks each product, records the price, and raises alerts."""

    def __init__(
        self,
        settings: Settings,
        products: list[Product],
        history: PriceHistory,
        notifier: EmailNotifier | None = None,
        scraper_factory: Callable[[Settings], PriceScraper] = PriceScraper,
    ) -> None:
        self.settings = settings
        self.products = products
        self.history = history
        self.notifier = notifier
        self.scraper_factory = scraper_factory

    def run_once(self) -> RunSummary:
        summary = RunSummary()
        with self.scraper_factory(self.settings) as scraper:
            for product in self.products:
                summary.checked += 1
                try:
                    previous = self.history.last_price(product.name)
                    reading = scraper.check(product)
                    self.history.append(reading)
                except PriceMonitorError as exc:
                    logger.error("%s: %s", product.name, exc)
                    summary.failed += 1
                    summary.errors.append(f"{product.name}: {exc}")
                    continue

                summary.succeeded += 1
                logger.info("%s: %s (%.2f)", product.name, reading.raw_text, reading.price)
                summary.alerts.extend(build_alerts(product, reading, previous))

        for alert in summary.alerts:
            logger.warning(alert)
        if summary.alerts and self.notifier is not None:
            self.notifier.send("Price alert", "\n".join(summary.alerts))
        return summary
