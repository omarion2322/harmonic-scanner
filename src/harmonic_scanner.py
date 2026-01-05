"""
Hybrid Harmonic Pattern Scanner
Combines Pyharmonics peak detection with Scott Carney's exact trading framework from Volumes 1-3

Usage:
    python harmonic_scanner.py
"""

# Print early to show scanner is loading
print("Loading harmonic pattern scanner modules...")

import yfinance as yf
import pandas as pd
from datetime import datetime
import warnings
from typing import List, Dict
import time

from pattern_detector import PatternDetector
from reaction_detector import ReactionDetector
from data_downloader import download_stock_data
from pattern_tracker import PatternTracker, PatternStatus
from utils import ConfigHelper, PathManager, FormattingUtils, TickerManager

warnings.filterwarnings('ignore')

print("✓ Modules loaded successfully")

# Import configuration
try:
    import config
except ImportError:
    class config:
        MAX_STOCKS_TO_SCAN = 50
        MAX_DAYS_SINCE_PATTERN = 10


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

    def __init__(self):
        self.detector = PatternDetector()  # Uses Carney's exact specifications
        self.reaction_detector = ReactionDetector()  # Type 1 and Type 2 reaction detection
        self.tracker = PatternTracker(storage_dir="./pattern_tracking")  # Pattern state tracking

        # Initialize utility helpers
        self.config_helper = ConfigHelper(config)
        self.path_manager = PathManager()

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
                print(f"✓ Successfully fetched {len(sp500_tickers)} S&P 500 tickers from SlickCharts")

                # Merge custom tickers with S&P 500 using TickerManager
                custom_tickers = self.config_helper.get('STOCK_TICKERS')
                tickers = TickerManager.merge_ticker_lists(custom_tickers, sp500_tickers)
                TickerManager.print_custom_ticker_info(custom_tickers)

                return tickers
            else:
                raise Exception("Symbol column not found")

        except Exception as e:
            print(f"Error fetching S&P 500 list from SlickCharts: {e}")
            print("Using fallback list of major stocks...")

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

    def scan_stock(self, ticker: str, verbose: bool = None, override_period: str = None) -> Dict:
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
            # download_stock_data includes retry logic with exponential backoff
            df = download_stock_data(
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

            # Evaluate most recent pattern first (before generating chart) may need to change to -1
            latest_pattern = patterns[0]

            # Calculate days since pattern completion
            import pandas as pd
            from datetime import datetime
            # Convert both to date objects to avoid timezone issues
            today = datetime.now().date()
            pattern_date = latest_pattern.d.date.date() if hasattr(latest_pattern.d.date, 'date') else latest_pattern.d.date
            days_since = (today - pattern_date).days
            latest_pattern.days_since_completion = days_since

            # Use MAX_DAYS_SINCE_PATTERN from config for filtering patterns by completion date
            # Falls back to default (730 days) if not set
            max_pattern_age = getattr(config, 'MAX_DAYS_SINCE_PATTERN', None)
            signal, explanation = self.detector.generate_signal(
                latest_pattern,
                current_price,
                max_days_old=max_pattern_age,
                verbose=verbose
            )

            # Only generate chart if signal is BUY or SELL (actionable)
            chart_path = None
            reaction_data = None
            auto_save_charts = self.config_helper.get_bool('AUTO_SAVE_CHARTS', True)

            if signal in ['BUY', 'SELL'] and auto_save_charts:
                # Detect Type 1 and Type 2 reactions for the pattern
                current_idx = len(df) - 1
                reaction_data = self.reaction_detector.detect_reaction(df, latest_pattern, current_idx)

                # Get chart directory using PathManager
                chart_dir = str(self.path_manager.get_chart_dir(interval=data_interval))

                # Generate pattern chart
                try:
                    chart_path = self.detector.generate_pattern_chart(
                        latest_pattern, ticker, df, chart_dir,
                        interval=data_interval, reaction_data=reaction_data
                    )
                    latest_pattern.chart_path = chart_path
                except Exception as e:
                    print(f"Warning: Could not generate chart for {ticker}: {e}")
                    chart_path = None

            return {
                'ticker': ticker,
                'signal': signal,
                'reason': explanation,
                'patterns': patterns,
                'current_price': current_price,
                'chart_path': chart_path,
                'reaction_data': reaction_data
            }

        except Exception as e:
            return {
                'ticker': ticker,
                'signal': 'HOLD',
                'reason': f'Error analyzing stock: {str(e)}',
                'patterns': [],
                'chart_path': None
            }

    def run_scan(self, max_stocks: int = None) -> Dict[str, List[Dict]]:
        """
        Scan S&P 500 stocks for harmonic patterns.

        Args:
            max_stocks: Maximum number of stocks to scan (None for all)

        Returns:
            Dictionary with BUY, SELL, HOLD lists
        """
        print("="*80)
        print("IMPROVED HARMONIC PATTERN SCANNER")
        print("Pyharmonics Peak Detection + Scott Carney's Exact Rules (Volumes 1-3)")
        print("="*80)
        print()
        print("="*80)
        config.get_settings_summary()

        # Get ticker list using new stock universe system (respects STOCKS_TO_SCAN config)
        tickers = config.get_stock_list()

        # Merge custom tickers with universe using TickerManager
        custom_tickers = self.config_helper.get('STOCK_TICKERS')
        tickers = TickerManager.merge_ticker_lists(custom_tickers, tickers)
        TickerManager.print_custom_ticker_info(custom_tickers)

        print(f"Total tickers to scan: {len(tickers)}")

        if max_stocks:
            tickers = tickers[:max_stocks]


        print(f"Scanning {len(tickers)} stocks for harmonic patterns...")
        print("This may take several minutes...")
        print()

        results = {'BUY': [], 'SELL': [], 'HOLD': []}
        failed_tickers = []  # Track failed downloads for retry

        # Track patterns across scans
        tracked_stats = {
            'confirmed': 0,
            'watchlist': 0,
            'invalidated': 0
        }

        for i, ticker in enumerate(tickers, 1):
            # Progress update every 10 stocks
            if i % 10 == 0:
                print(f"Progress: {i}/{len(tickers)} stocks analyzed...")

            # Use verbose mode from config
            verbose = self.config_helper.get_bool('VERBOSE_REPORTS', False)
            analysis = self.scan_stock(ticker, verbose=verbose)

            # Track download failures for retry
            is_no_data = analysis['signal'] == 'HOLD' and 'No data available' in analysis['reason']
            is_error = analysis['signal'] == 'HOLD' and 'Error analyzing stock' in analysis['reason']

            # Only retry if download actually failed (no data returned)
            download_failed = is_no_data or is_error
            if download_failed:
                failed_tickers.append(ticker)

            results[analysis['signal']].append(analysis)

            # Update pattern tracker with completed AND forming patterns
            # Skip if initial download already failed to avoid duplicate download attempts
            if not download_failed:
                try:
                    from pyharmonics import OHLCTechnicals as Technicals
                    from pyharmonics.search import HarmonicSearch

                    # Download with retry logic (same as main download)
                    data_interval = self.config_helper.get('DATA_INTERVAL', '1wk')
                    data_period = self.config_helper.get('DATA_PERIOD', '2y')
                    max_retries = self.config_helper.get_int('MAX_DOWNLOAD_RETRIES', 3)

                    df = download_stock_data(
                        ticker=ticker,
                        period=data_period,
                        interval=data_interval,
                        auto_adjust=False,
                        max_retries=max_retries
                    )

                    if not df.empty:
                        df.columns = [c.lower() for c in df.columns]

                        # Collect all patterns (completed + forming)
                        all_patterns = []

                        # Add completed patterns from analysis
                        if analysis.get('patterns'):
                            all_patterns.extend(analysis['patterns'])

                        # Detect forming patterns (85-100% complete)
                        try:
                            swing_window = self.config_helper.get_int('SWING_WINDOW', 3)
                            tech = Technicals(df, ticker, data_interval, peak_spacing=swing_window)
                            fib_tolerance = self.config_helper.get_float('PYHARMONICS_FIB_TOLERANCE', 0.03)
                            h = HarmonicSearch(tech, fib_tolerance=fib_tolerance, check_anchor=True)

                            # Detect patterns 85% complete
                            h.forming(limit_to=10, percent_c_to_d=0.95)
                            forming = h.get_patterns(family=h.XABCD, formed=False)

                            # Convert forming patterns to HarmonicPattern objects
                            for py_pattern in forming.get(h.XABCD, []):
                                converted = self.detector._convert_pyharmonics_pattern(
                                    py_pattern, df, tech, fib_tolerance, ticker
                                )
                                if converted:
                                    all_patterns.append(converted)

                        except Exception as e:
                            if verbose:
                                print(f"  Warning: Could not detect forming patterns for {ticker}: {e}")

                        # Update tracker with all patterns
                        if all_patterns:
                            current_date = datetime.now()
                            tracked = self.tracker.update_patterns(
                                ticker=ticker,
                                detected_patterns=all_patterns,
                                price_data=df,
                                current_date=current_date
                            )

                            # Update stats
                            tracked_stats['confirmed'] += len(tracked.get('confirmed', []))
                            tracked_stats['watchlist'] += len(tracked.get('watchlist', []))
                            tracked_stats['invalidated'] += len(tracked.get('invalidated', []))

                except Exception as e:
                    if verbose:
                        print(f"  Warning: Could not update tracker for {ticker}: {e}")

            # Small delay to avoid rate limiting (from config)
            delay = self.config_helper.get_float('DOWNLOAD_DELAY', 0.1)
            if delay > 0:
                time.sleep(delay)

        # Retry failed downloads (genuine download failures only)
        if failed_tickers:
            print()
            print(f"Retrying {len(failed_tickers)} tickers with download failures...")

            success_count = 0
            for ticker in failed_tickers:
                # Try one fallback period (max history available)
                retry_analysis = self.scan_stock(ticker, verbose=False, override_period='max')

                # Check if retry succeeded (not a HOLD with download failure)
                is_still_failed = (retry_analysis['signal'] == 'HOLD' and
                                  ('No data available' in retry_analysis['reason'] or
                                   'Error analyzing stock' in retry_analysis['reason']))

                if not is_still_failed:
                    # Success - update results
                    results['HOLD'] = [r for r in results['HOLD'] if r['ticker'] != ticker]
                    results[retry_analysis['signal']].append(retry_analysis)
                    print(f"  ✓ {ticker}: Retry succeeded")
                    success_count += 1
                # No message for failures - ticker stays in original HOLD results

            if success_count > 0:
                print(f"Retry summary: {success_count}/{len(failed_tickers)} succeeded")
            print()

        print()
        print("="*80)
        print("SCAN COMPLETE")
        print("="*80)
        print(f"BUY signals: {len(results['BUY'])}")
        print(f"SELL signals: {len(results['SELL'])}")
        print(f"HOLD signals: {len(results['HOLD'])}")
        print()
        print("PATTERN TRACKING:")
        print(f"Confirmed patterns (Type 1/2): {tracked_stats['confirmed']}")
        print(f"Watchlist (forming patterns): {tracked_stats['watchlist']}")
        print(f"Invalidated (D extended): {tracked_stats['invalidated']}")
        print()

        # Store tracker summary in results for report generation
        results['_tracker_summary'] = self.tracker.get_summary()
        results['_tracked_stats'] = tracked_stats

        return results

    def generate_report(self, results: Dict[str, List[Dict]]) -> str:
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

        # Add tracker stats if available
        tracked_stats = results.get('_tracked_stats', {})
        if tracked_stats:
            report_lines.append("")
            report_lines.append("Pattern Tracking:")
            report_lines.append(f"  Confirmed (Type 1/2 Reactions): {tracked_stats.get('confirmed', 0)}")
            report_lines.append(f"  Watchlist (Forming Patterns): {tracked_stats.get('watchlist', 0)}")
            report_lines.append(f"  Invalidated (D Extended): {tracked_stats.get('invalidated', 0)}")

        report_lines.append("")

        # BUY signals
        if results['BUY']:
            report_lines.append("="*80)
            report_lines.append("BUY SIGNALS")
            report_lines.append("="*80)
            report_lines.append("")

            for analysis in results['BUY']:
                report_lines.append(f"Ticker: {analysis['ticker']}")
                report_lines.append(f"Current Price: ${analysis.get('current_price', 0):.2f}")
                report_lines.append(f"Analysis: {analysis['reason']}")

                if analysis['patterns']:
                    # Use patterns[0] - the pattern that was analyzed for the signal (not patterns[-1])
                    pattern = analysis['patterns'][0]
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

                # Add chart reference if available
                if analysis.get('chart_path'):
                    report_lines.append("")
                    report_lines.append(f"  📊 Pattern Chart: {analysis['chart_path']}")

                report_lines.append("-"*80)
                report_lines.append("")

        # SELL signals
        if results['SELL']:
            report_lines.append("="*80)
            report_lines.append("SELL SIGNALS")
            report_lines.append("="*80)
            report_lines.append("")

            for analysis in results['SELL']:
                report_lines.append(f"Ticker: {analysis['ticker']}")
                report_lines.append(f"Current Price: ${analysis.get('current_price', 0):.2f}")
                report_lines.append(f"Analysis: {analysis['reason']}")

                if analysis['patterns']:
                    # Use patterns[0] - the pattern that was analyzed for the signal (not patterns[-1])
                    pattern = analysis['patterns'][0]
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
        tracker_summary = results.get('_tracker_summary', {})
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

    def save_report(self, report: str):
        """Save report to file in reports/<date>/ directory"""
        # Get configuration values using ConfigHelper
        data_interval = self.config_helper.get('DATA_INTERVAL', '1d')
        verbose = self.config_helper.get_bool('VERBOSE_REPORTS', False)

        # Get report path using PathManager
        report_path = self.path_manager.get_report_path(
            interval=data_interval,
            verbose=verbose
        )

        with open(report_path, 'w') as f:
            f.write(report)

        print(f"✓ Report saved to: {report_path}")
        return report_path


def main():
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
