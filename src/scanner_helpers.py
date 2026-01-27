"""
Helper classes for HarmonicScanner to reduce method complexity.

This module contains extracted helper classes that break down the long
run_scan() method into smaller, more testable components.
"""

from typing import Dict, List, Optional, Tuple
from datetime import datetime
import time

import pandas as pd

from logging_config import get_logger
from exceptions import DataDownloadError, PatternDetectionError
from utils import ConfigHelper

logger = get_logger(__name__)


class ScanProgressTracker:
    """
    Tracks and reports scan progress.

    Responsibilities:
    - Report progress at intervals
    - Track success/failure counts
    - Generate summary statistics
    """

    def __init__(self, total_tickers: int, report_interval: int = 10):
        """
        Initialize progress tracker.

        Args:
            total_tickers: Total number of tickers to scan
            report_interval: Report progress every N tickers
        """
        self.total_tickers = total_tickers
        self.report_interval = report_interval
        self.current_index = 0
        self.start_time = datetime.now()

    def update(self, index: int, ticker: str) -> None:
        """
        Update progress and report if at interval.

        Args:
            index: Current ticker index (1-based)
            ticker: Ticker symbol being processed
        """
        self.current_index = index

        if index % self.report_interval == 0:
            elapsed = (datetime.now() - self.start_time).total_seconds()
            rate = index / elapsed if elapsed > 0 else 0
            remaining = self.total_tickers - index
            eta_seconds = remaining / rate if rate > 0 else 0

            logger.info(
                f"Progress: {index}/{self.total_tickers} tickers "
                f"({index/self.total_tickers*100:.1f}%) | "
                f"Rate: {rate:.1f} tickers/sec | "
                f"ETA: {eta_seconds/60:.1f} min"
            )

    def get_summary(self) -> Dict[str, float]:
        """
        Get scan summary statistics.

        Returns:
            Dictionary with duration and rate statistics
        """
        elapsed = (datetime.now() - self.start_time).total_seconds()
        rate = self.current_index / elapsed if elapsed > 0 else 0

        return {
            'duration_seconds': elapsed,
            'duration_minutes': elapsed / 60,
            'tickers_processed': self.current_index,
            'rate_per_second': rate
        }


class FailedDownloadRetrier:
    """
    Handles retry logic for failed ticker downloads.

    Responsibilities:
    - Identify failed downloads
    - Retry with fallback parameters
    - Update results with successful retries
    """

    def __init__(
        self,
        scanner,
        fallback_period: str = 'max',
        max_retries: int = 1
    ):
        """
        Initialize retry handler.

        Args:
            scanner: HarmonicScanner instance
            fallback_period: Period to use for retries (e.g., 'max', '1y')
            max_retries: Maximum retry attempts per ticker
        """
        self.scanner = scanner
        self.fallback_period = fallback_period
        self.max_retries = max_retries

    def identify_failed_tickers(
        self,
        results: Dict[str, List[Dict]]
    ) -> List[str]:
        """
        Identify tickers that failed to download.

        Args:
            results: Scan results dictionary

        Returns:
            List of ticker symbols that failed
        """
        failed_tickers = []

        for analysis in results.get('HOLD', []):
            is_download_failure = (
                'No data available' in analysis.get('reason', '') or
                'Error analyzing stock' in analysis.get('reason', '')
            )

            if is_download_failure:
                failed_tickers.append(analysis['ticker'])

        return failed_tickers

    def retry_failed(
        self,
        failed_tickers: List[str],
        results: Dict[str, List[Dict]]
    ) -> Tuple[int, int]:
        """
        Retry failed downloads and update results.

        Args:
            failed_tickers: List of tickers to retry
            results: Results dictionary to update

        Returns:
            Tuple of (success_count, failure_count)
        """
        if not failed_tickers:
            return 0, 0

        logger.info(f"Retrying {len(failed_tickers)} failed downloads...")

        success_count = 0
        failure_count = 0

        for ticker in failed_tickers:
            retry_analysis = self.scanner.scan_stock(
                ticker,
                verbose=False,
                override_period=self.fallback_period
            )

            # Check if retry succeeded
            is_still_failed = (
                retry_analysis['signal'] == 'HOLD' and
                ('No data available' in retry_analysis['reason'] or
                 'Error analyzing stock' in retry_analysis['reason'])
            )

            if not is_still_failed:
                # Remove old failed result
                results['HOLD'] = [
                    r for r in results['HOLD']
                    if r['ticker'] != ticker
                ]
                # Add successful retry
                results[retry_analysis['signal']].append(retry_analysis)
                success_count += 1
                logger.debug(f"Retry succeeded for {ticker}")
            else:
                failure_count += 1

        if success_count > 0:
            logger.info(
                f"Retry summary: {success_count}/{len(failed_tickers)} succeeded"
            )

        return success_count, failure_count


