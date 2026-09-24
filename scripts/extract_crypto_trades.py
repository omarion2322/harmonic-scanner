#!/usr/bin/env python3
"""
Extract trades from harmonic pattern report and save to JSON for paper trading.
Prevents duplicates and maintains a clean list of active trades.
"""

import re
import json
import sys
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, asdict

# Add src directory to path to import config
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
from config import get_timeframe_config
from extract_trades import parse_report_targets, resolve_rr_thresholds


@dataclass
class PaperTrade:
    """Represents a paper trade extracted from the report"""
    ticker: str
    signal_type: str  # BUY or SELL
    pattern: str
    detected_date: str
    entry_price: float
    stop_loss: float
    target1: Optional[float]
    target2: Optional[float]
    target3: Optional[float]
    risk_reward: float
    grade: str
    timeframe: str
    extracted_date: str  # When this trade was added to paper trading
    status: str = "OPEN"  # OPEN, CLOSED, STOPPED_OUT

    def get_unique_id(self) -> str:
        """
        Generate unique ID for this trade.
        Uses ticker + signal_type + pattern + timeframe to identify the same pattern.
        Does NOT use detected_date to prevent duplicates when the same pattern is detected on different days.
        """
        # Normalize pattern name (remove direction indicators)
        pattern_normalized = self.pattern.replace(' (BULLISH)', '').replace(' (BEARISH)', '').strip()
        return f"{self.ticker}_{self.signal_type}_{pattern_normalized}_{self.timeframe}"


def parse_report_file(filepath: Path, timeframe: str, min_grade: str = "C-",
                      min_long_rr: Optional[float] = None,
                      min_short_rr: Optional[float] = None) -> List[PaperTrade]:
    """
    Parse the report file and extract BUY and SELL trades with filters.

    Args:
        filepath: Path to report file
        timeframe: Timeframe of the report (1d, 1wk, 1mo)
        min_grade: Minimum pattern grade to include
        min_long_rr: Minimum R/R for LONG trades
        min_short_rr: Minimum R/R for SHORT trades

    Returns:
        List of PaperTrade objects
    """
    min_long_rr, min_short_rr = resolve_rr_thresholds(timeframe, min_long_rr, min_short_rr)
    with open(filepath, 'r') as f:
        content = f.read()

    trades = []
    sections = content.split('=' * 80)

    current_section = None
    for section in sections:
        if 'BUY SIGNALS' in section:
            current_section = 'BUY'
            continue
        elif 'SELL SIGNALS' in section:
            current_section = 'SELL'
            continue
        elif 'HOLD SIGNALS' in section:
            current_section = 'HOLD'
            continue

        if current_section in ['BUY', 'SELL']:
            trade_blocks = section.split('---' + '-' * 77)

            for block in trade_blocks:
                if not block.strip():
                    continue

                try:
                    # Extract ticker
                    ticker_match = re.search(r'Ticker:\s+(\S+)', block)
                    if not ticker_match:
                        continue
                    ticker = ticker_match.group(1)

                    # Extract detected date
                    analysis_match = re.search(r'Analysis:.*?Detected\s+(\d{4}-\d{2}-\d{2})', block)
                    if not analysis_match:
                        continue
                    detected_date = analysis_match.group(1)

                    # Extract pattern
                    pattern_match = re.search(r'Pattern:\s+([^\n]+)', block)
                    pattern = pattern_match.group(1).strip() if pattern_match else 'Unknown'

                    # Extract grade
                    grade_match = re.search(r'Grade:\s+([A-C][+-]?)', block)
                    grade = grade_match.group(1).strip() if grade_match else 'C-'

                    # Extract entry, stop, and targets
                    entry_match = re.search(r'Entry:\s+\$?([\d.]+)', block)
                    stop_match = re.search(r'Stop Loss:\s+\$?([\d.]+)', block)
                    targets = parse_report_targets(block)
                    rr_match = re.search(r'Risk/Reward:\s+([\d.]+):1', block)

                    if not all([entry_match, stop_match, rr_match]) or targets[0] is None:
                        continue

                    risk_reward = float(rr_match.group(1))

                    # Filter by risk/reward ratio
                    threshold = min_long_rr if current_section == 'BUY' else min_short_rr
                    if risk_reward < threshold:
                        continue

                    # Filter by grade
                    if min_grade and not meets_min_grade(grade, min_grade):
                        continue

                    trade = PaperTrade(
                        ticker=ticker,
                        signal_type=current_section,
                        pattern=pattern,
                        detected_date=detected_date,
                        entry_price=float(entry_match.group(1)),
                        stop_loss=float(stop_match.group(1)),
                        target1=targets[0],
                        target2=targets[1],
                        target3=targets[2],
                        risk_reward=risk_reward,
                        grade=grade,
                        timeframe=timeframe,
                        extracted_date=datetime.now().strftime('%Y-%m-%d'),
                        status="OPEN"
                    )

                    trades.append(trade)

                except Exception as e:
                    print(f"Error parsing trade block: {e}")
                    continue

    return trades


def grade_to_value(grade: str) -> int:
    """Convert grade string to numeric value for comparison."""
    grade_map = {
        'A+': 9, 'A': 8, 'A-': 7,
        'B+': 6, 'B': 5, 'B-': 4,
        'C+': 3, 'C': 2, 'C-': 1
    }
    return grade_map.get(grade, 1)


def meets_min_grade(grade: str, min_grade: str) -> bool:
    """Check if grade meets or exceeds minimum grade requirement."""
    return grade_to_value(grade) >= grade_to_value(min_grade)


