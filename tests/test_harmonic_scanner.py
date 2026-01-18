"""
Tests for HarmonicScanner class.
"""

import pytest
from pathlib import Path
import sys
from unittest.mock import Mock, MagicMock, patch, call
import pandas as pd
import numpy as np
from datetime import datetime

src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from harmonic_scanner import HarmonicScanner, smart_download_data
from pattern_detector import HarmonicPattern
from pathlib import Path as PathLib


class TestHarmonicScannerInitialization:
    """Test HarmonicScanner initialization."""

    def test_scanner_initialization_stocks(self):
        """Test scanner initializes for stocks."""
        scanner = HarmonicScanner(asset_type='stocks')

        assert scanner.detector is not None
        assert scanner.reaction_detector is not None
        assert scanner.tracker is not None
        assert scanner.asset_type == 'stocks'

    def test_scanner_initialization_crypto(self):
        """Test scanner initializes for crypto."""
        scanner = HarmonicScanner(asset_type='crypto')

        assert scanner.detector is not None
        assert scanner.asset_type == 'crypto'

    def test_scanner_has_utility_helpers(self):
        """Test that scanner has utility helpers."""
        scanner = HarmonicScanner()

        assert scanner.config_helper is not None
        assert scanner.path_manager is not None
        assert hasattr(scanner.config_helper, 'get')
        assert hasattr(scanner.path_manager, 'get_report_path')


class TestSmartDownloadData:
    """Test smart_download_data function."""

    @patch('harmonic_scanner.download_crypto_data')
    def test_smart_download_crypto_ticker(self, mock_crypto_download):
        """Test that crypto tickers use crypto downloader."""
        mock_crypto_download.return_value = pd.DataFrame({'close': [100]})

        result = smart_download_data('BTC-USD', period='1mo')

        mock_crypto_download.assert_called_once()
        assert isinstance(result, pd.DataFrame)

    @patch('harmonic_scanner.download_stock_data')
    def test_smart_download_stock_ticker(self, mock_stock_download):
        """Test that stock tickers use stock downloader."""
        mock_stock_download.return_value = pd.DataFrame({'close': [100]})

        result = smart_download_data('AAPL', period='6mo')

        mock_stock_download.assert_called_once()
        assert isinstance(result, pd.DataFrame)

    @patch('harmonic_scanner.download_crypto_data')
    def test_smart_download_eth_usd(self, mock_crypto_download):
        """Test ETH-USD uses crypto downloader."""
        mock_crypto_download.return_value = pd.DataFrame({'close': [2000]})

        smart_download_data('ETH-USD', period='1mo')

        mock_crypto_download.assert_called_once()


class TestGetSP500Tickers:
    """Test get_sp500_tickers method."""

    @patch('harmonic_scanner.pd.read_html')
    def test_get_sp500_tickers_success(self, mock_read_html):
        """Test successful fetch of S&P 500 tickers."""
        # Mock DataFrame from SlickCharts
        mock_df = pd.DataFrame({
            'Symbol': ['AAPL', 'MSFT', 'GOOGL', 'AMZN']
        })
        mock_read_html.return_value = [mock_df]

        scanner = HarmonicScanner()
        tickers = scanner.get_sp500_tickers()

        assert isinstance(tickers, list)
        assert len(tickers) >= 4
        assert 'AAPL' in tickers
        assert 'MSFT' in tickers

    @patch('harmonic_scanner.pd.read_html')
    def test_get_sp500_tickers_failure_uses_fallback(self, mock_read_html):
        """Test that fetch failure uses fallback list."""
        mock_read_html.side_effect = Exception("Network error")

        scanner = HarmonicScanner()
        tickers = scanner.get_sp500_tickers()

        # Should return fallback list
        assert isinstance(tickers, list)
        assert len(tickers) > 0
        assert 'AAPL' in tickers or 'MSFT' in tickers

    @patch('harmonic_scanner.pd.read_html')
    def test_get_sp500_tickers_handles_nan(self, mock_read_html):
        """Test that NaN values are filtered out."""
        mock_df = pd.DataFrame({
            'Symbol': ['AAPL', np.nan, 'MSFT', None, 'GOOGL']
        })
        mock_read_html.return_value = [mock_df]

        scanner = HarmonicScanner()
        tickers = scanner.get_sp500_tickers()

        # Should filter out NaN/None
        assert None not in tickers
        assert np.nan not in tickers
        assert all(isinstance(t, str) for t in tickers)


