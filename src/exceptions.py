"""
Custom exception hierarchy for the Harmonic Pattern Trading System.

This module defines specific exceptions for different error scenarios,
enabling more precise error handling and better debugging.
"""

from typing import Optional


class HarmonicTradingError(Exception):
    """Base exception for all harmonic trading system errors."""

    def __init__(self, message: str, ticker: Optional[str] = None):
        self.ticker = ticker
        self.message = message
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        """Format error message with optional ticker prefix."""
        if self.ticker:
            return f"[{self.ticker}] {self.message}"
        return self.message


class DataDownloadError(HarmonicTradingError):
    """Raised when data download fails."""
    pass


class InsufficientDataError(HarmonicTradingError):
    """Raised when insufficient data is available for pattern detection."""

    def __init__(self, message: str, ticker: Optional[str] = None, bars_available: int = 0, bars_required: int = 0):
        self.bars_available = bars_available
        self.bars_required = bars_required
        super().__init__(message, ticker)


class PatternDetectionError(HarmonicTradingError):
    """Raised when pattern detection fails."""
    pass


class PatternValidationError(HarmonicTradingError):
    """Raised when a pattern fails validation."""

    def __init__(self, message: str, ticker: Optional[str] = None, pattern_type: Optional[str] = None):
        self.pattern_type = pattern_type
        super().__init__(message, ticker)


class TemporalValidationError(PatternValidationError):
    """Raised when pattern fails temporal proportionality validation."""

    def __init__(self, message: str, ticker: Optional[str] = None,
                 pattern_type: Optional[str] = None, duration_days: int = 0):
        self.duration_days = duration_days
        super().__init__(message, ticker, pattern_type)


class ConfigurationError(HarmonicTradingError):
    """Raised when configuration is invalid."""
    pass


class ChartGenerationError(HarmonicTradingError):
    """Raised when chart generation fails."""

    def __init__(self, message: str, ticker: Optional[str] = None, chart_path: Optional[str] = None):
        self.chart_path = chart_path
        super().__init__(message, ticker)


class InvalidPriceDataError(HarmonicTradingError):
    """Raised when price data is invalid or malformed."""
    pass


class StrategyError(HarmonicTradingError):
    """Raised when TP strategy calculation fails."""

    def __init__(self, message: str, ticker: Optional[str] = None, strategy_name: Optional[str] = None):
        self.strategy_name = strategy_name
        super().__init__(message, ticker)


class PatternConversionError(HarmonicTradingError):
    """Raised when converting between pattern formats fails."""

    def __init__(self, message: str, ticker: Optional[str] = None,
                 source_format: Optional[str] = None, target_format: Optional[str] = None):
        self.source_format = source_format
        self.target_format = target_format
        super().__init__(message, ticker)