class PatternTrackerUpdater:
    """
    Handles pattern tracker updates during scanning.

    Responsibilities:
    - Update tracker with detected patterns
    - Detect forming patterns
    - Collect tracking statistics
    """

    def __init__(
        self,
        tracker,
        detector,
        config_helper: ConfigHelper
    ):
        """
        Initialize tracker updater.

        Args:
            tracker: PatternTracker instance
            detector: PatternDetector instance
            config_helper: ConfigHelper for configuration access
        """
        self.tracker = tracker
        self.detector = detector
        self.config_helper = config_helper
        self.stats = {
            'confirmed': 0,
            'watchlist': 0,
            'invalidated': 0
        }

    def update_for_ticker(
        self,
        ticker: str,
        completed_patterns: List,
        df: pd.DataFrame,
        smart_download_data
    ) -> None:
        """
        Update pattern tracker for a single ticker.

        Args:
            ticker: Ticker symbol
            completed_patterns: List of completed patterns
            df: Price dataframe
            smart_download_data: Data download function
        """
        try:
            # Collect all patterns (completed + forming)
            all_patterns = self._collect_all_patterns(
                ticker,
                completed_patterns,
                df,
                smart_download_data
            )

            if all_patterns:
                current_date = datetime.now()
                tracked = self.tracker.update_patterns(
                    ticker=ticker,
                    detected_patterns=all_patterns,
                    price_data=df,
                    current_date=current_date
                )

                # Update statistics
                self.stats['confirmed'] += len(tracked.get('confirmed', []))
                self.stats['watchlist'] += len(tracked.get('watchlist', []))
                self.stats['invalidated'] += len(tracked.get('invalidated', []))

        except Exception as e:
            logger.debug(f"Could not update tracker for {ticker}: {e}")

    def _collect_all_patterns(
        self,
        ticker: str,
        completed_patterns: List,
        df: pd.DataFrame,
        smart_download_data
    ) -> List:
        """
        Collect both completed and forming patterns.

        Args:
            ticker: Ticker symbol
            completed_patterns: List of completed patterns
            df: Price dataframe
            smart_download_data: Data download function

        Returns:
            Combined list of all patterns
        """
        all_patterns = list(completed_patterns) if completed_patterns else []

        # Detect forming patterns
        try:
            forming_patterns = self._detect_forming_patterns(
                ticker,
                df,
                smart_download_data
            )
            all_patterns.extend(forming_patterns)
        except Exception as e:
            logger.debug(f"Could not detect forming patterns for {ticker}: {e}")

        return all_patterns

    def _detect_forming_patterns(
        self,
        ticker: str,
        df: pd.DataFrame,
        smart_download_data
    ) -> List:
        """
        Detect patterns that are 85-100% complete.

        Args:
            ticker: Ticker symbol
            df: Price dataframe (may not have full history)
            smart_download_data: Data download function

        Returns:
            List of forming patterns
        """
        from pyharmonics import OHLCTechnicals as Technicals
        from pyharmonics.search import HarmonicSearch

        forming_patterns = []

        # Use provided df if available and non-empty, otherwise download
        if df is not None and not df.empty:
            df_full = df
        else:
            # Download data with retry logic
            data_interval = self.config_helper.get('DATA_INTERVAL', '1wk')
            data_period = self.config_helper.get('DATA_PERIOD', '2y')
            max_retries = self.config_helper.get_int('MAX_DOWNLOAD_RETRIES', 3)

            df_full = smart_download_data(
                ticker=ticker,
                period=data_period,
                interval=data_interval,
                auto_adjust=False,
                max_retries=max_retries
            )

        if df_full.empty:
            return forming_patterns

        # Ensure columns are lowercase
        df_full.columns = [c.lower() for c in df_full.columns]

        # Search for forming patterns
        swing_window = self.config_helper.get_int('SWING_WINDOW', 3)
        tech = Technicals(df_full, ticker, data_interval, peak_spacing=swing_window)

        fib_tolerance = self.config_helper.get_float('PYHARMONICS_FIB_TOLERANCE', 0.03)
        h = HarmonicSearch(tech, fib_tolerance=fib_tolerance, check_anchor=True)

        # Detect patterns 85% complete
        h.forming(limit_to=10, percent_c_to_d=0.95)
        forming = h.get_patterns(family=h.XABCD, formed=False)

        # Convert to HarmonicPattern objects
        for py_pattern in forming.get(h.XABCD, []):
            converted = self.detector._convert_pyharmonics_pattern(
                py_pattern,
                df_full,
                tech,
                fib_tolerance,
                ticker
            )
            if converted:
                forming_patterns.append(converted)

        return forming_patterns

    def get_stats(self) -> Dict[str, int]:
        """
        Get tracking statistics.

        Returns:
            Dictionary with confirmed, watchlist, invalidated counts
        """
        return self.stats.copy()