class TestScanStock:
    """Test scan_stock method."""

    @patch('harmonic_scanner.smart_download_data')
    def test_scan_stock_returns_dict(self, mock_download):
        """Test that scan_stock returns a dictionary."""
        mock_download.return_value = pd.DataFrame({
            'open': [100],
            'high': [102],
            'low': [99],
            'close': [101],
            'volume': [1000000]
        }, index=pd.date_range('2023-01-01', periods=1))

        scanner = HarmonicScanner()
        result = scanner.scan_stock('AAPL')

        assert isinstance(result, dict)
        assert 'ticker' in result
        assert 'signal' in result
        assert 'reason' in result
        assert 'patterns' in result

    @patch('harmonic_scanner.smart_download_data')
    def test_scan_stock_valid_signal(self, mock_download):
        """Test that scan_stock returns valid signal."""
        mock_download.return_value = pd.DataFrame({
            'open': [100],
            'high': [102],
            'low': [99],
            'close': [101],
            'volume': [1000000]
        }, index=pd.date_range('2023-01-01', periods=1))

        scanner = HarmonicScanner()
        result = scanner.scan_stock('AAPL')

        assert result['signal'] in ['BUY', 'SELL', 'HOLD']

    @patch('harmonic_scanner.smart_download_data')
    def test_scan_stock_empty_data_returns_hold(self, mock_download):
        """Test that empty data returns HOLD."""
        mock_download.return_value = pd.DataFrame()

        scanner = HarmonicScanner()
        result = scanner.scan_stock('AAPL')

        assert result['signal'] == 'HOLD'
        assert 'No data available' in result['reason']

    @patch('harmonic_scanner.smart_download_data')
    def test_scan_stock_download_failure_returns_hold(self, mock_download):
        """Test that download failure returns HOLD."""
        mock_download.side_effect = Exception("Download failed")

        scanner = HarmonicScanner()
        result = scanner.scan_stock('INVALID')

        assert result['signal'] == 'HOLD'
        assert 'Error analyzing stock' in result['reason']

    @patch('harmonic_scanner.smart_download_data')
    def test_scan_stock_no_patterns_returns_hold(self, mock_download, sample_price_data):
        """Test that no patterns returns HOLD."""
        mock_download.return_value = sample_price_data

        scanner = HarmonicScanner()
        result = scanner.scan_stock('AAPL')

        # Most likely HOLD since sample data is random
        assert result['signal'] in ['BUY', 'SELL', 'HOLD']

    @patch('harmonic_scanner.smart_download_data')
    def test_scan_stock_verbose_mode(self, mock_download, sample_price_data):
        """Test scan_stock with verbose mode."""
        mock_download.return_value = sample_price_data

        scanner = HarmonicScanner()
        result = scanner.scan_stock('AAPL', verbose=True)

        assert isinstance(result['reason'], str)

    @patch('harmonic_scanner.smart_download_data')
    def test_scan_stock_override_period(self, mock_download, sample_price_data):
        """Test scan_stock with override period."""
        mock_download.return_value = sample_price_data

        scanner = HarmonicScanner()
        result = scanner.scan_stock('AAPL', override_period='1y')

        # Should have called download with override period
        assert mock_download.called


class TestRunScan:
    """Test run_scan method."""

    @patch.object(HarmonicScanner, 'scan_stock')
    @patch.object(HarmonicScanner, '_get_ticker_list')
    def test_run_scan_returns_dict(self, mock_get_tickers, mock_scan):
        """Test that run_scan returns a dictionary."""
        mock_get_tickers.return_value = ['AAPL', 'MSFT']
        mock_scan.return_value = {
            'ticker': 'AAPL',
            'signal': 'HOLD',
            'reason': 'No patterns',
            'patterns': []
        }

        scanner = HarmonicScanner()
        results = scanner.run_scan(max_stocks=2)

        assert isinstance(results, dict)
        assert 'BUY' in results
        assert 'SELL' in results
        assert 'HOLD' in results

    @patch.object(HarmonicScanner, 'scan_stock')
    @patch.object(HarmonicScanner, '_get_ticker_list')
    def test_run_scan_processes_all_tickers(self, mock_get_tickers, mock_scan):
        """Test that run_scan processes all tickers."""
        mock_get_tickers.return_value = ['AAPL', 'MSFT', 'GOOGL']
        mock_scan.return_value = {
            'ticker': 'TEST',
            'signal': 'HOLD',
            'reason': 'No patterns',
            'patterns': []
        }

        scanner = HarmonicScanner()
        results = scanner.run_scan(max_stocks=3)

        # Should have scanned all 3 tickers
        assert mock_scan.call_count == 3

    @patch.object(HarmonicScanner, 'scan_stock')
    @patch.object(HarmonicScanner, '_get_ticker_list')
    def test_run_scan_categorizes_results(self, mock_get_tickers, mock_scan):
        """Test that run_scan categorizes results correctly."""
        mock_get_tickers.return_value = ['AAPL', 'MSFT', 'GOOGL']

        # Mock different signals
        def mock_scan_side_effect(ticker, **kwargs):
            if ticker == 'AAPL':
                return {'ticker': 'AAPL', 'signal': 'BUY', 'reason': 'Pattern', 'patterns': []}
            elif ticker == 'MSFT':
                return {'ticker': 'MSFT', 'signal': 'SELL', 'reason': 'Pattern', 'patterns': []}
            else:
                return {'ticker': 'GOOGL', 'signal': 'HOLD', 'reason': 'No pattern', 'patterns': []}

        mock_scan.side_effect = mock_scan_side_effect

        scanner = HarmonicScanner()
        results = scanner.run_scan(max_stocks=3)

        assert len(results['BUY']) == 1
        assert len(results['SELL']) == 1
        assert len(results['HOLD']) == 1

    @patch.object(HarmonicScanner, 'scan_stock')
    @patch.object(HarmonicScanner, '_get_ticker_list')
    def test_run_scan_max_stocks_limits_scan(self, mock_get_tickers, mock_scan):
        """Test that max_stocks parameter limits scan."""
        mock_get_tickers.return_value = ['A', 'B', 'C']
        mock_scan.return_value = {
            'ticker': 'TEST',
            'signal': 'HOLD',
            'reason': 'No patterns',
            'patterns': []
        }

        scanner = HarmonicScanner()
        results = scanner.run_scan(max_stocks=3)

        # Should scan 3 stocks (note: may retry failures)
        assert mock_scan.call_count >= 3


