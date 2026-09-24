#!/usr/bin/env python3
"""
Analyze harmonic pattern trades from the report file.
For each trade, determine if targets or stop loss were hit and calculate P&L.
"""

# ============================================================================
# IMPORTS
# ============================================================================
import re
import json
import sys
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import yfinance as yf

# Add src directory to path to import config
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
from config import get_timeframe_config, TP_STRATEGY, POSITION_SIZE_T1, POSITION_SIZE_T2, POSITION_SIZE_T3
from tp_strategies.base import target_allocations
from extract_trades import parse_report_targets


# ============================================================================
# CONFIGURATION
# ============================================================================
@dataclass
class AnalysisConfig:
    """Configuration for trade analysis"""
    # Report settings
    timeframe: str = '1wk'
    report_date: str = None  # None = today
    min_grade: str = "C-"

    # Risk/Reward filters
    min_long_rr: float = 12.0
    min_short_rr: float = 4.0

    # Investment parameters
    initial_investment_per_trade: float = 1000.0

    # Analysis modes
    show_detailed_results: bool = True
    save_to_json: bool = True

    # Paths
    reports_base_path: Path = Path(__file__).parent.parent / 'reports'
    results_json_file: Path = Path(__file__).parent.parent / 'config_results.json'


# ============================================================================
# DATA MODELS
# ============================================================================
@dataclass
class Trade:
    """Represents a single harmonic pattern trade"""
    ticker: str
    signal_type: str  # BUY or SELL
    pattern: str
    detected_date: str
    entry_price: float
    stop_loss: float
    target1: Optional[float]
    target2: Optional[float]
    target3: Optional[float]
    current_price: float
    risk_reward: float = 0.0
    grade: str = "C"  # A+, A, A-, B+, B, B-, C+, C, C-

    def __repr__(self):
        return (f"{self.ticker} {self.signal_type} @ ${self.entry_price} "
                f"on {self.detected_date} (R/R: {self.risk_reward}, Grade: {self.grade})")


@dataclass
class AnalysisStatistics:
    """Container for all analysis statistics"""
    total_invested: float
    total_pnl: float
    total_pnl_percent: float
    long_invested: float
    long_pnl: float
    long_pnl_percent: float
    short_invested: float
    short_pnl: float
    short_pnl_percent: float

    wins: List[Dict]
    losses: List[Dict]
    breakeven: List[Dict]
    longs_won: List[Dict]
    shorts_won: List[Dict]
    longs_lost: List[Dict]
    shorts_lost: List[Dict]

    all_results: List[Dict]


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================
def grade_to_value(grade: str) -> int:
    """
    Convert grade string to numeric value for comparison.
    A+ = 9, A = 8, A- = 7, B+ = 6, B = 5, B- = 4, C+ = 3, C = 2, C- = 1
    """
    grade_map = {
        'A+': 9, 'A': 8, 'A-': 7,
        'B+': 6, 'B': 5, 'B-': 4,
        'C+': 3, 'C': 2, 'C-': 1
    }
    return grade_map.get(grade, 1)


def meets_min_grade(grade: str, min_grade: str) -> bool:
    """Check if grade meets or exceeds minimum grade requirement."""
    return grade_to_value(grade) >= grade_to_value(min_grade)


def format_pnl(pnl: float, pnl_percent: float) -> str:
    """Format P&L with sign and percentage"""
    sign = '+' if pnl >= 0 else ''
    return f"{sign}${pnl:,.2f} ({sign}{pnl_percent:.2f}%)"


def calculate_position_pnl(shares: float, entry: float, exit: float, signal_type: str) -> float:
    """Calculate P&L for a position"""
    if signal_type == 'BUY':
        return shares * (exit - entry)
    else:
        return shares * (entry - exit)


def target_hit_before_stop(target_hit: bool, target_date, stop_hit: bool, stop_date) -> bool:
    """
    Check if target was hit before stop loss.
    Conservative approach: same-day hits count as target before stop.
    """
    return target_hit and (not stop_hit or
                          (stop_date is not None and target_date is not None
                           and target_date <= stop_date))


