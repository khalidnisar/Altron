class AltronError(Exception):
    """Base exception for the platform."""


class DataValidationError(AltronError, ValueError):
    """Raised when market data violates the canonical OHLCV contract."""


class ConfigurationError(AltronError, ValueError):
    """Raised when a component has an unsafe or invalid configuration."""


class StrategyError(AltronError):
    """Raised when a strategy cannot produce valid signals."""


class LiveTradingDisabled(ConfigurationError):
    """Raised when real execution was requested without all safety gates."""
