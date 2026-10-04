"""Settings from .env / environment variables, and the products file loader."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from dotenv import load_dotenv

from .exceptions import ConfigError
from .models import Product

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def _load_env_file() -> None:
    """Load .env from the current folder, falling back to the project folder."""
    for candidate in (Path.cwd() / ".env", Path(__file__).resolve().parent.parent / ".env"):
        if candidate.is_file():
            load_dotenv(candidate)
            return


def _get_bool(env: Mapping[str, str], key: str, default: bool) -> bool:
    raw = env.get(key)
    if raw is None or raw.strip() == "":
        return default
    value = raw.strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    raise ConfigError(f"{key} must be true or false, got '{raw}'.")


def _get_number(env: Mapping[str, str], key: str, default: float, cast, minimum: float):
    raw = env.get(key)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = cast(raw.strip())
    except ValueError:
        raise ConfigError(f"{key} must be a number, got '{raw}'.") from None
    if value < minimum:
        raise ConfigError(f"{key} must be at least {minimum}, got {value}.")
    return value


def _get_optional(env: Mapping[str, str], key: str) -> str | None:
    raw = env.get(key)
    return raw.strip() if raw and raw.strip() else None


@dataclass(frozen=True)
class Settings:
    """Runtime configuration. Build it with Settings.from_env()."""

    headless: bool = True
    timeout_ms: int = 15000
    max_retries: int = 3
    retry_delay_s: float = 2.0
    screenshot_dir: Path = Path("screenshots")
    data_file: Path = Path("data") / "price_history.csv"
    products_file: Path = Path("products.json")
    log_file: Path = Path("logs") / "price_monitor.log"
    user_agent: str = DEFAULT_USER_AGENT
    chromium_path: str | None = None
    chromium_args: tuple[str, ...] = ()
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    alert_email_to: str | None = None

    @property
    def email_enabled(self) -> bool:
        return all([self.smtp_host, self.smtp_user, self.smtp_password, self.alert_email_to])

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        """Read settings from `env`, or from .env and the process environment."""
        if env is None:
            _load_env_file()
            env = os.environ

        args = _get_optional(env, "CHROMIUM_ARGS")
        return cls(
            headless=_get_bool(env, "HEADLESS", True),
            timeout_ms=_get_number(env, "TIMEOUT_MS", 15000, int, 1000),
            max_retries=_get_number(env, "MAX_RETRIES", 3, int, 1),
            retry_delay_s=_get_number(env, "RETRY_DELAY_S", 2.0, float, 0),
            screenshot_dir=Path(env.get("SCREENSHOT_DIR") or "screenshots"),
            data_file=Path(env.get("DATA_FILE") or Path("data") / "price_history.csv"),
            products_file=Path(env.get("PRODUCTS_FILE") or "products.json"),
            log_file=Path(env.get("LOG_FILE") or Path("logs") / "price_monitor.log"),
            user_agent=_get_optional(env, "USER_AGENT") or DEFAULT_USER_AGENT,
            chromium_path=_get_optional(env, "CHROMIUM_PATH"),
            chromium_args=tuple(args.split()) if args else (),
            smtp_host=_get_optional(env, "SMTP_HOST"),
            smtp_port=_get_number(env, "SMTP_PORT", 587, int, 1),
            smtp_user=_get_optional(env, "SMTP_USER"),
            smtp_password=_get_optional(env, "SMTP_PASSWORD"),
            alert_email_to=_get_optional(env, "ALERT_EMAIL_TO"),
        )


def load_products(path: Path) -> list[Product]:
    """Load and validate the list of products to monitor."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigError(f"Products file not found: {path}") from None
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"Could not read products file '{path}': {exc}") from exc

    if not isinstance(data, list) or not data:
        raise ConfigError("The products file must contain a non-empty JSON list.")

    products: list[Product] = []
    for number, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            raise ConfigError(f"Product #{number} must be a JSON object.")
        for key in ("name", "url", "price_selector"):
            if not str(item.get(key, "")).strip():
                raise ConfigError(f"Product #{number} is missing '{key}'.")

        url = str(item["url"]).strip()
        if not url.startswith(("http://", "https://")):
            raise ConfigError(f"Product #{number} has an invalid URL: {url}")

        target = item.get("target_price")
        if target is not None:
            try:
                target = float(target)
            except (TypeError, ValueError):
                raise ConfigError(f"Product #{number} has a non-numeric target_price.") from None
            if target <= 0:
                raise ConfigError(f"Product #{number} target_price must be positive.")

        products.append(
            Product(
                name=str(item["name"]).strip(),
                url=url,
                price_selector=str(item["price_selector"]).strip(),
                target_price=target,
            )
        )
    return products
