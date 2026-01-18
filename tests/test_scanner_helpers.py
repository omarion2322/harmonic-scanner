"""
Tests for scanner helper classes.
"""

import pytest
from pathlib import Path
import sys
from datetime import datetime

src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from scanner_helpers import (
    ScanProgressTracker,
    FailedDownloadRetrier,
    PatternTrackerUpdater,
    ScanResultsFormatter
)


class TestScanProgressTracker:
    """Test ScanProgressTracker class."""

    def test_initialization(self):
        """Test tracker initialization."""
        tracker = ScanProgressTracker(total_tickers=100, report_interval=10)

        assert tracker.total_tickers == 100
        assert tracker.report_interval == 10
        assert tracker.current_index == 0
        assert tracker.start_time is not None

    def test_update_increments_index(self):
        """Test that update increments current index."""
        tracker = ScanProgressTracker(total_tickers=100)
        tracker.update(5, "AAPL")

        assert tracker.current_index == 5

    def test_get_summary(self):
        """Test getting summary statistics."""
        tracker = ScanProgressTracker(total_tickers=100)
        tracker.update(50, "AAPL")

        summary = tracker.get_summary()

        assert 'duration_seconds' in summary
        assert 'duration_minutes' in summary
        assert 'tickers_processed' in summary
        assert 'rate_per_second' in summary
        assert summary['tickers_processed'] == 50

    def test_summary_calculates_rate(self):
        """Test that summary calculates processing rate."""
        tracker = ScanProgressTracker(total_tickers=100)
        tracker.update(10, "AAPL")

        summary = tracker.get_summary()

        # Rate should be positive
        assert summary['rate_per_second'] >= 0


class TestFailedDownloadRetrier:
    """Test FailedDownloadRetrier class."""

    class MockScanner:
        """Mock scanner for testing."""

        def __init__(self, retry_success=True):
            self.retry_success = retry_success
            self.scan_calls = []

        def scan_stock(self, ticker, verbose=False, override_period=None):
            """Mock scan_stock method."""
            self.scan_calls.append({
                'ticker': ticker,
                'verbose': verbose,
                'period': override_period
            })

            if self.retry_success:
                return {
                    'ticker': ticker,
                    'signal': 'BUY',
                    'reason': 'Pattern detected',
                    'patterns': [],
                    'current_price': 100.0
                }
            else:
                return {
                    'ticker': ticker,
                    'signal': 'HOLD',
                    'reason': 'No data available',
                    'patterns': []
                }

    def test_identify_failed_tickers(self):
        """Test identifying failed ticker downloads."""
        scanner = self.MockScanner()
        retrier = FailedDownloadRetrier(scanner)

        results = {
            'BUY': [],
            'SELL': [],
            'HOLD': [
                {'ticker': 'AAPL', 'reason': 'No data available'},
                {'ticker': 'MSFT', 'reason': 'No valid patterns'},
                {'ticker': 'GOOGL', 'reason': 'Error analyzing stock'},
            ]
        }

        failed = retrier.identify_failed_tickers(results)

        assert len(failed) == 2
        assert 'AAPL' in failed
        assert 'GOOGL' in failed
        assert 'MSFT' not in failed  # Not a download failure

    def test_retry_failed_success(self):
        """Test successful retry updates results."""
        scanner = self.MockScanner(retry_success=True)
        retrier = FailedDownloadRetrier(scanner)

        failed_tickers = ['AAPL', 'MSFT']
        results = {
            'BUY': [],
            'SELL': [],
            'HOLD': [
                {'ticker': 'AAPL', 'reason': 'No data available'},
                {'ticker': 'MSFT', 'reason': 'No data available'},
            ]
        }

        success, failure = retrier.retry_failed(failed_tickers, results)

        assert success == 2
        assert failure == 0
        assert len(results['HOLD']) == 0
        assert len(results['BUY']) == 2

    def test_retry_failed_uses_fallback_period(self):
        """Test that retry uses fallback period."""
        scanner = self.MockScanner()
        retrier = FailedDownloadRetrier(scanner, fallback_period='1y')

        failed_tickers = ['AAPL']
        results = {
            'BUY': [],
            'SELL': [],
            'HOLD': [{'ticker': 'AAPL', 'reason': 'No data available'}]
        }

        retrier.retry_failed(failed_tickers, results)

        # Check that scan was called with correct period
        assert len(scanner.scan_calls) == 1
        assert scanner.scan_calls[0]['period'] == '1y'

    def test_retry_failed_empty_list(self):
        """Test retry with empty failed list returns zero counts."""
        scanner = self.MockScanner()
        retrier = FailedDownloadRetrier(scanner)

        results = {'BUY': [], 'SELL': [], 'HOLD': []}
        success, failure = retrier.retry_failed([], results)

        assert success == 0
        assert failure == 0


