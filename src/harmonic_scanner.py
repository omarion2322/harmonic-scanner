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

            signal, explanation = self.detector.generate_signal(
                latest_pattern,
                current_price,
                max_days_old=config.MAX_DAYS_SINCE_PATTERN,
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

        for i, ticker in enumerate(tickers, 1):
            # Progress update every 10 stocks
            if i % 10 == 0:
                print(f"Progress: {i}/{len(tickers)} stocks analyzed...")

            # Use verbose mode from config
            verbose = config.VERBOSE_REPORTS if hasattr(config, 'VERBOSE_REPORTS') else False
            analysis = self.scan_stock(ticker, verbose=verbose)
            results[analysis['signal']].append(analysis)

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
        report_lines.append(f"Total Stocks Scanned: {sum(len(v) for v in results.values())}")
        report_lines.append(f"BUY Signals: {len(results['BUY'])}")
        report_lines.append(f"SELL Signals: {len(results['SELL'])}")
        report_lines.append(f"HOLD Signals: {len(results['HOLD'])}")
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
                    report_lines.append(f"  Grade: {pattern.grade} | Quality: {pattern.pattern_quality} | Tolerance: {pattern.tolerance_level}")
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
                    if reaction.type1_detected:
                        targets_hit = []
                        if reaction.type1_reached_382:
                            targets_hit.append("38.2%")
                        if reaction.type1_reached_618:
                            targets_hit.append("61.8%")
                        if targets_hit:
                            report_lines.append(f"    Type 1 Targets Hit: {', '.join(targets_hit)}")
                        if reaction.type1_trendline_broken:
                            report_lines.append(f"    ⚠ Type 1 Trendline Broken - Watching for Type 2")
                    if reaction.type2_detected:
                        report_lines.append(f"    Type 2 Reversal Confirmed - PRZ Retested")

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
                    report_lines.append(f"  Grade: {pattern.grade} | Quality: {pattern.pattern_quality} | Tolerance: {pattern.tolerance_level}")
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
                    if reaction.type1_detected:
                        targets_hit = []
                        if reaction.type1_reached_382:
                            targets_hit.append("38.2%")
                        if reaction.type1_reached_618:
                            targets_hit.append("61.8%")
                        if targets_hit:
                            report_lines.append(f"    Type 1 Targets Hit: {', '.join(targets_hit)}")
                        if reaction.type1_trendline_broken:
                            report_lines.append(f"    ⚠ Type 1 Trendline Broken - Watching for Type 2")
                    if reaction.type2_detected:
                        report_lines.append(f"    Type 2 Reversal Confirmed - PRZ Retested")

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

                # Charts should NOT be generated for HOLD signals anymore
                # (only for BUY/SELL signals)

                report_lines.append("-"*80)
                report_lines.append("")

            if len(results['HOLD']) > max_hold_display:
                report_lines.append(f"... and {len(results['HOLD']) - max_hold_display} more HOLD signals")
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