def print_section_header(title: str, width: int = 80, char: str = "="):
    """Print a section header"""
    print("\n" + char * width)
    print(title)
    print(char * width)


def get_report_path(config: AnalysisConfig) -> Path:
    """Get the path to the report file"""
    date = config.report_date or datetime.now().strftime('%Y-%m-%d')
    return (config.reports_base_path / date / config.timeframe /
            f'harmonic_report_{date}_{config.timeframe}.txt')


# ============================================================================
# CORE ANALYSIS FUNCTIONS
# ============================================================================
def parse_report_file(filepath: Path, config: AnalysisConfig) -> Tuple[List[Trade], List[Trade]]:
    """
    Parse the report file and extract BUY and SELL trades with filters.

    Args:
        filepath: Path to report file
        config: Analysis configuration

    Returns:
        Tuple of (buy_trades, sell_trades)
    """
    with open(filepath, 'r') as f:
        content = f.read()

    buy_trades = []
    sell_trades = []
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

                    # Extract current price
                    current_price_match = re.search(r'Current Price:\s+\$?([\d.]+)', block)
                    if not current_price_match:
                        continue
                    current_price = float(current_price_match.group(1))

                    # Extract pattern and detected date
                    analysis_match = re.search(r'Analysis:.*?Detected\s+(\d{4}-\d{2}-\d{2})', block)
                    if not analysis_match:
                        continue
                    detected_date = analysis_match.group(1)

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
                    threshold = config.min_long_rr if current_section == 'BUY' else config.min_short_rr
                    if risk_reward < threshold:
                        continue

                    # Filter by grade
                    if config.min_grade and not meets_min_grade(grade, config.min_grade):
                        continue

                    trade = Trade(
                        ticker=ticker,
                        signal_type=current_section,
                        pattern=pattern,
                        detected_date=detected_date,
                        entry_price=float(entry_match.group(1)),
                        stop_loss=float(stop_match.group(1)),
                        target1=targets[0],
                        target2=targets[1],
                        target3=targets[2],
                        current_price=current_price,
                        risk_reward=risk_reward,
                        grade=grade
                    )

                    if current_section == 'BUY':
                        buy_trades.append(trade)
                    else:
                        sell_trades.append(trade)

                except Exception as e:
                    print(f"Error parsing trade block: {e}")
                    continue

    return buy_trades, sell_trades