class ScanResultsFormatter:
    """
    Formats scan results for display.

    Responsibilities:
    - Generate scan summary
    - Format result counts
    - Create status messages
    """

    @staticmethod
    def print_header(config_module) -> None:
        """
        Print scan header with configuration.

        Args:
            config_module: Configuration module
        """
        logger.info("=" * 80)
        logger.info("IMPROVED HARMONIC PATTERN SCANNER")
        logger.info("Pyharmonics Peak Detection + Scott Carney's Exact Rules")
        logger.info("=" * 80)
        logger.info("")

        # Print configuration summary
        if hasattr(config_module, 'get_settings_summary'):
            config_module.get_settings_summary()

    @staticmethod
    def print_summary(
        results: Dict[str, List[Dict]],
        tracker_stats: Dict[str, int]
    ) -> None:
        """
        Print scan completion summary.

        Args:
            results: Scan results dictionary
            tracker_stats: Pattern tracking statistics
        """
        logger.info("")
        logger.info("=" * 80)
        logger.info("SCAN COMPLETE")
        logger.info("=" * 80)
        logger.info(f"BUY signals: {len(results['BUY'])}")
        logger.info(f"SELL signals: {len(results['SELL'])}")
        logger.info(f"HOLD signals: {len(results['HOLD'])}")
        logger.info("")
        logger.info("PATTERN TRACKING:")
        logger.info(f"Confirmed patterns (Type 1/2): {tracker_stats.get('confirmed', 0)}")
        logger.info(f"Watchlist (forming patterns): {tracker_stats.get('watchlist', 0)}")
        logger.info(f"Invalidated (D extended): {tracker_stats.get('invalidated', 0)}")
        logger.info("")

    @staticmethod
    def get_ticker_list(config_module, max_stocks: Optional[int]) -> List[str]:
        """
        Get ticker list using config settings.

        Args:
            config_module: Configuration module
            max_stocks: Optional limit on tickers

        Returns:
            List of ticker symbols
        """
        tickers = config_module.get_stock_list()

        if max_stocks:
            tickers = tickers[:max_stocks]

        logger.info(f"Total tickers to scan: {len(tickers)}")
        logger.info("This may take several minutes...")
        logger.info("")

        return tickers
