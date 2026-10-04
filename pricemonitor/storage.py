"""CSV price history."""

import csv
import logging
from pathlib import Path

from .exceptions import StorageError
from .models import PriceReading

logger = logging.getLogger("pricemonitor")


class PriceHistory:
    """Appends readings to a CSV file and reads them back."""

    FIELDNAMES = ["timestamp", "name", "url", "price", "screenshot"]

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def append(self, reading: PriceReading) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            write_header = not self.path.exists() or self.path.stat().st_size == 0
            with self.path.open("a", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(file, fieldnames=self.FIELDNAMES)
                if write_header:
                    writer.writeheader()
                writer.writerow(
                    {
                        "timestamp": reading.timestamp,
                        "name": reading.name,
                        "url": reading.url,
                        "price": f"{reading.price:.2f}",
                        "screenshot": reading.screenshot,
                    }
                )
        except OSError as exc:
            raise StorageError(f"Could not write '{self.path}': {exc}") from exc

    def load(self, name: str | None = None) -> list[dict[str, str]]:
        """Return all rows, optionally only those for one product name."""
        if not self.path.exists():
            return []
        try:
            with self.path.open("r", newline="", encoding="utf-8") as file:
                rows = list(csv.DictReader(file))
        except (OSError, csv.Error, UnicodeDecodeError) as exc:
            raise StorageError(f"Could not read '{self.path}': {exc}") from exc

        valid = []
        for row in rows:
            try:
                float(row["price"])
            except (KeyError, TypeError, ValueError):
                logger.warning("Skipping malformed history row: %s", row)
                continue
            if name is None or row.get("name") == name:
                valid.append(row)
        return valid

    def last_price(self, name: str) -> float | None:
        rows = self.load(name)
        return float(rows[-1]["price"]) if rows else None
