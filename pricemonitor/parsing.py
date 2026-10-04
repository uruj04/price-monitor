"""Turn scraped price text such as '£1,299.00' or '12,99 €' into a float."""

import re

from .exceptions import PriceParseError

_GROUP_SPACES = re.compile(r"(?<=\d)[\u00a0\u202f\u2009 ](?=\d{3}(?:\D|$))")
_NUMBER = re.compile(r"\d[\d.,]*\d|\d")


def parse_price(text: str) -> float:
    """Extract the first number from `text`, handling common currency formats."""
    if not text or not text.strip():
        raise PriceParseError("Price text is empty.")

    cleaned = _GROUP_SPACES.sub("", text)
    match = _NUMBER.search(cleaned)
    if not match:
        raise PriceParseError(f"No number found in price text: {text!r}")

    raw = match.group()
    last_dot, last_comma = raw.rfind("."), raw.rfind(",")

    if last_dot != -1 and last_comma != -1:
        decimal, thousands = (".", ",") if last_dot > last_comma else (",", ".")
        raw = raw.replace(thousands, "").replace(decimal, ".")
    elif last_comma != -1:
        parts = raw.split(",")
        if len(parts) == 2 and len(parts[1]) in (1, 2):
            raw = f"{parts[0]}.{parts[1]}"
        else:
            raw = raw.replace(",", "")
    elif raw.count(".") > 1:
        raw = raw.replace(".", "")

    try:
        return float(raw)
    except ValueError:
        raise PriceParseError(f"Could not convert {text!r} to a number.") from None
