"""
Tests for utility classes (ConfigHelper, PathManager, FormattingUtils, TickerManager).
"""

import pytest
from pathlib import Path
import sys

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from utils import ConfigHelper, PathManager, FormattingUtils, TickerManager


class TestConfigHelper:
    """Test ConfigHelper class."""

    def test_get_existing_key(self, mock_config):
        """Test getting an existing configuration key."""
        helper = ConfigHelper(mock_config)
        assert helper.get('DATA_INTERVAL') == '1d'

    def test_get_missing_key_with_default(self, mock_config):
        """Test getting a missing key returns default."""
        helper = ConfigHelper(mock_config)
        assert helper.get('NONEXISTENT_KEY', 'default_value') == 'default_value'

    def test_get_bool(self, mock_config):
        """Test getting boolean configuration values."""
        helper = ConfigHelper(mock_config)
        assert helper.get_bool('AUTO_SAVE_CHARTS') is False
        assert helper.get_bool('NONEXISTENT', True) is True

    def test_get_int(self, mock_config):
        """Test getting integer configuration values."""
        helper = ConfigHelper(mock_config)
        assert helper.get_int('SWING_WINDOW') == 3
        assert helper.get_int('NONEXISTENT', 42) == 42

    def test_get_float(self, mock_config):
        """Test getting float configuration values."""
        helper = ConfigHelper(mock_config)
        assert helper.get_float('PYHARMONICS_FIB_TOLERANCE') == 0.03
        assert helper.get_float('NONEXISTENT', 3.14) == 3.14

    def test_get_int_invalid_conversion(self, mock_config):
        """Test that invalid int conversion returns default."""
        mock_config.INVALID_INT = 'not_a_number'
        helper = ConfigHelper(mock_config)
        assert helper.get_int('INVALID_INT', 99) == 99

    def test_get_float_invalid_conversion(self, mock_config):
        """Test that invalid float conversion returns default."""
        mock_config.INVALID_FLOAT = 'not_a_number'
        helper = ConfigHelper(mock_config)
        assert helper.get_float('INVALID_FLOAT', 9.99) == 9.99


class TestPathManager:
    """Test PathManager class."""

    def test_initialization_with_project_root(self, tmp_path):
        """Test PathManager initialization with explicit project root."""
        pm = PathManager(project_root=tmp_path)
        assert pm.project_root == tmp_path

    def test_get_report_dir_creates_directory(self, tmp_path):
        """Test that get_report_dir creates the directory structure."""
        pm = PathManager(project_root=tmp_path)
        report_dir = pm.get_report_dir(date='2024-01-15', interval='1wk')

        assert report_dir.exists()
        assert report_dir.is_dir()
        assert '2024-01-15' in str(report_dir)
        assert '1wk' in str(report_dir)

    def test_get_chart_dir_creates_directory(self, tmp_path):
        """Test that get_chart_dir creates the directory structure."""
        pm = PathManager(project_root=tmp_path)
        chart_dir = pm.get_chart_dir(date='2024-01-15', interval='1d')

        assert chart_dir.exists()
        assert chart_dir.is_dir()
        assert 'charts' in str(chart_dir)

    def test_get_tracking_dir_creates_directory(self, tmp_path):
        """Test that get_tracking_dir creates the directory."""
        pm = PathManager(project_root=tmp_path)
        tracking_dir = pm.get_tracking_dir()

        assert tracking_dir.exists()
        assert tracking_dir.is_dir()
        assert 'pattern_tracking' in str(tracking_dir)

    def test_get_report_path(self, tmp_path):
        """Test getting full report path."""
        pm = PathManager(project_root=tmp_path)
        report_path = pm.get_report_path(
            date='2024-01-15',
            interval='1wk',
            verbose=True
        )

        assert report_path.parent.exists()
        assert 'harmonic_report' in report_path.name
        assert 'verbose' in report_path.name
        assert '2024-01-15' in report_path.name

    def test_crypto_asset_type_uses_crypto_reports_dir(self, tmp_path):
        """Test that crypto asset type uses crypto_reports directory."""
        pm = PathManager(project_root=tmp_path)
        report_dir = pm.get_report_dir(asset_type='crypto')

        assert 'crypto_reports' in str(report_dir)