def analyze_trade(trade: Trade, config: AnalysisConfig) -> Dict:
    """
    Analyze a single trade to determine if targets or stop loss were hit.

    Args:
        trade: Trade object to analyze
        config: Analysis configuration

    Returns:
        Dict with trade results including P&L
    """
    try:
        allocation1, allocation2, allocation3 = target_allocations(
            (trade.target1, trade.target2, trade.target3),
            (POSITION_SIZE_T1, POSITION_SIZE_T2, POSITION_SIZE_T3),
        )
        # Get historical data
        ticker_obj = yf.Ticker(trade.ticker)
        hist = ticker_obj.history(start=trade.detected_date, end=datetime.now())

        if hist.empty:
            return {
                'ticker': trade.ticker,
                'signal_type': trade.signal_type,
                'risk_reward': trade.risk_reward,
                'status': 'NO_DATA',
                'pnl': 0,
                'pnl_percent': 0,
                'reason': 'No historical data available'
            }

        # Track target and stop hits
        t1_hit, t2_hit, t3_hit, stop_hit = False, False, False, False
        t1_date, t2_date, t3_date, stop_date = None, None, None, None

        # Check each day's price action
        for date, row in hist.iterrows():
            high, low = row['High'], row['Low']

            if trade.signal_type == 'BUY':
                # Long trades
                if not stop_hit and low <= trade.stop_loss:
                    stop_hit, stop_date = True, date
                if trade.target1 is not None and not t1_hit and high >= trade.target1:
                    t1_hit, t1_date = True, date
                if trade.target2 is not None and t1_hit and not t2_hit and high >= trade.target2:
                    t2_hit, t2_date = True, date
                if trade.target3 is not None and t2_hit and not t3_hit and high >= trade.target3:
                    t3_hit, t3_date = True, date
            else:
                # Short trades
                if not stop_hit and high >= trade.stop_loss:
                    stop_hit, stop_date = True, date
                if trade.target1 is not None and not t1_hit and low <= trade.target1:
                    t1_hit, t1_date = True, date
                if trade.target2 is not None and t1_hit and not t2_hit and low <= trade.target2:
                    t2_hit, t2_date = True, date
                if trade.target3 is not None and t2_hit and not t3_hit and low <= trade.target3:
                    t3_hit, t3_date = True, date

        # Calculate P&L with partial profit-taking
        shares = config.initial_investment_per_trade / trade.entry_price
        shares_t1 = shares * allocation1
        shares_t2 = shares * allocation2
        shares_t3 = shares * allocation3

        total_pnl = 0
        status_parts = []
        remaining_position = 1.0

        # Check which targets hit before stop
        t1_before_stop = target_hit_before_stop(t1_hit, t1_date, stop_hit, stop_date)
        t2_before_stop = target_hit_before_stop(t2_hit, t2_date, stop_hit, stop_date)
        t3_before_stop = target_hit_before_stop(t3_hit, t3_date, stop_hit, stop_date)

        # T1
        if t1_before_stop:
            total_pnl += calculate_position_pnl(shares_t1, trade.entry_price, trade.target1, trade.signal_type)
            remaining_position -= allocation1
            status_parts.append(f"T1 on {t1_date.strftime('%Y-%m-%d')}")

        # T2
        if t2_before_stop:
            total_pnl += calculate_position_pnl(shares_t2, trade.entry_price, trade.target2, trade.signal_type)
            remaining_position -= allocation2
            status_parts.append(f"T2 on {t2_date.strftime('%Y-%m-%d')}")

        # T3
        if t3_before_stop:
            total_pnl += calculate_position_pnl(shares_t3, trade.entry_price, trade.target3, trade.signal_type)
            remaining_position -= allocation3
            status_parts.append(f"T3 on {t3_date.strftime('%Y-%m-%d')}")

        remaining_position = max(0.0, round(remaining_position, 12))

        # Remaining position
        if stop_hit and remaining_position > 0:
            remaining_shares = shares * remaining_position
            total_pnl += calculate_position_pnl(remaining_shares, trade.entry_price, trade.stop_loss, trade.signal_type)
            status_parts.append(f"Stop on {stop_date.strftime('%Y-%m-%d')}")
        elif remaining_position > 0:
            remaining_shares = shares * remaining_position
            total_pnl += calculate_position_pnl(remaining_shares, trade.entry_price, trade.current_price, trade.signal_type)

        # Determine status
        if total_pnl < 0:
            status = 'STOPPED_OUT'
            reason = ', '.join(status_parts)
        elif remaining_position == 0:
            status = 'FULL_WIN'
            reason = ', '.join(status_parts)
        elif len([s for s in status_parts if 'T' in s]) > 0:
            status = 'PARTIAL_WIN'
            reason = ', '.join(status_parts)
            if remaining_position > 0 and not stop_hit:
                reason += f", remaining position open at ${trade.current_price}"
        else:
            status = 'OPEN'
            reason = f"No targets hit yet, current price ${trade.current_price}"

        pnl_percent = (total_pnl / config.initial_investment_per_trade) * 100

        return {
            'ticker': trade.ticker,
            'signal_type': trade.signal_type,
            'entry_price': trade.entry_price,
            'detected_date': trade.detected_date,
            'risk_reward': trade.risk_reward,
            'status': status,
            'pnl': total_pnl,
            'pnl_percent': pnl_percent,
            'reason': reason,
            't1_hit': t1_before_stop,
            't2_hit': t2_before_stop,
            't3_hit': t3_before_stop,
            'stop_hit': stop_hit
        }

    except Exception as e:
        return {
            'ticker': trade.ticker,
            'signal_type': trade.signal_type,
            'risk_reward': trade.risk_reward,
            'status': 'ERROR',
            'pnl': 0,
            'pnl_percent': 0,
            'reason': f'Error: {str(e)}'
        }


