"""
Tests for custom exception hierarchy.
"""

import pytest
from pathlib import Path
import sys

src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from exceptions import (
    HarmonicTradingError,
    DataDownloadError,
    InsufficientDataError,
    PatternDetectionError,
    PatternValidationError,
    TemporalValidationError,
    ConfigurationError,
    ChartGenerationError,
    InvalidPriceDataError,
    StrategyError,
    PatternConversionError
)


class TestHarmonicTradingError:
    """Test base exception class."""

    def test_basic_error(self):
        """Test basic error creation."""
        error = HarmonicTradingError("Test error")
        assert str(error) == "Test error"

    def test_error_with_ticker(self):
        """Test error with ticker prefix."""
        error = HarmonicTradingError("Test error", ticker="AAPL")
        assert "[AAPL]" in str(error)
        assert error.ticker == "AAPL"


class TestDataDownloadError:
    """Test DataDownloadError."""

    def test_download_error(self):
        """Test download error creation."""
        error = DataDownloadError("Failed to download data", ticker="MSFT")
        assert "[MSFT]" in str(error)
        assert "download" in str(error).lower()


class TestInsufficientDataError:
    """Test InsufficientDataError."""

    def test_insufficient_data_error(self):
        """Test insufficient data error with metadata."""
        error = InsufficientDataError(
            "Not enough bars",
            ticker="GOOGL",
            bars_available=20,
            bars_required=50
        )

        assert "[GOOGL]" in str(error)
        assert error.bars_available == 20
        assert error.bars_required == 50


class TestPatternValidationError:
    """Test PatternValidationError."""

    def test_validation_error_with_pattern_type(self):
        """Test validation error with pattern type."""
        error = PatternValidationError(
            "Invalid Fibonacci ratios",
            ticker="TSLA",
            pattern_type="gartley"
        )

        assert "[TSLA]" in str(error)
        assert error.pattern_type == "gartley"


class TestTemporalValidationError:
    """Test TemporalValidationError."""

    def test_temporal_validation_error(self):
        """Test temporal validation error with duration."""
        error = TemporalValidationError(
            "Pattern duration too long",
            ticker="NVDA",
            pattern_type="bat",
            duration_days=3650
        )

        assert "[NVDA]" in str(error)
        assert error.duration_days == 3650
        assert error.pattern_type == "bat"


class TestChartGenerationError:
    """Test ChartGenerationError."""

    def test_chart_error_with_path(self):
        """Test chart generation error with path."""
        error = ChartGenerationError(
            "Failed to save chart",
            ticker="AAPL",
            chart_path="/path/to/chart.png"
        )

        assert "[AAPL]" in str(error)
        assert error.chart_path == "/path/to/chart.png"


class TestStrategyError:
    """Test StrategyError."""

    def test_strategy_error(self):
        """Test strategy error with strategy name."""
        error = StrategyError(
            "Failed to calculate targets",
            ticker="META",
            strategy_name="MITCH"
        )

        assert "[META]" in str(error)
        assert error.strategy_name == "MITCH"


class TestPatternConversionError:
    """Test PatternConversionError."""

    def test_conversion_error(self):
        """Test pattern conversion error."""
        error = PatternConversionError(
            "Failed to convert pattern",
            ticker="AMZN",
            source_format="pyharmonics",
            target_format="HarmonicPattern"
        )

        assert "[AMZN]" in str(error)
        assert error.source_format == "pyharmonics"
        assert error.target_format == "HarmonicPattern"


class TestExceptionInheritance:
    """Test exception inheritance hierarchy."""

    def test_all_inherit_from_base(self):
        """Test that all exceptions inherit from HarmonicTradingError."""
        exceptions = [
            DataDownloadError,
            InsufficientDataError,
            PatternDetectionError,
            PatternValidationError,
            TemporalValidationError,
            ConfigurationError,
            ChartGenerationError,
            InvalidPriceDataError,
            StrategyError,
            PatternConversionError
        ]

        for exc_class in exceptions:
            assert issubclass(exc_class, HarmonicTradingError)

    def test_can_catch_with_base_exception(self):
        """Test that specific exceptions can be caught with base class."""
        try:
            raise DataDownloadError("Test", ticker="AAPL")
        except HarmonicTradingError as e:
            assert isinstance(e, DataDownloadError)
            assert e.ticker == "AAPL"
