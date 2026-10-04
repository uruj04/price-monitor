import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pricemonitor.alerts import EmailNotifier, build_alerts
from pricemonitor.config import Settings
from pricemonitor.models import PriceReading, Product
from pricemonitor.storage import PriceHistory


def make_reading(price: float, name: str = "Book") -> PriceReading:
    return PriceReading(
        timestamp="2026-10-01T10:00:00",
        name=name,
        url="https://x.test/a",
        price=price,
        raw_text=f"£{price}",
        screenshot="shot.png",
    )


class PriceHistoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.history = PriceHistory(Path(self._tmp.name) / "data" / "history.csv")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_empty_history(self) -> None:
        self.assertEqual(self.history.load(), [])
        self.assertIsNone(self.history.last_price("Book"))

    def test_append_and_load_with_single_header(self) -> None:
        self.history.append(make_reading(10.0))
        self.history.append(make_reading(9.5))
        self.assertEqual(len(self.history.load()), 2)
        content = self.history.path.read_text(encoding="utf-8")
        self.assertEqual(content.count("timestamp,name"), 1)

    def test_last_price_and_name_filter(self) -> None:
        self.history.append(make_reading(10.0, "A"))
        self.history.append(make_reading(20.0, "B"))
        self.history.append(make_reading(8.0, "A"))
        self.assertEqual(self.history.last_price("A"), 8.0)
        self.assertEqual(self.history.last_price("B"), 20.0)
        self.assertEqual(len(self.history.load("A")), 2)

    def test_malformed_rows_are_skipped(self) -> None:
        self.history.path.parent.mkdir(parents=True)
        self.history.path.write_text(
            "timestamp,name,url,price,screenshot\n"
            "t,Book,u,not-a-number,s\n"
            "t,Book,u,12.50,s\n",
            encoding="utf-8",
        )
        self.assertEqual(self.history.last_price("Book"), 12.5)


class BuildAlertsTests(unittest.TestCase):
    product = Product("Book", "https://x.test/a", ".p", target_price=50.0)

    def test_target_hit(self) -> None:
        alerts = build_alerts(self.product, make_reading(49.0), None)
        self.assertEqual(len(alerts), 1)
        self.assertIn("TARGET HIT", alerts[0])

    def test_target_alert_fires_when_target_is_newly_reached(self) -> None:
        alerts = build_alerts(self.product, make_reading(49.0), 55.0)
        self.assertTrue(any("TARGET HIT" in a for a in alerts))

    def test_target_alert_not_repeated_while_price_stays_below_target(self) -> None:
        self.assertEqual(build_alerts(self.product, make_reading(49.0), 49.0), [])
        alerts = build_alerts(self.product, make_reading(48.0), 49.0)
        self.assertEqual(len(alerts), 1)
        self.assertIn("PRICE DROP", alerts[0])

    def test_price_drop(self) -> None:
        alerts = build_alerts(self.product, make_reading(55.0), 60.0)
        self.assertEqual(len(alerts), 1)
        self.assertIn("PRICE DROP", alerts[0])

    def test_both_alerts(self) -> None:
        self.assertEqual(len(build_alerts(self.product, make_reading(45.0), 60.0)), 2)

    def test_no_alert_when_price_rises_or_is_unchanged(self) -> None:
        self.assertEqual(build_alerts(self.product, make_reading(60.0), 55.0), [])
        self.assertEqual(build_alerts(self.product, make_reading(60.0), 60.0), [])

    def test_no_target_and_no_history(self) -> None:
        product = Product("Book", "https://x.test/a", ".p")
        self.assertEqual(build_alerts(product, make_reading(1.0), None), [])


class EmailNotifierTests(unittest.TestCase):
    def test_disabled_without_settings(self) -> None:
        notifier = EmailNotifier(Settings())
        self.assertFalse(notifier.enabled)
        self.assertFalse(notifier.send("s", "b"))

    def test_sends_message_when_configured(self) -> None:
        settings = Settings(
            smtp_host="smtp.example.com",
            smtp_user="me@example.com",
            smtp_password="secret",
            alert_email_to="you@example.com",
        )
        with mock.patch("pricemonitor.alerts.smtplib.SMTP") as smtp:
            self.assertTrue(EmailNotifier(settings).send("Subject", "Body"))
        server = smtp.return_value.__enter__.return_value
        server.starttls.assert_called_once()
        server.login.assert_called_once_with("me@example.com", "secret")
        server.send_message.assert_called_once()

    def test_smtp_failure_is_swallowed(self) -> None:
        settings = Settings(
            smtp_host="smtp.example.com",
            smtp_user="me@example.com",
            smtp_password="secret",
            alert_email_to="you@example.com",
        )
        with mock.patch("pricemonitor.alerts.smtplib.SMTP", side_effect=OSError("down")):
            self.assertFalse(EmailNotifier(settings).send("Subject", "Body"))


if __name__ == "__main__":
    unittest.main()
