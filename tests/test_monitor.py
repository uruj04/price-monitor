import tempfile
import unittest
from pathlib import Path

from pricemonitor.config import Settings
from pricemonitor.exceptions import ScrapeError
from pricemonitor.models import PriceReading, Product
from pricemonitor.monitor import PriceMonitor
from pricemonitor.storage import PriceHistory


class FakeScraper:
    prices: dict[str, float | Exception] = {}

    def __init__(self, settings: Settings) -> None:
        pass

    def __enter__(self) -> "FakeScraper":
        return self

    def __exit__(self, *exc_info) -> None:
        return None

    def check(self, product: Product) -> PriceReading:
        outcome = self.prices[product.name]
        if isinstance(outcome, Exception):
            raise outcome
        return PriceReading("2026-10-01T10:00:00", product.name, product.url, outcome, f"£{outcome}", "s.png")


class RecordingNotifier:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send(self, subject: str, body: str) -> bool:
        self.sent.append((subject, body))
        return True


class MonitorTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.history = PriceHistory(Path(self._tmp.name) / "history.csv")
        self.products = [
            Product("Cheap", "https://x.test/1", ".p", target_price=20.0),
            Product("Broken", "https://x.test/2", ".p"),
            Product("Pricey", "https://x.test/3", ".p", target_price=5.0),
        ]
        FakeScraper.prices = {
            "Cheap": 15.0,
            "Broken": ScrapeError("page did not load"),
            "Pricey": 99.0,
        }
        self.notifier = RecordingNotifier()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def build(self) -> PriceMonitor:
        return PriceMonitor(
            Settings(), self.products, self.history, self.notifier, scraper_factory=FakeScraper
        )

    def test_one_failure_does_not_stop_the_run(self) -> None:
        summary = self.build().run_once()
        self.assertEqual((summary.checked, summary.succeeded, summary.failed), (3, 2, 1))
        self.assertEqual(len(summary.errors), 1)
        self.assertEqual({r["name"] for r in self.history.load()}, {"Cheap", "Pricey"})

    def test_alerts_are_collected_and_emailed_once(self) -> None:
        summary = self.build().run_once()
        self.assertEqual(len(summary.alerts), 1)
        self.assertIn("Cheap", summary.alerts[0])
        self.assertEqual(len(self.notifier.sent), 1)

    def test_price_drop_detected_across_runs(self) -> None:
        monitor = self.build()
        monitor.run_once()
        FakeScraper.prices["Pricey"] = 80.0
        summary = monitor.run_once()
        self.assertTrue(any("PRICE DROP" in a and "Pricey" in a for a in summary.alerts))

    def test_no_email_when_nothing_to_report(self) -> None:
        FakeScraper.prices["Cheap"] = 50.0
        summary = self.build().run_once()
        self.assertEqual(summary.alerts, [])
        self.assertEqual(self.notifier.sent, [])


if __name__ == "__main__":
    unittest.main()
