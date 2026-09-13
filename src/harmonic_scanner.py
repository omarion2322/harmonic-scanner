"""
Hybrid Harmonic Pattern Scanner
Combines Pyharmonics peak detection with Scott Carney's exact trading framework from Volumes 1-3

Usage:
    python harmonic_scanner.py
"""

import pandas as pd
from datetime import datetime
import warnings
from typing import List, Dict, Optional, Any
import time
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
import threading
import multiprocessing

from pattern_detector import PatternDetector
from reaction_detector import ReactionDetector
from data_downloader import download_stock_data
from crypto_data_downloader import download_crypto_data
from pattern_tracker import PatternTracker, PatternStatus
from utils import ConfigHelper, PathManager, FormattingUtils, TickerManager
from logging_config import get_logger
from sector_etf_analyzer import SectorETFAnalyzer
from scanner_helpers import (
    ScanProgressTracker,
    FailedDownloadRetrier,
    PatternTrackerUpdater,
    ScanResultsFormatter
)

logger = get_logger(__name__)


def smart_download_data(ticker: str, **kwargs) -> pd.DataFrame:
    """
    Smart data downloader that automatically selects the right source.

    - Crypto tickers (ending with -USD): Uses crypto_data_downloader with cascading fallbacks
    - Stock tickers: Uses regular data_downloader

    Args:
        ticker: Ticker symbol
        **kwargs: Additional arguments passed to the downloader

    Returns:
        DataFrame with OHLCV data
    """
    # Detect crypto tickers (end with -USD and not a stock)
    # Most stocks don't end with -USD, this is a crypto pattern
    if ticker.endswith('-USD'):
        # Use crypto downloader with cascading fallbacks
        return download_crypto_data(ticker=ticker, **kwargs)
    else:
        # Use regular stock downloader
        return download_stock_data(ticker=ticker, **kwargs)

warnings.filterwarnings('ignore')

logger.info("Modules loaded successfully")


def _scan_single_ticker(ticker: str, verbose: bool = False, asset_type: str = 'stocks') -> Dict[str, Any]:
    """
    Module-level function for scanning a single ticker (used by ProcessPoolExecutor).

    This function must be at module level to be picklable for multiprocessing.

    Args:
        ticker: Stock ticker symbol
        verbose: Whether to generate verbose reports
        asset_type: Asset type ('stocks' or 'crypto')

    Returns:
        Analysis dictionary
    """
    try:
        scanner = HarmonicScanner(asset_type=asset_type)
        return scanner.scan_stock(ticker, verbose=verbose)
    except Exception as e:
        logger.error(f"Unexpected error scanning {ticker}: {e}", exc_info=True)
        return {
            'ticker': ticker,
            'signal': 'HOLD',
            'reason': f'Error analyzing stock: {str(e)}',
            'patterns': [],
            'chart_path': None
        }

# Import configuration
try:
    import config  # type: ignore
except ImportError:
    class config:  # type: ignore
        MAX_STOCKS_TO_SCAN = 50
        MAX_DAYS_TO_INITIAL_ENTRY = 10
        MAX_DAYS_SINCE_PATTERN = 10
        MAX_BARS_TO_MONITOR_REACTION = 30