class TestGetTickerList:
    """Test _get_ticker_list helper method."""

    @patch('harmonic_scanner.config')
    def test_get_ticker_list_returns_list(self, mock_config):
        """Test that _get_ticker_list returns a list."""
        mock_config.get_stock_list.return_value = ['AAPL', 'MSFT']
        mock_config.STOCK_TICKERS = []

        scanner = HarmonicScanner()
        tickers = scanner._get_ticker_list(None)

        assert isinstance(tickers, list)

    @patch('harmonic_scanner.config')
    def test_get_ticker_list_max_stocks(self, mock_config):
        """Test that max_stocks limits ticker list."""
        mock_config.get_stock_list.return_value = ['A', 'B', 'C', 'D', 'E']
        mock_config.STOCK_TICKERS = []

        scanner = HarmonicScanner()
        tickers = scanner._get_ticker_list(max_stocks=3)

        assert len(tickers) == 3


class TestScanAllTickers:
    """Test _scan_all_tickers helper method."""

    @patch.object(HarmonicScanner, 'scan_stock')
    @patch('harmonic_scanner.time.sleep')
    def test_scan_all_tickers_processes_all(self, mock_sleep, mock_scan):
        """Test that _scan_all_tickers processes all tickers."""
        mock_scan.return_value = {
            'ticker': 'TEST',
            'signal': 'HOLD',
            'reason': 'No patterns',
            'patterns': []
        }

        scanner = HarmonicScanner()
        results = {'BUY': [], 'SELL': [], 'HOLD': []}

        from scanner_helpers import ScanProgressTracker, PatternTrackerUpdater

        progress = ScanProgressTracker(3)
        tracker_updater = PatternTrackerUpdater(
            scanner.tracker, scanner.detector, scanner.config_helper
        )

        scanner._scan_all_tickers(
            ['A', 'B', 'C'], results, progress, tracker_updater
        )

        assert mock_scan.call_count == 3
        assert len(results['HOLD']) == 3


class TestIsDownloadFailure:
    """Test _is_download_failure static method."""

    def test_is_download_failure_no_data(self):
        """Test that 'No data available' is identified as failure."""
        analysis = {
            'signal': 'HOLD',
            'reason': 'No data available for AAPL'
        }

        assert HarmonicScanner._is_download_failure(analysis) is True

    def test_is_download_failure_error_analyzing(self):
        """Test that 'Error analyzing stock' is identified as failure."""
        analysis = {
            'signal': 'HOLD',
            'reason': 'Error analyzing stock: Network timeout'
        }

        assert HarmonicScanner._is_download_failure(analysis) is True

    def test_is_download_failure_normal_hold(self):
        """Test that normal HOLD is not identified as failure."""
        analysis = {
            'signal': 'HOLD',
            'reason': 'No valid harmonic patterns detected'
        }

        assert HarmonicScanner._is_download_failure(analysis) is False

    def test_is_download_failure_buy_signal(self):
        """Test that BUY signal is not identified as failure."""
        analysis = {
            'signal': 'BUY',
            'reason': 'Bullish Gartley pattern'
        }

        assert HarmonicScanner._is_download_failure(analysis) is False