# ============================================================================
# STATISTICS CALCULATION
# ============================================================================
def calculate_statistics(results: List[Dict], config: AnalysisConfig) -> AnalysisStatistics:
    """Calculate all statistics from results"""

    # Overall statistics
    total_invested = len(results) * config.initial_investment_per_trade
    total_pnl = sum(r['pnl'] for r in results)
    total_pnl_percent = (total_pnl / total_invested * 100) if total_invested > 0 else 0

    # Long/Short breakdown
    long_results = [r for r in results if r['signal_type'] == 'BUY']
    short_results = [r for r in results if r['signal_type'] == 'SELL']

    long_invested = len(long_results) * config.initial_investment_per_trade
    short_invested = len(short_results) * config.initial_investment_per_trade

    long_pnl = sum(r['pnl'] for r in long_results)
    short_pnl = sum(r['pnl'] for r in short_results)

    long_pnl_percent = (long_pnl / long_invested * 100) if long_invested > 0 else 0
    short_pnl_percent = (short_pnl / short_invested * 100) if short_invested > 0 else 0

    # Win/Loss categorization
    wins = [r for r in results if r['pnl'] > 0]
    losses = [r for r in results if r['pnl'] < 0]
    breakeven = [r for r in results if r['pnl'] == 0]

    longs_won = [r for r in wins if r['signal_type'] == 'BUY']
    shorts_won = [r for r in wins if r['signal_type'] == 'SELL']
    longs_lost = [r for r in losses if r['signal_type'] == 'BUY']
    shorts_lost = [r for r in losses if r['signal_type'] == 'SELL']

    return AnalysisStatistics(
        total_invested=total_invested,
        total_pnl=total_pnl,
        total_pnl_percent=total_pnl_percent,
        long_invested=long_invested,
        long_pnl=long_pnl,
        long_pnl_percent=long_pnl_percent,
        short_invested=short_invested,
        short_pnl=short_pnl,
        short_pnl_percent=short_pnl_percent,
        wins=wins,
        losses=losses,
        breakeven=breakeven,
        longs_won=longs_won,
        shorts_won=shorts_won,
        longs_lost=longs_lost,
        shorts_lost=shorts_lost,
        all_results=results
    )


# ============================================================================
# DISPLAY FUNCTIONS
# ============================================================================
def print_summary_stats(stats: AnalysisStatistics, config: AnalysisConfig):
    """Print summary statistics"""
    print_section_header(f"TRADE ANALYSIS SUMMARY (LONG R/R >= {config.min_long_rr}, SHORT R/R >= {config.min_short_rr})")

    print(f"\nTotal Trades Analyzed: {len(stats.all_results)}")
    print(f"Total Capital Invested: ${stats.total_invested:,.2f}")
    print(f"\nWinning Trades: {len(stats.wins)}")
    print(f"Longs Won: {len(stats.longs_won)} | Shorts Won: {len(stats.shorts_won)}")
    print(f"Losing Trades: {len(stats.losses)}")
    print(f"Longs Lost: {len(stats.longs_lost)} | Shorts Lost: {len(stats.shorts_lost)}")
    print(f"Breakeven/Open Trades: {len(stats.breakeven)}")


def print_pnl_breakdown(stats: AnalysisStatistics):
    """Print P&L breakdown by long/short"""
    print_section_header("P&L BREAKDOWN", char="-")

    # Long P&L
    long_results = [r for r in stats.all_results if r['signal_type'] == 'BUY']
    print(f"\nLong Trades ({len(long_results)} trades):")
    print(f"  Capital Invested: ${stats.long_invested:,.2f}")
    print(f"  P&L: {format_pnl(stats.long_pnl, stats.long_pnl_percent)}")

    # Short P&L
    short_results = [r for r in stats.all_results if r['signal_type'] == 'SELL']
    print(f"\nShort Trades ({len(short_results)} trades):")
    print(f"  Capital Invested: ${stats.short_invested:,.2f}")
    print(f"  P&L: {format_pnl(stats.short_pnl, stats.short_pnl_percent)}")

    # Overall P&L
    print(f"\nOverall (All Trades):")
    print(f"  Total Capital Invested: ${stats.total_invested:,.2f}")
    print(f"  Total P&L: {format_pnl(stats.total_pnl, stats.total_pnl_percent)}")

    if stats.wins:
        avg_win = sum(r['pnl'] for r in stats.wins) / len(stats.wins)
        print(f"\nAverage Win: ${avg_win:.2f}")

    if stats.losses:
        avg_loss = sum(r['pnl'] for r in stats.losses) / len(stats.losses)
        print(f"Average Loss: ${avg_loss:.2f}")