class HarmonicScanner:
    """
    Scans S&P 500 stocks for harmonic patterns using hybrid approach:
    - Pyharmonics for peak/trough detection
    - Scott Carney's exact rules for pattern validation and trading signals (Volumes 1-3)

    Improvements:
    - Pattern-specific B point validation with tolerances
    - "Great Gartley Controversy" differentiation (BC > 1.618 = Bat)
    - I.P.O. (Initial Profit Objective) from pattern range
    - Pattern-specific stop losses
    - PRZ (Potential Reversal Zone) calculation
    - Pattern quality assessment
    """

    def __init__(self, asset_type: str = 'stocks') -> None:
        self.detector = PatternDetector()  # Uses Carney's exact specifications

        # Initialize utility helpers
        self.config_helper = ConfigHelper(config)
        max_reaction_bars = self.config_helper.get_int('MAX_BARS_TO_MONITOR_REACTION', 30)
        retest_tolerance = (
            self.config_helper.get_float('TYPE2_RETEST_TOLERANCE_PCT', 2.0) / 100.0
        )
        self.reaction_detector = ReactionDetector(
            max_type2_bars=max_reaction_bars,
            type2_retest_tolerance=retest_tolerance,
        )
        self.tracker = PatternTracker(storage_dir="./pattern_tracking")
        self.tracker.MAX_REACTION_BARS = max_reaction_bars
        self.tracker.TYPE2_RETEST_TOLERANCE = retest_tolerance
        self.path_manager = PathManager()
        self.asset_type = asset_type  # 'stocks' or 'crypto' - determines report directory
        self.sector_etf_analyzer = SectorETFAnalyzer()

    def get_sp500_tickers(self) -> List[str]:
        """
        Fetch S&P 500 ticker list from SlickCharts.com
        Prepends custom tickers from config.STOCK_TICKERS (scanned first) if they exist
        Returns list: [custom tickers] + [S&P 500 tickers with duplicates removed]
        """
        try:
            url = 'https://www.slickcharts.com/sp500'
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }

            tables = pd.read_html(url, storage_options=headers)
            df = tables[0]

            if 'Symbol' in df.columns:
                sp500_tickers = df['Symbol'].tolist()
                sp500_tickers = [str(ticker).strip().replace('.', '-') for ticker in sp500_tickers
                          if pd.notna(ticker)]
                logger.info("Successfully fetched %d S&P 500 tickers from SlickCharts", len(sp500_tickers))

                # Merge custom tickers with S&P 500 using TickerManager
                custom_tickers = self.config_helper.get('STOCK_TICKERS')
                tickers = TickerManager.merge_ticker_lists(custom_tickers, sp500_tickers)
                TickerManager.print_custom_ticker_info(custom_tickers)

                return tickers
            else:
                raise Exception("Symbol column not found")

        except (ValueError, pd.errors.ParserError) as e:
            logger.error("Error parsing S&P 500 list from SlickCharts: %s", e)
            logger.info("Using fallback list of major stocks")
        except (OSError, IOError) as e:
            logger.error("Network error fetching S&P 500 list from SlickCharts: %s", e)
            logger.info("Using fallback list of major stocks")
        except Exception as e:
            logger.error("Unexpected error fetching S&P 500 list from SlickCharts: %s", e)
            logger.info("Using fallback list of major stocks")

            # Fallback list of major stocks
            fallback_sp500 = [
                'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA', 'BRK-B',
                'UNH', 'JNJ', 'XOM', 'V', 'PG', 'MA', 'HD', 'CVX', 'MRK', 'ABBV',
                'PEP', 'KO', 'AVGO', 'COST', 'WMT', 'LLY', 'TMO', 'MCD', 'ACN',
                'CSCO', 'ABT', 'DHR', 'VZ', 'NEE', 'ADBE', 'NKE', 'CRM', 'TXN',
                'PM', 'UNP', 'ORCL', 'LIN', 'DIS', 'COP', 'BMY', 'WFC', 'QCOM',
                'RTX', 'HON', 'INTC', 'UPS', 'AMGN'
            ]

            # Merge custom tickers with fallback list using TickerManager
            custom_tickers = self.config_helper.get('STOCK_TICKERS')
            fallback_tickers = TickerManager.merge_ticker_lists(custom_tickers, fallback_sp500)
            TickerManager.print_custom_ticker_info(custom_tickers)

            return fallback_tickers

    def scan_stock(self, ticker: str, verbose: Optional[bool] = None, override_period: Optional[str] = None) -> Dict[str, Any]:
        """
        Scan a single stock for harmonic patterns using hybrid detector.

        Args:
            ticker: Stock ticker symbol
            verbose: If True, generate detailed explanations (defaults to config.VERBOSE_REPORTS)
            override_period: Optional data period override (for fallback retries)

        Returns:
            Dictionary with analysis results
        """
        # Use config setting if not explicitly provided
        if verbose is None:
            verbose = self.config_helper.get('VERBOSE_REPORTS', False)

        try:
            # Download data using config settings with retry logic
            data_interval = self.config_helper.get('DATA_INTERVAL', '1d')

            # Always use DATA_PERIOD for pattern detection (performance optimization)
            # For MITCH strategy with scoring engine, we'll download max history separately for S/R analysis
            # Use override_period if provided (for fallback retries)
            data_period = override_period if override_period else self.config_helper.get('DATA_PERIOD', '6mo')

            # Get retry configuration
            max_retries = self.config_helper.get_int('MAX_DOWNLOAD_RETRIES', 3)
            download_delay = self.config_helper.get_float('DOWNLOAD_DELAY', 0.1)

            # Use auto_adjust=False to get actual NYSE trading prices (not dividend-adjusted)
            # smart_download_data automatically uses crypto downloader for -USD tickers
            df = smart_download_data(
                ticker=ticker,
                period=data_period,
                interval=data_interval,
                auto_adjust=False,
                max_retries=max_retries
            )

            # Apply rate limiting delay
            if download_delay > 0:
                time.sleep(download_delay)

            # Check if download succeeded
            if df.empty:
                return {
                    'ticker': ticker,
                    'signal': 'HOLD',
                    'reason': f'No data available for {ticker}',
                    'patterns': [],
                    'current_price': None
                }

            # Pyharmonics requires lowercase columns
            df.columns = [c.lower() for c in df.columns]

            # Detect patterns using hybrid detector
            patterns = self.detector.detect_patterns(df, ticker, interval=data_interval)

            if not patterns:
                no_pattern_msg = f'No harmonic patterns detected for {ticker} that meet Carney\'s exact specifications (checked {len(df)} bars)' if verbose else 'No valid harmonic patterns detected'
                return {
                    'ticker': ticker,
                    'signal': 'HOLD',
                    'reason': no_pattern_msg,
                    'patterns': [],
                    'current_price': df['close'].iloc[-1],
                    'chart_path': None
                }

            # Get current price
            current_price = df['close'].iloc[-1]

            # Evaluate the most recent pattern for a fresh initial entry.
            latest_pattern = patterns[0]

            # Calculate age and reaction state for every completed pattern.
            today = datetime.now().date()
            current_idx = len(df) - 1
            max_reaction_bars = self.config_helper.get_int(
                'MAX_BARS_TO_MONITOR_REACTION', 30
            )
            reaction_records = []
            for pattern in patterns:
                pattern_date = (
                    pattern.d.date.date()
                    if hasattr(pattern.d.date, 'date')
                    else pattern.d.date
                )
                pattern.days_since_completion = (today - pattern_date).days
                reaction = self.reaction_detector.detect_reaction(
                    df, pattern, current_idx
                )
                if (
                    reaction is not None
                    and reaction.bars_since_completion <= max_reaction_bars
                ):
                    reaction_records.append({
                        'pattern': pattern,
                        'reaction_data': reaction,
                    })

            latest_reaction = next(
                (
                    record['reaction_data']
                    for record in reaction_records
                    if record['pattern'] is latest_pattern
                ),
                None,
            )
            type2_confirmations = [
                self._build_type2_record(record, current_idx)
                for record in reaction_records
                if record['reaction_data'].reaction_type == 'TYPE_2'
            ]
            type2_candidates = [
                self._build_type2_record(record, current_idx)
                for record in reaction_records
                if record['reaction_data'].reaction_type == 'TYPE_2_CANDIDATE'
            ]

            max_initial_entry_age = self.config_helper.get_int(
                'MAX_DAYS_TO_INITIAL_ENTRY',
                self.config_helper.get_int('MAX_DAYS_SINCE_PATTERN', 730),
            )
            signal, explanation = self.detector.generate_signal(
                latest_pattern,
                current_price,
                max_days_old=max_initial_entry_age,
                verbose=verbose
            )

            signal_pattern = latest_pattern
            reaction_data = latest_reaction
            signal_source = 'INITIAL_ENTRY'
            confirmation_freshness = self.config_helper.get_int(
                'TYPE2_ENTRY_MAX_BARS_AFTER_CONFIRMATION', 1
            )
            actionable_type2 = [
                record for record in type2_confirmations
                if record['bars_since_confirmation'] <= confirmation_freshness
                and not record['stop_hit']
                and record['risk_pct'] <= self.config_helper.get_float(
                    'MAX_ALLOWED_STOP_LOSS_PCT', 15.0
                )
            ]
            if actionable_type2:
                selected = max(
                    actionable_type2,
                    key=lambda record: record['confirmation_date'],
                )
                signal_pattern = selected['pattern']
                reaction_data = selected['reaction_data']
                signal = 'BUY' if signal_pattern.is_bullish else 'SELL'
                signal_source = 'TYPE_2'
                explanation = (
                    f"TYPE 2 confirmed on {selected['confirmation_date'].date()}: "
                    f"entry ${selected['entry_price']:.2f}, "
                    f"stop ${selected['stop_loss']:.2f}, "
                    f"targets ${selected['target_1']:.2f} / "
                    f"${selected['target_2']:.2f} / ${selected['target_3']:.2f}"
                )

            # Only generate a chart for an actionable signal.
            chart_path = None
            sector_etf_analysis = None
            auto_save_charts = self.config_helper.get_bool('AUTO_SAVE_CHARTS', True)

            if signal in ['BUY', 'SELL'] and auto_save_charts:
                if self.asset_type == 'stocks':
                    try:
                        sector_etf_analysis = self.sector_etf_analyzer.analyze(
                            ticker=ticker,
                            signal=signal,
                            interval=data_interval,
                            period=data_period,
                        )
                    except (KeyError, TypeError, ValueError) as e:
                        logger.warning(
                            "%s: Could not calculate sector ETF confluence: %s",
                            ticker,
                            e,
                        )

                # Get chart directory using PathManager
                chart_dir = str(self.path_manager.get_chart_dir(interval=data_interval, asset_type=self.asset_type))

                # Generate pattern chart
                try:
                    chart_path = self.detector.generate_pattern_chart(
                        signal_pattern, ticker, df, chart_dir,
                        interval=data_interval,
                        reaction_data=reaction_data,
                        sector_etf_analysis=sector_etf_analysis
                    )
                    signal_pattern.chart_path = chart_path
                except (OSError, IOError) as e:
                    logger.warning("Could not save chart for %s: %s", ticker, e)
                    chart_path = None
                except ValueError as e:
                    logger.warning("Invalid chart data for %s: %s", ticker, e)
                    chart_path = None
                except Exception as e:
                    logger.warning("Unexpected error generating chart for %s: %s", ticker, e)
                    chart_path = None

            return {
                'ticker': ticker,
                'signal': signal,
                'reason': explanation,
                'patterns': patterns,
                'current_price': current_price,
                'chart_path': chart_path,
                'reaction_data': reaction_data,
                'signal_pattern': signal_pattern,
                'signal_source': signal_source,
                'type2_confirmations': type2_confirmations,
                'type2_candidates': type2_candidates,
                'sector_etf_analysis': sector_etf_analysis,
                '_df': df  # Include DataFrame for pattern tracker (avoid re-download)
            }

        except (ValueError, KeyError) as e:
            # Data-related errors
            logger.debug("Data error analyzing %s: %s", ticker, e)
            return {
                'ticker': ticker,
                'signal': 'HOLD',
                'reason': f'Data error: {str(e)}',
                'patterns': [],
                'chart_path': None
            }
        except Exception as e:
            # Unexpected errors
            logger.warning("Unexpected error analyzing %s: %s", ticker, e, exc_info=True)
            return {
                'ticker': ticker,
                'signal': 'HOLD',
                'reason': f'Error analyzing stock: {str(e)}',
                'patterns': [],
                'chart_path': None
            }

    @staticmethod
    def _build_type2_record(
        reaction_record: Dict[str, Any],
        current_idx: int,
    ) -> Dict[str, Any]:
        """Build a reportable Type 2 candidate or confirmation."""
        pattern = reaction_record['pattern']
        reaction = reaction_record['reaction_data']
        confirmation_idx = reaction.type2_terminal_bar_idx
        bars_since_confirmation = (
            current_idx - confirmation_idx
            if confirmation_idx is not None
            else None
        )
        risk_pct = (
            abs(reaction.type2_entry_price - reaction.type2_stop_loss)
            / reaction.type2_entry_price
            * 100
            if reaction.type2_entry_price and reaction.type2_stop_loss
            else float('inf')
        )
        return {
            'pattern': pattern,
            'reaction_data': reaction,
            'ticker': getattr(pattern, 'ticker', None),
            'retest_date': reaction.type2_retest_date,
            'confirmation_date': reaction.type2_terminal_bar_date,
            'bars_since_confirmation': bars_since_confirmation,
            'entry_price': reaction.type2_entry_price,
            'stop_loss': reaction.type2_stop_loss,
            'target_1': reaction.type2_target_1,
            'target_2': reaction.type2_target_2,
            'target_3': reaction.type2_target_3,
            'forward_return_pct': reaction.type2_forward_return_pct,
            'stop_hit': reaction.type2_stop_hit,
            'risk_pct': risk_pct,
        }

    def run_scan(self, max_stocks: Optional[int] = None) -> Dict[str, List[Dict[str, Any]]]:
        """
        Scan S&P 500 stocks for harmonic patterns.

        Args:
            max_stocks: Maximum number of stocks to scan (None for all)

        Returns:
            Dictionary with BUY, SELL, HOLD lists
        """
        # Step 1: Print header and get ticker list
        ScanResultsFormatter.print_header(config)
        tickers = self._get_ticker_list(max_stocks)

        logger.info("Scanning %d stocks for harmonic patterns...", len(tickers))
        logger.info("This may take several minutes...")
        logger.info("")

        # Step 2: Initialize tracking
        results: Dict[str, List[Dict[str, Any]]] = {'BUY': [], 'SELL': [], 'HOLD': []}
        progress = ScanProgressTracker(len(tickers), report_interval=10)
        tracker_updater = PatternTrackerUpdater(self.tracker, self.detector, self.config_helper)

        # Step 3: Scan all tickers
        self._scan_all_tickers(tickers, results, progress, tracker_updater)

        # Step 4: Retry failures
        self._retry_failures(results)

        # Step 5: Print summary
        tracked_stats = tracker_updater.get_stats()
        ScanResultsFormatter.print_summary(results, tracked_stats)

        # Store tracker summary in results for report generation
        results['_tracker_summary'] = self.tracker.get_summary()  # type: ignore
        results['_tracked_stats'] = tracked_stats  # type: ignore

        return results

    def _get_ticker_list(self, max_stocks: Optional[int]) -> List[str]:
        """
        Get the list of tickers to scan.

        Args:
            max_stocks: Maximum number of stocks to scan

        Returns:
            List of ticker symbols
        """
        # Get custom tickers first
        custom_tickers = self.config_helper.get('STOCK_TICKERS')

        # If we have enough custom tickers to meet max_stocks, use only those
        if custom_tickers and max_stocks and len(custom_tickers) >= max_stocks:
            tickers = [t.upper().strip() for t in custom_tickers[:max_stocks]]
            logger.info("Using only custom tickers (%d of %d): %s",
                       len(tickers), len(custom_tickers), ', '.join(tickers))
            TickerManager.print_custom_ticker_info(custom_tickers[:max_stocks])
            return tickers

        # Otherwise, get ticker list from universe and merge
        tickers = config.get_stock_list()

        # Merge custom tickers with universe using TickerManager
        tickers = TickerManager.merge_ticker_lists(custom_tickers, tickers)
        TickerManager.print_custom_ticker_info(custom_tickers)

        logger.info("Total tickers to scan: %d", len(tickers))

        if max_stocks:
            tickers = tickers[:max_stocks]

        return tickers

    def _scan_all_tickers_parallel(
        self,
        tickers: List[str],
        results: Dict[str, List[Dict[str, Any]]],
        progress: ScanProgressTracker,
        tracker_updater: PatternTrackerUpdater
    ) -> None:
        """
        Scan all tickers in parallel using ThreadPoolExecutor or ProcessPoolExecutor.

        Args:
            tickers: List of ticker symbols
            results: Results dictionary to populate
            progress: Progress tracker
            tracker_updater: Pattern tracker updater
        """
        verbose = self.config_helper.get_bool('VERBOSE_REPORTS', False)
        max_workers = self.config_helper.get_int('PARALLEL_WORKERS', 20)
        parallel_mode = self.config_helper.get('PARALLEL_MODE', 'thread')

        # List to store all analyses for pattern tracker updates (done sequentially after)
        all_analyses = []

        # Choose executor type based on mode
        if parallel_mode == 'process':
            executor_class = ProcessPoolExecutor
            # Limit workers to CPU count for processes
            max_workers = min(max_workers, multiprocessing.cpu_count())
            logger.info(f"Starting parallel scan with {max_workers} processes (CPU-bound mode)...")

            # For ProcessPoolExecutor, use module-level function
            from functools import partial
            scan_func = partial(_scan_single_ticker, verbose=verbose, asset_type=self.asset_type)
        else:
            executor_class = ThreadPoolExecutor
            logger.info(f"Starting parallel scan with {max_workers} threads (I/O-bound mode)...")

            # Thread-safe lock for updating shared results dictionary
            results_lock = threading.Lock()
            analyses_lock = threading.Lock()

            # For ThreadPoolExecutor, use instance method
            def scan_ticker_wrapper(ticker: str) -> Dict[str, Any]:
                """Wrapper function for scanning a single ticker"""
                try:
                    analysis = self.scan_stock(ticker, verbose=verbose)
                    return analysis
                except Exception as e:
                    logger.error(f"Unexpected error scanning {ticker}: {e}", exc_info=True)
                    return {
                        'ticker': ticker,
                        'signal': 'HOLD',
                        'reason': f'Error analyzing stock: {str(e)}',
                        'patterns': [],
                        'chart_path': None
                    }
            scan_func = scan_ticker_wrapper

        # Submit all ticker scan jobs to executor
        with executor_class(max_workers=max_workers) as executor:
            # Create future-to-ticker mapping
            future_to_ticker = {
                executor.submit(scan_func, ticker): ticker
                for ticker in tickers
            }

            # Process completed scans as they finish
            completed_count = 0
            for future in as_completed(future_to_ticker):
                completed_count += 1
                ticker = future_to_ticker[future]

                try:
                    analysis = future.result()

                    # Update results (thread-safe for threads, no sharing for processes)
                    if parallel_mode == 'thread':
                        with results_lock:
                            results[analysis['signal']].append(analysis)
                        with analyses_lock:
                            all_analyses.append(analysis)
                    else:
                        # For processes, direct append (no sharing between processes)
                        results[analysis['signal']].append(analysis)
                        all_analyses.append(analysis)

                    # Update progress (thread-safe via logger)
                    progress.update(completed_count, ticker)

                except Exception as e:
                    logger.error(f"Error processing result for {ticker}: {e}", exc_info=True)

        logger.info("Parallel scanning complete. Updating pattern tracker...")

        # Update pattern tracker sequentially (file I/O is not thread-safe)
        for analysis in all_analyses:
            if not self._is_download_failure(analysis):
                try:
                    tracker_updater.update_for_ticker(
                        analysis['ticker'],
                        analysis.get('patterns', []),
                        analysis.get('_df'),  # Use already-downloaded DataFrame
                        smart_download_data
                    )
                except Exception as e:
                    logger.debug(f"Could not update tracker for {analysis['ticker']}: {e}")

        logger.info("Pattern tracker updates complete.")

    def _scan_all_tickers(
        self,
        tickers: List[str],
        results: Dict[str, List[Dict[str, Any]]],
        progress: ScanProgressTracker,
        tracker_updater: PatternTrackerUpdater
    ) -> None:
        """
        Scan all tickers with progress tracking and pattern tracker updates.

        This method routes to either parallel or sequential scanning based on config.

        Args:
            tickers: List of ticker symbols
            results: Results dictionary to populate
            progress: Progress tracker
            tracker_updater: Pattern tracker updater
        """
        # Check if parallel processing is enabled
        enable_parallel = self.config_helper.get_bool('ENABLE_PARALLEL_PROCESSING', True)

        if enable_parallel:
            # Use parallel scanning
            self._scan_all_tickers_parallel(tickers, results, progress, tracker_updater)
        else:
            # Use sequential scanning (original implementation)
            self._scan_all_tickers_sequential(tickers, results, progress, tracker_updater)

    def _scan_all_tickers_sequential(
        self,
        tickers: List[str],
        results: Dict[str, List[Dict[str, Any]]],
        progress: ScanProgressTracker,
        tracker_updater: PatternTrackerUpdater
    ) -> None:
        """
        Scan all tickers sequentially (original implementation).

        Args:
            tickers: List of ticker symbols
            results: Results dictionary to populate
            progress: Progress tracker
            tracker_updater: Pattern tracker updater
        """
        verbose = self.config_helper.get_bool('VERBOSE_REPORTS', False)

        for i, ticker in enumerate(tickers, 1):
            # Update progress
            progress.update(i, ticker)

            # Scan ticker
            analysis = self.scan_stock(ticker, verbose=verbose)
            results[analysis['signal']].append(analysis)

            # Update pattern tracker (if download succeeded)
            if not self._is_download_failure(analysis):
                tracker_updater.update_for_ticker(
                    ticker,
                    analysis.get('patterns', []),
                    analysis.get('_df'),  # Use already-downloaded DataFrame
                    smart_download_data
                )

            # Rate limiting delay
            delay = self.config_helper.get_float('DOWNLOAD_DELAY', 0.1)
            if delay > 0:
                time.sleep(delay)

    def _retry_failures(self, results: Dict[str, List[Dict[str, Any]]]) -> None:
        """
        Retry failed downloads with fallback period.

        Args:
            results: Results dictionary to update
        """
        retrier = FailedDownloadRetrier(self, fallback_period='max', max_retries=1)
        failed_tickers = retrier.identify_failed_tickers(results)

        if failed_tickers:
            logger.info("")
            retrier.retry_failed(failed_tickers, results)

    @staticmethod
    def _is_download_failure(analysis: Dict[str, Any]) -> bool:
        """
        Check if analysis represents a download failure.

        Args:
            analysis: Analysis dictionary

        Returns:
            True if download failed
        """
        return (
            analysis['signal'] == 'HOLD' and
            ('No data available' in analysis.get('reason', '') or
             'Error analyzing stock' in analysis.get('reason', ''))
        )

    def generate_report(self, results: Dict[str, List[Dict[str, Any]]]) -> str:
        """
        Generate formatted report from scan results.

        Args:
            results: Dictionary with BUY, SELL, HOLD lists

        Returns:
            Formatted report string
        """
        report_lines = []
        report_lines.append("="*80)
        report_lines.append("IMPROVED HARMONIC PATTERN SCANNER REPORT")
        report_lines.append("Scott Carney's Exact Specifications from Volumes 1, 2, and 3")
        report_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append("="*80)
        report_lines.append("")

        # Summary
        report_lines.append("SUMMARY")
        report_lines.append("-"*80)
        total_scanned = sum(len(v) for k, v in results.items() if not k.startswith('_'))
        report_lines.append(f"Total Stocks Scanned: {total_scanned}")
        report_lines.append(f"BUY Signals: {len(results['BUY'])}")
        report_lines.append(f"SELL Signals: {len(results['SELL'])}")
        report_lines.append(f"HOLD Signals: {len(results['HOLD'])}")
        type2_confirmed_count = sum(
            len(analysis.get('type2_confirmations', []))
            for signal in ('BUY', 'SELL', 'HOLD')
            for analysis in results[signal]
        )
        type2_candidate_count = sum(
            len(analysis.get('type2_candidates', []))
            for signal in ('BUY', 'SELL', 'HOLD')
            for analysis in results[signal]
        )
        report_lines.append(f"Type 2 Confirmed: {type2_confirmed_count}")
        report_lines.append(f"Type 2 Candidates: {type2_candidate_count}")

        # Add tracker stats if available
        tracked_stats_value: Any = results.get('_tracked_stats', {})
        if tracked_stats_value and isinstance(tracked_stats_value, dict):
            report_lines.append("")
            report_lines.append("Pattern Tracking:")
            report_lines.append(f"  Confirmed (Type 1/2 Reactions): {tracked_stats_value.get('confirmed', 0)}")
            report_lines.append(f"  Watchlist (Forming Patterns): {tracked_stats_value.get('watchlist', 0)}")
            report_lines.append(f"  Invalidated (D Extended): {tracked_stats_value.get('invalidated', 0)}")

        report_lines.append("")

        self._append_type2_sections(report_lines, results)

        # BUY signals
        direct_buy_signals = [
            analysis for analysis in results['BUY']
            if analysis.get('signal_source') != 'TYPE_2'
        ]
        if direct_buy_signals:
            report_lines.append("="*80)
            report_lines.append("BUY SIGNALS")
            report_lines.append("="*80)
            report_lines.append("")

            for analysis in direct_buy_signals:
                report_lines.append(f"Ticker: {analysis['ticker']}")
                report_lines.append(f"Current Price: ${analysis.get('current_price', 0):.2f}")
                report_lines.append(f"Analysis: {analysis['reason']}")

                if analysis['patterns']:
                    # Use patterns[0] - the pattern that was analyzed for the signal (not patterns[-1])
                    pattern = analysis.get('signal_pattern', analysis['patterns'][0])
                    report_lines.append("")
                    report_lines.append(f"  Pattern: {pattern.pattern_type.upper()} ({'BULLISH' if pattern.is_bullish else 'BEARISH'})")
                    report_lines.append(f"  Grade: {pattern.grade} | Tolerance: {pattern.tolerance_level}")

                    # Show D-point range (PRZ zone)
                    if hasattr(pattern, 'd_point_range_min') and pattern.d_point_range_min > 0:
                        range_from_entry = ((pattern.d_point_range_max - pattern.entry_price) / pattern.entry_price) * 100
                        report_lines.append(f"  Entry Zone (PRZ): ${pattern.d_point_range_min:.2f} - ${pattern.d_point_range_max:.2f} (±{range_from_entry:.1f}%)")

                    report_lines.append(f"  Entry: ${pattern.entry_price:.2f}")
                    report_lines.append(f"  Stop Loss: ${pattern.stop_loss:.2f}")
                    report_lines.append(f"  Target 1: ${pattern.ipo_target_1:.2f}")
                    report_lines.append(f"  Target 2: ${pattern.ipo_target_2:.2f}")
                    report_lines.append(f"  Target 3: ${pattern.target_point_a:.2f}")
                    # Add TP strategy indication
                    if hasattr(pattern, 'tp_strategy_used') and pattern.tp_strategy_used:
                        report_lines.append(f"  TP Targets: {pattern.tp_strategy_used}")
                    report_lines.append(f"  Risk/Reward: {pattern.risk_reward:.2f}:1")
                    report_lines.append(f"  Ratios: {FormattingUtils.format_pattern_ratios(pattern)}")

                # Add reaction information if available (using FormattingUtils)
                if analysis.get('reaction_data'):
                    reaction_lines = FormattingUtils.format_reaction_status(
                        analysis['reaction_data'], pattern
                    )
                    report_lines.extend(reaction_lines)

                self._append_sector_etf_report(report_lines, analysis)

                # Add chart reference if available
                if analysis.get('chart_path'):
                    report_lines.append("")
                    report_lines.append(f"  📊 Pattern Chart: {analysis['chart_path']}")

                report_lines.append("-"*80)
                report_lines.append("")

        # SELL signals
        direct_sell_signals = [
            analysis for analysis in results['SELL']
            if analysis.get('signal_source') != 'TYPE_2'
        ]
        if direct_sell_signals:
            report_lines.append("="*80)
            report_lines.append("SELL SIGNALS")
            report_lines.append("="*80)
            report_lines.append("")

            for analysis in direct_sell_signals:
                report_lines.append(f"Ticker: {analysis['ticker']}")
                report_lines.append(f"Current Price: ${analysis.get('current_price', 0):.2f}")
                report_lines.append(f"Analysis: {analysis['reason']}")

                if analysis['patterns']:
                    # Use patterns[0] - the pattern that was analyzed for the signal (not patterns[-1])
                    pattern = analysis.get('signal_pattern', analysis['patterns'][0])
                    report_lines.append("")
                    report_lines.append(f"  Pattern: {pattern.pattern_type.upper()} ({'BULLISH' if pattern.is_bullish else 'BEARISH'})")
                    report_lines.append(f"  Grade: {pattern.grade} | Tolerance: {pattern.tolerance_level}")

                    # Show D-point range (PRZ zone)
                    if hasattr(pattern, 'd_point_range_min') and pattern.d_point_range_min > 0:
                        range_from_entry = ((pattern.d_point_range_max - pattern.entry_price) / pattern.entry_price) * 100
                        report_lines.append(f"  Entry Zone (PRZ): ${pattern.d_point_range_min:.2f} - ${pattern.d_point_range_max:.2f} (±{range_from_entry:.1f}%)")

                    report_lines.append(f"  Entry: ${pattern.entry_price:.2f}")
                    report_lines.append(f"  Stop Loss: ${pattern.stop_loss:.2f}")
                    report_lines.append(f"  Target 1: ${pattern.ipo_target_1:.2f}")
                    report_lines.append(f"  Target 2: ${pattern.ipo_target_2:.2f}")
                    report_lines.append(f"  Target 3: ${pattern.target_point_a:.2f}")
                    # Add TP strategy indication
                    if hasattr(pattern, 'tp_strategy_used') and pattern.tp_strategy_used:
                        report_lines.append(f"  TP Targets: {pattern.tp_strategy_used}")
                    report_lines.append(f"  Risk/Reward: {pattern.risk_reward:.2f}:1")
                    report_lines.append(f"  Ratios: {FormattingUtils.format_pattern_ratios(pattern)}")

                # Add reaction information if available (using FormattingUtils)
                if analysis.get('reaction_data'):
                    reaction_lines = FormattingUtils.format_reaction_status(
                        analysis['reaction_data'], pattern
                    )
                    report_lines.extend(reaction_lines)

                self._append_sector_etf_report(report_lines, analysis)

                # Add chart reference if available
                if analysis.get('chart_path'):
                    report_lines.append("")
                    report_lines.append(f"  📊 Pattern Chart: {analysis['chart_path']}")

                report_lines.append("-"*80)
                report_lines.append("")

        # HOLD signals (if enabled in config)
        include_hold = self.config_helper.get_bool('INCLUDE_HOLD_IN_REPORT', False)
        if include_hold and results['HOLD']:
            report_lines.append("="*80)
            report_lines.append("HOLD SIGNALS")
            report_lines.append("="*80)
            report_lines.append("")

            # Only show first 50 HOLD signals to keep report manageable
            max_hold_display = 100
            for analysis in results['HOLD'][:max_hold_display]:
                report_lines.append(f"Ticker: {analysis['ticker']}")
                if analysis.get('current_price'):
                    report_lines.append(f"Current Price: ${analysis.get('current_price', 0):.2f}")

                # If pattern was detected but filtered, show pattern details
                if analysis['patterns']:
                    # Use patterns[0] - the pattern that was analyzed (not patterns[-1])
                    pattern = analysis['patterns'][0]
                    direction = "BULLISH" if pattern.is_bullish else "BEARISH"
                    report_lines.append(f"Pattern Detected: {direction} {pattern.pattern_type.upper()} (Grade: {pattern.grade})")
                    report_lines.append(f"Detection Date: {pattern.d.date.date()} ({pattern.days_since_completion} days ago)")
                    report_lines.append(f"Filter Reason: {analysis['reason']}")
                else:
                    report_lines.append(f"Reason: {analysis['reason']}")

                report_lines.append("-"*80)
                report_lines.append("")

            if len(results['HOLD']) > max_hold_display:
                report_lines.append(f"... and {len(results['HOLD']) - max_hold_display} more HOLD signals")
                report_lines.append("")

        # MONITORING - Patterns approaching D point (forming patterns)
        tracker_summary: Dict[str, Any] = results.get('_tracker_summary', {})  # type: ignore
        if tracker_summary:
            # Get watchlist (forming patterns - haven't reached D point yet)
            watchlist = self.tracker.get_active_patterns(status=PatternStatus.FORMING)

            if watchlist:
                report_lines.append("="*80)
                report_lines.append(f"MONITORING - PATTERNS MATURING ({len(watchlist)})")
                report_lines.append("="*80)
                report_lines.append("Patterns approaching D-point but haven't reached it yet.")
                report_lines.append("="*80)
                report_lines.append("")

                # Get max patterns to display from config (None = show all)
                max_display = self.config_helper.get('MAX_MATURING_PATTERNS_DISPLAY_IN_REPORT', 50)
                patterns_to_show = sorted(watchlist, key=lambda p: p.completion_percentage, reverse=True)
                if max_display is not None:
                    patterns_to_show = patterns_to_show[:max_display]

                for pattern in patterns_to_show:
                    report_lines.append(f"Ticker: {pattern.ticker}")
                    report_lines.append(f"Pattern: {pattern.pattern_type.upper()} ({'BULLISH' if pattern.is_bullish else 'BEARISH'})")
                    report_lines.append(f"Completion: {pattern.completion_percentage*100:.1f}%")
                    report_lines.append(f"Grade: {pattern.grade} | R/R: {pattern.risk_reward:.2f}:1")

                    # Show D-point range (PRZ zone) from pattern tracker
                    if hasattr(pattern, 'd_point_range_min') and pattern.d_point_range_min > 0:
                        range_from_entry = ((pattern.d_point_range_max - pattern.entry_price) / pattern.entry_price) * 100
                        report_lines.append(f"Entry Zone (PRZ): ${pattern.d_point_range_min:.2f} - ${pattern.d_point_range_max:.2f} (±{range_from_entry:.1f}%)")
                    else:
                        # Fallback if d_point_range not set (old patterns)
                        d_target = pattern.entry_price
                        tolerance_pct = 0.02  # 2% tolerance for PRZ
                        d_low = d_target * (1 - tolerance_pct)
                        d_high = d_target * (1 + tolerance_pct)
                        report_lines.append(f"Entry Zone (PRZ): ${d_low:.2f} - ${d_high:.2f}")

                    # Show entry locking status
                    if hasattr(pattern, 'entry_locked') and pattern.entry_locked:
                        report_lines.append(f"Original Entry: ${pattern.original_entry_price:.2f} (LOCKED)")
                        if pattern.entry_price != pattern.original_entry_price:
                            report_lines.append(f"Current D-Point: ${pattern.entry_price:.2f} (moved {abs(pattern.entry_price - pattern.original_entry_price):.2f})")
                    else:
                        report_lines.append(f"Projected Entry: ${pattern.entry_price:.2f}")

                    report_lines.append(f"Projected Stop: ${pattern.stop_loss:.2f}")
                    report_lines.append(f"Days Monitored: {pattern.days_monitored}")
                    report_lines.append("-"*80)
                    report_lines.append("")

                # Show count of remaining patterns if any were omitted
                if max_display is not None and len(watchlist) > max_display:
                    report_lines.append(f"... and {len(watchlist) - max_display} more forming patterns")
                    report_lines.append("")

        report_lines.append("="*80)
        report_lines.append("END OF REPORT")
        report_lines.append("="*80)

        return "\n".join(report_lines)

    @staticmethod
    def _append_type2_sections(
        report_lines: List[str],
        results: Dict[str, List[Dict[str, Any]]],
    ) -> None:
        """Append Type 2 confirmations and candidates outside ordinary HOLDs."""
        analyses = [
            analysis
            for signal in ('BUY', 'SELL', 'HOLD')
            for analysis in results[signal]
        ]
        confirmed = [
            (analysis, record)
            for analysis in analyses
            for record in analysis.get('type2_confirmations', [])
        ]
        candidates = [
            (analysis, record)
            for analysis in analyses
            for record in analysis.get('type2_candidates', [])
        ]

        if confirmed:
            report_lines.append("=" * 80)
            report_lines.append(f"TYPE 2 CONFIRMED ({len(confirmed)})")
            report_lines.append("=" * 80)
            report_lines.append("")
            for analysis, record in confirmed:
                pattern = record['pattern']
                actionable = (
                    analysis.get('signal_source') == 'TYPE_2'
                    and analysis.get('signal_pattern') is pattern
                )
                if actionable:
                    status = 'ACTIONABLE'
                elif record['stop_hit']:
                    status = 'STOPPED'
                elif record['bars_since_confirmation'] is not None:
                    status = 'MONITORING'
                else:
                    status = 'NOT ACTIONABLE'
                report_lines.append(f"Ticker: {analysis['ticker']}")
                report_lines.append(
                    f"Pattern: {pattern.pattern_type.upper()} "
                    f"({'BULLISH' if pattern.is_bullish else 'BEARISH'})"
                )
                report_lines.append(
                    f"Retest Date: {record['retest_date'].date()}"
                )
                report_lines.append(
                    f"Confirmation Date: {record['confirmation_date'].date()}"
                )
                report_lines.append(f"Status: {status}")
                report_lines.append(
                    f"New Entry: ${record['entry_price']:.2f} | "
                    f"New Stop: ${record['stop_loss']:.2f} "
                    f"({record['risk_pct']:.1f}% risk)"
                )
                report_lines.append(
                    f"1R / 2R / 3R: ${record['target_1']:.2f} / "
                    f"${record['target_2']:.2f} / ${record['target_3']:.2f}"
                )
                if record['forward_return_pct'] is not None:
                    report_lines.append(
                        f"Forward Return: {record['forward_return_pct']:+.2f}%"
                    )
                if record['stop_hit']:
                    report_lines.append("Warning: Retest-derived stop has been hit")
                report_lines.append("-" * 80)
                report_lines.append("")

        if candidates:
            report_lines.append("=" * 80)
            report_lines.append(f"TYPE 2 CANDIDATES ({len(candidates)})")
            report_lines.append("=" * 80)
            report_lines.append(
                "Initial reaction and PRZ retest detected; waiting for a second reversal."
            )
            report_lines.append("")
            for analysis, record in candidates:
                pattern = record['pattern']
                report_lines.append(f"Ticker: {analysis['ticker']}")
                report_lines.append(
                    f"Pattern: {pattern.pattern_type.upper()} "
                    f"({'BULLISH' if pattern.is_bullish else 'BEARISH'})"
                )
                report_lines.append(f"Retest Date: {record['retest_date'].date()}")
                report_lines.append("Status: NOT ACTIONABLE")
                report_lines.append("-" * 80)
                report_lines.append("")

    @staticmethod
    def _append_sector_etf_report(
        report_lines: List[str],
        analysis: Dict[str, Any]
    ) -> None:
        """Append sector ETF trend confluence to an actionable signal."""
        sector_context = analysis.get('sector_etf_analysis')
        if not sector_context:
            return

        report_lines.append("")
        report_lines.append(
            f"  Relevant ETF: {sector_context.etf_ticker} "
            f"({sector_context.theme})"
        )
        report_lines.append(
            f"  ETF Selection: {sector_context.selection_reason}"
        )
        report_lines.append(
            f"  ETF Trend: {sector_context.trend} | "
            f"20-Period Return: {sector_context.return_20_period_pct:+.1f}%"
        )
        report_lines.append(
            f"  Signal Confluence: {sector_context.confluence_label}"
        )

    def save_report(self, report: str) -> str:
        """Save report to file in reports/<date>/ directory"""
        # Get configuration values using ConfigHelper
        data_interval = self.config_helper.get('DATA_INTERVAL', '1d')
        verbose = self.config_helper.get_bool('VERBOSE_REPORTS', False)

        # Get report path using PathManager
        report_path = self.path_manager.get_report_path(
            interval=data_interval,
            verbose=verbose,
            asset_type=self.asset_type
        )

        with open(report_path, 'w') as f:
            f.write(report)

        logger.info("Report saved to: %s", report_path)
        return report_path


def main() -> None:
    """Main entry point"""
    scanner = HarmonicScanner()

    # Run scan
    max_stocks = scanner.config_helper.get_int('MAX_STOCKS_TO_SCAN', 50)
    results = scanner.run_scan(max_stocks=max_stocks)

    # Generate and display report
    report = scanner.generate_report(results)
    print(report)

    # Save report
    scanner.save_report(report)


if __name__ == "__main__":
    main()
