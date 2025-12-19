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
from pattern_tracker import PatternTracker, PatternStatus

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

                # Prepend custom tickers from config if they exist (scan them first)
                if hasattr(config, 'STOCK_TICKERS') and config.STOCK_TICKERS:
                    custom_tickers = [t.upper().strip() for t in config.STOCK_TICKERS]
                    # Remove duplicates - keep custom tickers first, then S&P 500
                    sp500_upper = [t.upper() for t in sp500_tickers]
                    # Filter out S&P 500 tickers that are already in custom list
                    unique_sp500 = [t for t in sp500_tickers if t.upper() not in [c.upper() for c in custom_tickers]]

                    # Final list: custom tickers first, then unique S&P 500 tickers
                    tickers = custom_tickers + unique_sp500
                    print(f"✓ Custom tickers will be scanned first: {', '.join(custom_tickers)}")
                else:
                    tickers = sp500_tickers

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

            # Prepend custom tickers to fallback list (scan them first)
            if hasattr(config, 'STOCK_TICKERS') and config.STOCK_TICKERS:
                custom_tickers = [t.upper().strip() for t in config.STOCK_TICKERS]
                # Remove duplicates - keep custom tickers first, then fallback
                unique_fallback = [t for t in fallback_sp500 if t.upper() not in [c.upper() for c in custom_tickers]]

                # Final list: custom tickers first, then unique fallback tickers
                fallback_tickers = custom_tickers + unique_fallback
                print(f"✓ Custom tickers will be scanned first: {', '.join(custom_tickers)}")
            else:
                fallback_tickers = fallback_sp500

            return fallback_tickers

    def scan_stock(self, ticker: str, verbose: bool = None) -> Dict:
        """
        Scan a single stock for harmonic patterns using hybrid detector.

        Args:
            ticker: Stock ticker symbol
            verbose: If True, generate detailed explanations (defaults to config.VERBOSE_REPORTS)

        Returns:
            Dictionary with analysis results
        """
        # Use config setting if not explicitly provided
        if verbose is None:
            verbose = config.VERBOSE_REPORTS if hasattr(config, 'VERBOSE_REPORTS') else False

        try:
            # Download data using config settings
            stock = yf.Ticker(ticker)
            data_interval = config.DATA_INTERVAL if hasattr(config, 'DATA_INTERVAL') else '1d'

            # For MITCH strategy, download full history to find support/resistance from entire stock history
            # For other strategies, use configured DATA_PERIOD
            tp_strategy = config.TP_STRATEGY if hasattr(config, 'TP_STRATEGY') else 'SCOTT'
            if tp_strategy == 'MITCH':
                data_period = 'max'  # Full history for comprehensive S/R analysis
            else:
                data_period = config.DATA_PERIOD if hasattr(config, 'DATA_PERIOD') else '6mo'

            # Use auto_adjust=False to get actual NYSE trading prices (not dividend-adjusted)
            df = stock.history(period=data_period, interval=data_interval, auto_adjust=False)

            if df.empty or len(df) < 50:
                interval_name = {'1d': 'days', '1wk': 'weeks', '1mo': 'months'}.get(data_interval, 'bars')
                insufficient_msg = f'Insufficient data for {ticker}: only {len(df)} bars available (minimum 50 required)' if verbose else f'Insufficient data: only {len(df)} {interval_name} available'
                return {
                    'ticker': ticker,
                    'signal': 'HOLD',
                    'reason': insufficient_msg,
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
            auto_save_charts = config.AUTO_SAVE_CHARTS if hasattr(config, 'AUTO_SAVE_CHARTS') else True

            if signal in ['BUY', 'SELL'] and auto_save_charts:
                # Detect Type 1 and Type 2 reactions for the pattern
                current_idx = len(df) - 1
                reaction_data = self.reaction_detector.detect_reaction(df, latest_pattern, current_idx)

                # Get chart directory (in reports/<date>/charts/)
                import os
                from datetime import datetime
                script_dir = os.path.dirname(os.path.abspath(__file__))
                project_root = os.path.dirname(script_dir)
                today = datetime.now().strftime('%Y-%m-%d')
                chart_dir = os.path.join(project_root, "reports", today, data_interval, "charts")

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

        # Prepend custom tickers from config if they exist (scan them first)
        if hasattr(config, 'STOCK_TICKERS') and config.STOCK_TICKERS:
            custom_tickers = [t.upper().strip() for t in config.STOCK_TICKERS]
            # Remove duplicates - keep custom tickers first
            tickers_upper = [t.upper() for t in tickers]
            unique_tickers = [t for t in tickers if t.upper() not in [c.upper() for c in custom_tickers]]
            # Final list: custom tickers first, then universe tickers
            tickers = custom_tickers + unique_tickers
            print(f"✓ Custom tickers will be scanned first: {', '.join(custom_tickers)}")

        print(f"Total tickers to scan: {len(tickers)}")

        if max_stocks:
            tickers = tickers[:max_stocks]


        print(f"Scanning {len(tickers)} stocks for harmonic patterns...")
        print("This may take several minutes...")
        print()

        results = {'BUY': [], 'SELL': [], 'HOLD': []}

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
            verbose = config.VERBOSE_REPORTS if hasattr(config, 'VERBOSE_REPORTS') else False
            analysis = self.scan_stock(ticker, verbose=verbose)
            results[analysis['signal']].append(analysis)

            # Update pattern tracker with completed AND forming patterns
            # Get price data for tracking and forming pattern detection
            try:
                import yfinance as yf
                from pyharmonics import OHLCTechnicals as Technicals
                from pyharmonics.search import HarmonicSearch

                stock = yf.Ticker(ticker)
                data_interval = config.DATA_INTERVAL if hasattr(config, 'DATA_INTERVAL') else '1wk'
                data_period = config.DATA_PERIOD if hasattr(config, 'DATA_PERIOD') else '2y'
                df = stock.history(period=data_period, interval=data_interval, auto_adjust=False)

                if not df.empty and len(df) >= 50:
                    df.columns = [c.lower() for c in df.columns]

                    # Collect all patterns (completed + forming)
                    all_patterns = []

                    # Add completed patterns from analysis
                    if analysis.get('patterns'):
                        all_patterns.extend(analysis['patterns'])

                    # Detect forming patterns (85-100% complete)
                    try:
                        swing_window = config.SWING_WINDOW if hasattr(config, 'SWING_WINDOW') else 3
                        tech = Technicals(df, ticker, data_interval, peak_spacing=swing_window)
                        fib_tolerance = config.PYHARMONICS_FIB_TOLERANCE if hasattr(config, 'PYHARMONICS_FIB_TOLERANCE') else 0.03
                        h = HarmonicSearch(tech, fib_tolerance=fib_tolerance, check_anchor=True)

                        # Detect patterns 85% complete
                        h.forming(limit_to=10, percent_c_to_d=0.85)
                        forming = h.get_patterns(family=h.XABCD, formed=False)

                        # Convert forming patterns to HarmonicPattern objects
                        for py_pattern in forming.get(h.XABCD, []):
                            converted = self.detector._convert_pyharmonics_pattern(
                                py_pattern, df, tech, fib_tolerance
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
            delay = config.DOWNLOAD_DELAY if hasattr(config, 'DOWNLOAD_DELAY') else 0.1
            if delay > 0:
                time.sleep(delay)

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
                    report_lines.append(f"  Trade Quality: {pattern.trade_quality}")
                    report_lines.append(f"  Entry: ${pattern.entry_price:.2f}")
                    report_lines.append(f"  Stop Loss: ${pattern.stop_loss:.2f}")
                    report_lines.append(f"  Target 1: ${pattern.ipo_target_1:.2f}")
                    report_lines.append(f"  Target 2: ${pattern.ipo_target_2:.2f}")
                    report_lines.append(f"  Target 3: ${pattern.target_point_a:.2f}")
                    report_lines.append(f"  Risk/Reward: {pattern.risk_reward:.2f}:1")
                    report_lines.append(f"  Ratios: B={pattern.ab_xa_ratio:.3f}, BC_proj={pattern.bc_projection:.3f}, D={pattern.ad_xa_ratio:.3f}")

                # Add reaction information if available
                if analysis.get('reaction_data'):
                    reaction = analysis['reaction_data']
                    report_lines.append("")
                    report_lines.append(f"  Reaction: {reaction.reaction_summary}")

                    # Type 1 Status
                    if reaction.type1_detected:
                        type1_status = "✓ HIT"
                        price_info = f" - Price reached: ${reaction.type1_max_move:.2f}" if reaction.type1_max_move else ""
                        targets_hit = []
                        if reaction.type1_reached_382:
                            targets_hit.append("38.2% of CD")
                        if reaction.type1_reached_618:
                            targets_hit.append("61.8% of CD")
                        if targets_hit:
                            price_info += f" ({', '.join(targets_hit)})"
                    else:
                        type1_status = "✗ NOT HIT"
                        price_info = ""
                    report_lines.append(f"    Type 1: {type1_status}{price_info}")

                    # Type 2 Status
                    if reaction.type2_detected:
                        type2_status = "✓ HIT"
                        price_info = f" - Price reached: ${reaction.type2_terminal_bar_price:.2f}" if reaction.type2_terminal_bar_price else ""
                        type2_info = []
                        # Note: b_level_broken and cd_886_exceeded are in type2_data dict, need to track them
                        price_info += " (Broke B level or exceeded 88.6% of CD)"
                    else:
                        type2_status = "✗ NOT HIT"
                        price_info = ""
                    report_lines.append(f"    Type 2: {type2_status}{price_info}")

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
                    report_lines.append(f"  Trade Quality: {pattern.trade_quality}")
                    report_lines.append(f"  Entry: ${pattern.entry_price:.2f}")
                    report_lines.append(f"  Stop Loss: ${pattern.stop_loss:.2f}")
                    report_lines.append(f"  Target 1: ${pattern.ipo_target_1:.2f}")
                    report_lines.append(f"  Target 2: ${pattern.ipo_target_2:.2f}")
                    report_lines.append(f"  Target 3: ${pattern.target_point_a:.2f}")
                    report_lines.append(f"  Risk/Reward: {pattern.risk_reward:.2f}:1")
                    report_lines.append(f"  Ratios: B={pattern.ab_xa_ratio:.3f}, BC_proj={pattern.bc_projection:.3f}, D={pattern.ad_xa_ratio:.3f}")

                # Add reaction information if available
                if analysis.get('reaction_data'):
                    reaction = analysis['reaction_data']
                    report_lines.append("")
                    report_lines.append(f"  Reaction: {reaction.reaction_summary}")

                    # Type 1 Status
                    if reaction.type1_detected:
                        type1_status = "✓ HIT"
                        price_info = f" - Price reached: ${reaction.type1_max_move:.2f}" if reaction.type1_max_move else ""
                        targets_hit = []
                        if reaction.type1_reached_382:
                            targets_hit.append("38.2% of CD")
                        if reaction.type1_reached_618:
                            targets_hit.append("61.8% of CD")
                        if targets_hit:
                            price_info += f" ({', '.join(targets_hit)})"
                    else:
                        type1_status = "✗ NOT HIT"
                        price_info = ""
                    report_lines.append(f"    Type 1: {type1_status}{price_info}")

                    # Type 2 Status
                    if reaction.type2_detected:
                        type2_status = "✓ HIT"
                        price_info = f" - Price reached: ${reaction.type2_terminal_bar_price:.2f}" if reaction.type2_terminal_bar_price else ""
                        type2_info = []
                        # Note: b_level_broken and cd_886_exceeded are in type2_data dict, need to track them
                        price_info += " (Broke B level or exceeded 88.6% of CD)"
                    else:
                        type2_status = "✗ NOT HIT"
                        price_info = ""
                    report_lines.append(f"    Type 2: {type2_status}{price_info}")

                # Add chart reference if available
                if analysis.get('chart_path'):
                    report_lines.append("")
                    report_lines.append(f"  📊 Pattern Chart: {analysis['chart_path']}")

                report_lines.append("-"*80)
                report_lines.append("")

        # HOLD signals (if enabled in config)
        include_hold = config.INCLUDE_HOLD_IN_REPORT if hasattr(config, 'INCLUDE_HOLD_IN_REPORT') else False
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

                for pattern in sorted(watchlist, key=lambda p: p.completion_percentage, reverse=True)[:20]:
                    report_lines.append(f"Ticker: {pattern.ticker}")
                    report_lines.append(f"Pattern: {pattern.pattern_type.upper()} ({'BULLISH' if pattern.is_bullish else 'BEARISH'})")
                    report_lines.append(f"Completion: {pattern.completion_percentage*100:.1f}%")
                    report_lines.append(f"Grade: {pattern.grade} | R/R: {pattern.risk_reward:.2f}:1")

                    # Calculate D-point range (PRZ zone)
                    # D point is the entry price, and we show a range around it
                    d_target = pattern.entry_price
                    tolerance_pct = 0.02  # 2% tolerance for PRZ
                    d_low = d_target * (1 - tolerance_pct)
                    d_high = d_target * (1 + tolerance_pct)

                    report_lines.append(f"D-Point Range: ${d_low:.2f} - ${d_high:.2f} (Target: ${d_target:.2f})")
                    report_lines.append(f"Projected Entry: ${pattern.entry_price:.2f} | Projected Stop: ${pattern.stop_loss:.2f}")
                    report_lines.append(f"Days Monitored: {pattern.days_monitored}")
                    report_lines.append("-"*80)
                    report_lines.append("")

                if len(watchlist) > 20:
                    report_lines.append(f"... and {len(watchlist) - 20} more forming patterns")
                    report_lines.append("")

        report_lines.append("="*80)
        report_lines.append("END OF REPORT")
        report_lines.append("="*80)

        return "\n".join(report_lines)

    def save_report(self, report: str):
        """Save report to file in reports/<date>/ directory"""
        import os

        # Get project root directory (one level up from src/)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)

        # Create reports directory with today's date and data interval
        today = datetime.now().strftime('%Y-%m-%d')
        data_interval = config.DATA_INTERVAL if hasattr(config, 'DATA_INTERVAL') else '1d'
        report_dir = os.path.join(project_root, "reports", today, data_interval)
        os.makedirs(report_dir, exist_ok=True)

        # Add verbose suffix if enabled
        verbose = config.VERBOSE_REPORTS if hasattr(config, 'VERBOSE_REPORTS') else False
        suffix = "_verbose" if verbose else ""

        # Save report (include interval in filename for clarity)
        report_filename = f"harmonic_report_{today}_{data_interval}{suffix}.txt"
        report_path = os.path.join(report_dir, report_filename)

        with open(report_path, 'w') as f:
            f.write(report)

        print(f"✓ Report saved to: {report_path}")
        return report_path


def main():
    """Main entry point"""
    scanner = HarmonicScanner()

    # Run scan
    max_stocks = config.MAX_STOCKS_TO_SCAN if hasattr(config, 'MAX_STOCKS_TO_SCAN') else 50
    results = scanner.run_scan(max_stocks=max_stocks)

    # Generate and display report
    report = scanner.generate_report(results)
    print(report)

    # Save report
    scanner.save_report(report)


if __name__ == "__main__":
    main()
