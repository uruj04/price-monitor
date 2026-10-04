"""Custom exceptions used across the application."""


class PriceMonitorError(Exception):
    """Base class for all application errors."""


class ConfigError(PriceMonitorError):
    """Raised when settings or the products file are invalid."""


class ScrapeError(PriceMonitorError):
    """Raised when a page cannot be loaded or the price cannot be found."""


class PriceParseError(PriceMonitorError):
    """Raised when scraped text cannot be converted to a number."""


class StorageError(PriceMonitorError):
    """Raised when the price history file cannot be read or written."""