def load_existing_trades(filepath: Path) -> Dict[str, Dict]:
    """Load existing paper trades from JSON file"""
    if filepath.exists():
        with open(filepath, 'r') as f:
            trades_list = json.load(f)
            # Convert list to dict with unique IDs as keys
            # Use same unique ID format as PaperTrade.get_unique_id()
            result = {}
            for trade in trades_list:
                pattern_normalized = trade['pattern'].replace(' (BULLISH)', '').replace(' (BEARISH)', '').strip()
                unique_id = f"{trade['ticker']}_{trade['signal_type']}_{pattern_normalized}_{trade['timeframe']}"
                result[unique_id] = trade
            return result
    return {}


def save_trades_to_json(trades: List[Dict], filepath: Path):
    """Save trades to JSON file"""
    # Sort by detected_date (most recent first)
    sorted_trades = sorted(trades, key=lambda x: x['detected_date'], reverse=True)

    with open(filepath, 'w') as f:
        json.dump(sorted_trades, f, indent=2)

    print(f"\nSaved {len(sorted_trades)} trades to {filepath}")


def extract_trades(report_date: str = None, timeframe: str = '1wk',
                   min_grade: str = "C-", min_long_rr: Optional[float] = None,
                   min_short_rr: Optional[float] = None, output_file: str = None):
    """
    Extract trades from report and save to JSON with duplicate prevention.

    Args:
        report_date: Date of report (YYYY-MM-DD), defaults to today
        timeframe: Timeframe of report (1d, 1wk, 1mo)
        min_grade: Minimum pattern grade
        min_long_rr: Minimum R/R for LONG trades
        min_short_rr: Minimum R/R for SHORT trades
        output_file: Output JSON file path
    """
    # Determine paths
    if report_date is None:
        report_date = datetime.now().strftime('%Y-%m-%d')

    base_path = Path(__file__).parent.parent
    report_path = base_path / 'crypto_reports' / report_date / timeframe / f'harmonic_report_{report_date}_{timeframe}.txt'

    if output_file is None:
        output_file = base_path / 'crypto_trades.json'
    else:
        output_file = Path(output_file)

    # Check if report exists
    if not report_path.exists():
        print(f"Error: Report file not found at {report_path}")
        return

    min_long_rr, min_short_rr = resolve_rr_thresholds(timeframe, min_long_rr, min_short_rr)
    print(f"Extracting crypto trades from {report_path}")
    print(f"Filters: Grade >= {min_grade}, LONG R/R >= {min_long_rr}, SHORT R/R >= {min_short_rr}")

    # Parse report
    new_trades = parse_report_file(report_path, timeframe, min_grade, min_long_rr, min_short_rr)
    print(f"\nFound {len(new_trades)} new trades in report")

    # Load existing trades
    existing_trades = load_existing_trades(output_file)
    print(f"Loaded {len(existing_trades)} existing trades from {output_file}")

    # Merge trades (prevent duplicates)
    added_count = 0
    skipped_count = 0
    updated_count = 0

    for trade in new_trades:
        trade_id = trade.get_unique_id()

        if trade_id in existing_trades:
            # Trade already exists - check if we should update or skip
            existing_trade = existing_trades[trade_id]

            if existing_trade['status'] == 'OPEN':
                # Update the trade with new data, but preserve original dates
                new_trade_dict = asdict(trade)
                # Preserve the original extracted_date and detected_date
                new_trade_dict['extracted_date'] = existing_trade['extracted_date']
                new_trade_dict['detected_date'] = existing_trade['detected_date']
                existing_trades[trade_id] = new_trade_dict
                updated_count += 1
            else:
                # Trade is closed or stopped out - don't update
                skipped_count += 1
        else:
            # Add new trade
            existing_trades[trade_id] = asdict(trade)
            added_count += 1

    print(f"\nResults:")
    print(f"  Added: {added_count} new trades")
    print(f"  Updated: {updated_count} existing trades")
    print(f"  Skipped: {skipped_count} closed/stopped trades")
    print(f"  Total trades: {len(existing_trades)}")

    # Save to file
    trades_list = list(existing_trades.values())
    save_trades_to_json(trades_list, output_file)

    # Print summary by status
    status_counts = {}
    for trade in trades_list:
        status = trade['status']
        status_counts[status] = status_counts.get(status, 0) + 1

    print(f"\nTrades by status:")
    for status, count in sorted(status_counts.items()):
        print(f"  {status}: {count}")


def parse_arguments():
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(
        description='Extract trades from harmonic pattern report for paper trading',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Extract from today's weekly report with default filters
  python extract_trades.py

  # Extract from specific date and timeframe
  python extract_trades.py --date 2025-12-25 --timeframe 1d

  # Extract with custom filters
  python extract_trades.py --min-grade B- --min-long-rr 10.0 --min-short-rr 6.0

  # Specify custom output file
  python extract_trades.py --output my_trades.json
        """
    )

    parser.add_argument('--date', help='Report date (YYYY-MM-DD), defaults to today')
    parser.add_argument('--timeframe', default='1wk', choices=['1d', '1wk', '1mo'],
                       help='Timeframe (default: 1wk)')
    parser.add_argument('--min-grade', default='C-',
                       help='Minimum pattern grade (default: C-)')
    parser.add_argument('--min-long-rr', type=float, default=None,
                       help='Minimum LONG R/R (default: scanner timeframe setting)')
    parser.add_argument('--min-short-rr', type=float, default=None,
                       help='Minimum SHORT R/R (default: scanner timeframe setting)')
    parser.add_argument('--output', help='Output JSON file path (default: crypto_trades.json)')

    return parser.parse_args()


def main():
    """Entry point"""
    args = parse_arguments()

    extract_trades(
        report_date=args.date,
        timeframe=args.timeframe,
        min_grade=args.min_grade,
        min_long_rr=args.min_long_rr,
        min_short_rr=args.min_short_rr,
        output_file=args.output
    )


if __name__ == '__main__':
    main()
