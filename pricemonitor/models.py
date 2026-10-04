"""Plain data objects shared between modules."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Product:
    """A product page to monitor."""

    name: str
    url: str
    price_selector: str
    target_price: float | None = None


@dataclass(frozen=True)
class PriceReading:
    """One successful price check."""

    timestamp: str
    name: str
    url: str
    price: float
    raw_text: str
    screenshot: str
