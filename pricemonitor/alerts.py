"""Decide when to alert, and send optional e-mail notifications."""

import logging
import smtplib
from email.message import EmailMessage

from .config import Settings
from .models import PriceReading, Product

logger = logging.getLogger("pricemonitor")


def build_alerts(product: Product, reading: PriceReading, previous_price: float | None) -> list[str]:
    """Return alert messages for a reading (empty list when nothing noteworthy).

    The target alert fires only when the target is newly reached, so a price that
    stays below target does not trigger a fresh alert on every check.
    """
    alerts = []
    newly_at_target = previous_price is None or previous_price > (product.target_price or 0)
    if product.target_price is not None and reading.price <= product.target_price and newly_at_target:
        alerts.append(
            f"TARGET HIT: {product.name} is {reading.price:.2f}, "
            f"at or below your target of {product.target_price:.2f}."
        )
    if previous_price is not None and reading.price < previous_price:
        alerts.append(
            f"PRICE DROP: {product.name} fell from {previous_price:.2f} to {reading.price:.2f}."
        )
    return alerts


class EmailNotifier:
    """Sends alert e-mails over SMTP. Failures are logged, never raised."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def enabled(self) -> bool:
        return self.settings.email_enabled

    def send(self, subject: str, body: str) -> bool:
        if not self.enabled:
            return False
        s = self.settings
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = s.smtp_user
        message["To"] = s.alert_email_to
        message.set_content(body)
        try:
            with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as server:
                server.starttls()
                server.login(s.smtp_user, s.smtp_password)
                server.send_message(message)
        except (smtplib.SMTPException, OSError) as exc:
            logger.error("Could not send alert e-mail: %s", exc)
            return False
        logger.info("Alert e-mail sent to %s", s.alert_email_to)
        return True