def print_detailed_results(results: List[Dict], title: str):
    """Print detailed trade results"""
    print_section_header(title)

    for result in sorted(results, key=lambda x: x['pnl'], reverse=True):
        pnl_sign = '+' if result['pnl'] >= 0 else ''
        print(f"\n{result['ticker']} ({result['signal_type']}) - "
              f"Entry: ${result.get('entry_price', 'N/A')} on {result.get('detected_date', 'N/A')} | "
              f"R/R: {result.get('risk_reward', 'N/A')}")
        print(f"  Status: {result['status']}")
        print(f"  P&L: {pnl_sign}${result['pnl']:.2f} ({pnl_sign}{result['pnl_percent']:.2f}%)")
        print(f"  Details: {result['reason']}")


# ============================================================================
# FILE I/O FUNCTIONS
# ============================================================================
def load_config_results(filepath: Path) -> List[Dict]:
    """Load existing configuration results from JSON file"""
    if filepath.exists():
        with open(filepath, 'r') as f:
            return json.load(f)
    return []


def save_config_results(filepath: Path, all_results: List[Dict]):
    """Save configuration results to JSON file, sorted by total_pnl_percentage"""
    sorted_results = sorted(all_results, key=lambda x: x['results']['total_pnl_percentage'], reverse=True)
    with open(filepath, 'w') as f:
        json.dump(sorted_results, f, indent=2)
    print(f"\nJSON results saved to: {filepath}")


def save_results_to_json(stats: AnalysisStatistics, config: AnalysisConfig):
    """Save current analysis run to JSON file"""
    timeframe_config = get_timeframe_config(config.timeframe)

    new_entry = {
        "config": {
            "timeframe": config.timeframe,
            "MIN_RISK_REWARD": f"LONG:{config.min_long_rr}/SHORT:{config.min_short_rr}",
            "SWING_WINDOW": timeframe_config['SWING_WINDOW'],
            "DATA_PERIOD": timeframe_config['DATA_PERIOD'],
            "MIN_ALLOWED_STOP_LOSS_PCT": timeframe_config['MIN_ALLOWED_STOP_LOSS_PCT'],
            "MAX_ALLOWED_STOP_LOSS_PCT": timeframe_config['MAX_ALLOWED_STOP_LOSS_PCT'],
            "Trading Algorithm": TP_STRATEGY,
            "Min Pattern Grade": config.min_grade
        },
        "results": {
            "total_trades": len(stats.all_results),
            "winning_trades": len(stats.wins),
            "winning_longs": len(stats.longs_won),
            "winning_shorts": len(stats.shorts_won),
            "losing_trades": len(stats.losses),
            "longs_lost": len(stats.longs_lost),
            "shorts_lost": len(stats.shorts_lost),
            "breakeven_trades": len(stats.breakeven),
            "total_pnl_percentage": round(stats.total_pnl_percent, 2),
            "total_pnl_dollars": round(stats.total_pnl, 2),
            "total_invested": stats.total_invested,
            "long_trades": len([r for r in stats.all_results if r['signal_type'] == 'BUY']),
            "long_pnl_percentage": round(stats.long_pnl_percent, 2),
            "long_pnl_dollars": round(stats.long_pnl, 2),
            "long_invested": stats.long_invested,
            "short_trades": len([r for r in stats.all_results if r['signal_type'] == 'SELL']),
            "short_pnl_percentage": round(stats.short_pnl_percent, 2),
            "short_pnl_dollars": round(stats.short_pnl, 2),
            "short_invested": stats.short_invested
        },
        "metadata": {
            "analyzed_at": datetime.now().isoformat()
        }
    }

    all_results = load_config_results(config.results_json_file)
    all_results.append(new_entry)
    save_config_results(config.results_json_file, all_results)