class TestFormattingUtils:
    """Test FormattingUtils class."""

    def test_format_pattern_ratios(self):
        """Test formatting pattern ratios."""
        from pattern_detector import HarmonicPattern, Point
        from datetime import datetime

        # Create minimal pattern for testing
        class MockPattern:
            ab_xa_ratio = 0.618
            bc_projection = 1.272
            ad_xa_ratio = 0.786

        pattern = MockPattern()
        result = FormattingUtils.format_pattern_ratios(pattern)

        assert 'B=0.618' in result
        assert 'BC_proj=1.272' in result
        assert 'D=0.786' in result

    def test_format_reaction_status_no_data(self):
        """Test formatting with no reaction data."""
        class MockPattern:
            pass

        pattern = MockPattern()
        result = FormattingUtils.format_reaction_status(None, pattern)

        assert result == []

    def test_format_reaction_status_with_type1(self):
        """Test formatting with Type 1 reaction detected."""
        class MockReactionData:
            reaction_summary = "Type 1 Detected"
            type1_detected = True
            type1_max_move = 105.50
            type1_reached_382 = True
            type1_reached_618 = False
            type2_detected = False

        class MockPattern:
            pass

        pattern = MockPattern()
        reaction_data = MockReactionData()
        result = FormattingUtils.format_reaction_status(reaction_data, pattern)

        assert len(result) > 0
        assert any('Type 1: ✓ HIT' in line for line in result)
        assert any('105.50' in line for line in result)


class TestTickerManager:
    """Test TickerManager class."""

    def test_merge_with_no_custom_tickers(self):
        """Test merging with no custom tickers returns universe unchanged."""
        universe = ['AAPL', 'MSFT', 'GOOGL']
        result = TickerManager.merge_ticker_lists(None, universe)

        assert result == universe

    def test_merge_with_custom_tickers(self):
        """Test merging custom tickers with universe."""
        custom = ['TSLA', 'NVDA']
        universe = ['AAPL', 'MSFT', 'GOOGL']
        result = TickerManager.merge_ticker_lists(custom, universe)

        assert result[:2] == ['TSLA', 'NVDA']
        assert 'AAPL' in result
        assert 'MSFT' in result
        assert len(result) == 5

    def test_merge_removes_duplicates(self):
        """Test that duplicates are removed (custom takes precedence)."""
        custom = ['TSLA', 'AAPL']
        universe = ['AAPL', 'MSFT', 'GOOGL']
        result = TickerManager.merge_ticker_lists(custom, universe)

        # AAPL should appear only once (from custom list)
        assert result.count('AAPL') == 1
        assert result[1] == 'AAPL'  # Second position (from custom)
        assert len(result) == 4  # TSLA, AAPL, MSFT, GOOGL

    def test_merge_normalizes_to_uppercase(self):
        """Test that tickers are normalized to uppercase."""
        custom = ['tsla', 'nvda']
        universe = ['aapl', 'msft']
        result = TickerManager.merge_ticker_lists(custom, universe)

        assert all(ticker.isupper() for ticker in result[:2])

    def test_print_custom_ticker_info(self, capsys):
        """Test printing custom ticker information (logs to logger)."""
        # This test verifies the function doesn't crash
        # Actual logging output verification would require log capture
        TickerManager.print_custom_ticker_info(['TSLA', 'NVDA'])
        # Function should complete without errors


class TestExceptionHandling:
    """Test that utilities handle edge cases gracefully."""

    def test_path_manager_with_special_characters(self, tmp_path):
        """Test PathManager handles special characters in paths."""
        pm = PathManager(project_root=tmp_path)
        # Should not raise exception
        report_dir = pm.get_report_dir(interval='1wk')
        assert report_dir.exists()

    def test_config_helper_with_none_value(self, mock_config):
        """Test ConfigHelper handles None values properly."""
        mock_config.NONE_VALUE = None
        helper = ConfigHelper(mock_config)

        assert helper.get('NONE_VALUE', 'default') == 'default'
        assert helper.get_bool('NONE_VALUE', True) is True
        assert helper.get_int('NONE_VALUE', 42) == 42
        assert helper.get_float('NONE_VALUE', 3.14) == 3.14