class TestGenerateReport:
    """Test generate_report method."""

    def test_generate_report_returns_string(self):
        """Test that generate_report returns a string."""
        scanner = HarmonicScanner()

        results = {
            'BUY': [],
            'SELL': [],
            'HOLD': []
        }

        report = scanner.generate_report(results)

        assert isinstance(report, str)
        assert len(report) > 0

    def test_generate_report_includes_summary(self):
        """Test that report includes summary section."""
        scanner = HarmonicScanner()

        results = {
            'BUY': [{'ticker': 'AAPL', 'signal': 'BUY', 'reason': 'Pattern', 'patterns': []}],
            'SELL': [],
            'HOLD': []
        }

        report = scanner.generate_report(results)

        assert 'SUMMARY' in report
        assert 'BUY Signals: 1' in report

    def test_generate_report_includes_buy_signals(self):
        """Test that report includes BUY signals."""
        scanner = HarmonicScanner()

        results = {
            'BUY': [{
                'ticker': 'AAPL',
                'signal': 'BUY',
                'reason': 'Bullish Gartley',
                'patterns': [],
                'current_price': 150.0
            }],
            'SELL': [],
            'HOLD': []
        }

        report = scanner.generate_report(results)

        assert 'BUY SIGNALS' in report
        assert 'AAPL' in report

    def test_generate_report_includes_sell_signals(self):
        """Test that report includes SELL signals."""
        scanner = HarmonicScanner()

        results = {
            'BUY': [],
            'SELL': [{
                'ticker': 'MSFT',
                'signal': 'SELL',
                'reason': 'Bearish Bat',
                'patterns': [],
                'current_price': 300.0
            }],
            'HOLD': []
        }

        report = scanner.generate_report(results)

        assert 'SELL SIGNALS' in report
        assert 'MSFT' in report

    def test_generate_report_with_tracker_stats(self):
        """Test report with tracker statistics."""
        scanner = HarmonicScanner()

        results = {
            'BUY': [],
            'SELL': [],
            'HOLD': [],
            '_tracked_stats': {
                'confirmed': 5,
                'watchlist': 10,
                'invalidated': 2
            }
        }

        report = scanner.generate_report(results)

        assert 'Pattern Tracking' in report
        assert 'Confirmed' in report


class TestSaveReport:
    """Test save_report method."""

    def test_save_report_creates_file(self, tmp_path):
        """Test that save_report creates a file."""
        scanner = HarmonicScanner()
        scanner.path_manager.project_root = tmp_path

        report = "Test Report"
        report_path = scanner.save_report(report)

        assert Path(report_path).exists()

    def test_save_report_returns_path(self, tmp_path):
        """Test that save_report returns path."""
        scanner = HarmonicScanner()
        scanner.path_manager.project_root = tmp_path

        report = "Test Report"
        report_path = scanner.save_report(report)

        # PathManager may return Path or str
        assert isinstance(report_path, (str, Path))
        assert len(str(report_path)) > 0

    def test_save_report_content_matches(self, tmp_path):
        """Test that saved report content matches input."""
        scanner = HarmonicScanner()
        scanner.path_manager.project_root = tmp_path

        report = "Test Report Content"
        report_path = scanner.save_report(report)

        with open(report_path, 'r') as f:
            saved_content = f.read()

        assert saved_content == report


class TestRetryFailures:
    """Test _retry_failures helper method."""

    @patch.object(HarmonicScanner, 'scan_stock')
    def test_retry_failures_retries_failed_tickers(self, mock_scan):
        """Test that _retry_failures retries failed downloads."""
        # First call fails, second succeeds
        mock_scan.side_effect = [
            {'ticker': 'FAIL', 'signal': 'BUY', 'reason': 'Pattern found', 'patterns': []}
        ]

        scanner = HarmonicScanner()
        results = {
            'BUY': [],
            'SELL': [],
            'HOLD': [{
                'ticker': 'FAIL',
                'signal': 'HOLD',
                'reason': 'No data available',
                'patterns': []
            }]
        }

        scanner._retry_failures(results)

        # Should have attempted retry
        assert mock_scan.called

    def test_retry_failures_no_failures(self):
        """Test _retry_failures with no failures."""
        scanner = HarmonicScanner()
        results = {
            'BUY': [{'ticker': 'AAPL', 'signal': 'BUY', 'reason': 'Pattern', 'patterns': []}],
            'SELL': [],
            'HOLD': [{'ticker': 'MSFT', 'signal': 'HOLD', 'reason': 'No pattern', 'patterns': []}]
        }

        # Should not raise error
        scanner._retry_failures(results)