# ============================================================================
# MAIN ORCHESTRATION
# ============================================================================
def run_analysis(config: AnalysisConfig):
    """Main analysis orchestration"""

    # Get report path
    report_path = get_report_path(config)

    # Build filter message
    filter_parts = [f"LONG R/R >= {config.min_long_rr}", f"SHORT R/R >= {config.min_short_rr}"]
    if config.min_grade:
        filter_parts.append(f"Grade >= {config.min_grade}")
    filter_msg = f" (filtering for {', '.join(filter_parts)})"

    # Parse report file
    print(f"Parsing report file{filter_msg}...")
    buy_trades, sell_trades = parse_report_file(report_path, config)

    print(f"\nFound {len(buy_trades)} BUY signals and {len(sell_trades)} SELL signals{filter_msg}")
    print(f"Total trades to analyze: {len(buy_trades) + len(sell_trades)}\n")

    if len(buy_trades) + len(sell_trades) == 0:
        print("No trades found matching criteria.")
        return

    # Analyze all trades
    all_trades = buy_trades + sell_trades
    results = []

    print("Analyzing trades...")
    for i, trade in enumerate(all_trades, 1):
        print(f"[{i}/{len(all_trades)}] Analyzing {trade.ticker} (R/R: {trade.risk_reward})...")
        result = analyze_trade(trade, config)
        results.append(result)

    # Calculate statistics
    stats = calculate_statistics(results, config)

    # Display results
    print_summary_stats(stats, config)
    print_pnl_breakdown(stats)

    if config.show_detailed_results:
        print_detailed_results(stats.all_results, "DETAILED TRADE RESULTS")

    # Save to JSON
    if config.save_to_json:
        save_results_to_json(stats, config)


def parse_arguments() -> AnalysisConfig:
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(
        description='Analyze harmonic pattern trades',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze with default settings (1wk timeframe)
  python analyze_trades.py

  # Analyze 1d timeframe with custom R/R thresholds
  python analyze_trades.py --timeframe 1d --min-long-rr 15.0 --min-short-rr 6.0

  # Analyze specific date
  python analyze_trades.py --date 2025-12-20

  # Analyze with minimum grade filter
  python analyze_trades.py --min-grade B-

  # Quick analysis without detailed results
  python analyze_trades.py --no-details
        """
    )

    parser.add_argument('--timeframe', default=None,
                       choices=['1d', '1wk', '1mo'],
                       help='Timeframe to analyze (default: 1wk)')
    parser.add_argument('--date',
                       help='Report date in YYYY-MM-DD format (default: today)')
    parser.add_argument('--min-long-rr', type=float, default=None,
                       help='Minimum R/R for LONG trades (default: 10.0)')
    parser.add_argument('--min-short-rr', type=float, default=None,
                       help='Minimum R/R for SHORT trades (default: 4.0)')
    parser.add_argument('--min-grade', default=None,
                       help='Minimum pattern grade (default: C-)')
    parser.add_argument('--investment', type=float, default=None,
                       help='Investment per trade in dollars (default: 1000.0)')
    parser.add_argument('--no-details', action='store_true',
                       help='Skip detailed trade results')
    parser.add_argument('--no-save', action='store_true',
                       help='Do not save results to JSON')

    args = parser.parse_args()

    # Create config with defaults from dataclass, override only if specified
    config = AnalysisConfig()

    if args.timeframe is not None:
        config.timeframe = args.timeframe
    if args.date is not None:
        config.report_date = args.date
    if args.min_grade is not None:
        config.min_grade = args.min_grade
    if args.min_long_rr is not None:
        config.min_long_rr = args.min_long_rr
    if args.min_short_rr is not None:
        config.min_short_rr = args.min_short_rr
    if args.investment is not None:
        config.initial_investment_per_trade = args.investment

    config.show_detailed_results = not args.no_details
    config.save_to_json = not args.no_save

    return config


def main():
    """Entry point"""
    config = parse_arguments()
    run_analysis(config)


if __name__ == '__main__':
    main()