class TestPatternTrackerUpdater:
    """Test PatternTrackerUpdater class."""

    class MockTracker:
        """Mock pattern tracker."""

        def update_patterns(self, ticker, detected_patterns, price_data, current_date):
            """Mock update_patterns method."""
            return {
                'confirmed': detected_patterns[:1],  # First pattern confirmed
                'watchlist': detected_patterns[1:],  # Rest in watchlist
                'invalidated': []
            }

    class MockDetector:
        """Mock pattern detector."""

        def _convert_pyharmonics_pattern(self, py_pattern, df, tech, fib_tol, ticker):
            """Mock conversion method."""
            return None  # Simplified for testing

    def test_initialization(self, mock_config):
        """Test tracker updater initialization."""
        from utils import ConfigHelper

        tracker = self.MockTracker()
        detector = self.MockDetector()
        config_helper = ConfigHelper(mock_config)

        updater = PatternTrackerUpdater(tracker, detector, config_helper)

        assert updater.tracker is tracker
        assert updater.detector is detector
        assert updater.stats['confirmed'] == 0
        assert updater.stats['watchlist'] == 0
        assert updater.stats['invalidated'] == 0

    def test_get_stats_returns_copy(self, mock_config):
        """Test that get_stats returns a copy of statistics."""
        from utils import ConfigHelper

        tracker = self.MockTracker()
        detector = self.MockDetector()
        config_helper = ConfigHelper(mock_config)

        updater = PatternTrackerUpdater(tracker, detector, config_helper)
        stats1 = updater.get_stats()
        stats2 = updater.get_stats()

        # Modify one copy
        stats1['confirmed'] = 999

        # Original and other copy should be unchanged
        assert updater.stats['confirmed'] == 0
        assert stats2['confirmed'] == 0


class TestScanResultsFormatter:
    """Test ScanResultsFormatter class."""

    def test_get_ticker_list_with_limit(self, mock_config):
        """Test getting ticker list with limit."""
        # Mock get_stock_list function
        mock_config.get_stock_list = lambda: ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA']

        tickers = ScanResultsFormatter.get_ticker_list(mock_config, max_stocks=3)

        assert len(tickers) == 3
        assert tickers == ['AAPL', 'MSFT', 'GOOGL']

    def test_get_ticker_list_without_limit(self, mock_config):
        """Test getting full ticker list."""
        mock_config.get_stock_list = lambda: ['AAPL', 'MSFT', 'GOOGL']

        tickers = ScanResultsFormatter.get_ticker_list(mock_config, max_stocks=None)

        assert len(tickers) == 3

    def test_print_header_does_not_crash(self, mock_config):
        """Test that print_header executes without errors."""
        # This just verifies the method doesn't crash
        ScanResultsFormatter.print_header(mock_config)

    def test_print_summary_does_not_crash(self):
        """Test that print_summary executes without errors."""
        results = {
            'BUY': [{'ticker': 'AAPL'}],
            'SELL': [],
            'HOLD': [{'ticker': 'MSFT'}]
        }
        tracker_stats = {
            'confirmed': 5,
            'watchlist': 10,
            'invalidated': 2
        }

        # This just verifies the method doesn't crash
        ScanResultsFormatter.print_summary(results, tracker_stats)
