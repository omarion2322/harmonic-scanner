#!/usr/bin/env python3
"""
Analyze harmonic pattern trades from the report file.
For each trade, determine if targets or stop loss were hit and calculate P&L.
"""

import re
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import yfinance as yf
from dataclasses import dataclass

from narwhals import Datetime


def grade_to_value(grade: str) -> int:
    """
    Convert grade string to numeric value for comparison.
    A+ = 9, A = 8, A- = 7, B+ = 6, B = 5, B- = 4, C+ = 3, C = 2, C- = 1
    Higher values = better grades.
    """
    grade_map = {
        'A+': 9, 'A': 8, 'A-': 7,
        'B+': 6, 'B': 5, 'B-': 4,
        'C+': 3, 'C': 2, 'C-': 1
    }
    return grade_map.get(grade, 1)  # Default to C- if grade not recognized


def meets_min_grade(grade: str, min_grade: str) -> bool:
    """
    Check if grade meets or exceeds minimum grade requirement.
    Returns True if grade >= min_grade.

    Examples:
        meets_min_grade('A', 'B-') -> True
        meets_min_grade('C+', 'B-') -> False
        meets_min_grade('B-', 'B-') -> True
    """
    return grade_to_value(grade) >= grade_to_value(min_grade)


# Add src directory to path to import config_timeframes
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
from config_timeframes import get_timeframe_config
from config import TP_STRATEGY

@dataclass
class Trade:
    ticker: str
    signal_type: str  # BUY or SELL
    pattern: str
    detected_date: str
    entry_price: float
    stop_loss: float
    target1: float
    target2: float
    target3: float
    current_price: float
    risk_reward: float = 0.0
    grade: str = "C"  # A+, A, A-, B+, B, B-, C+, C, C-

    def __repr__(self):
        return f"{self.ticker} {self.signal_type} @ ${self.entry_price} on {self.detected_date} (R/R: {self.risk_reward}, Grade: {self.grade})"


def parse_report_file(filepath: str, min_rr: float = 0, min_grade: str = '') -> Tuple[List[Trade], List[Trade]]:
    """Parse the report file and extract BUY and SELL trades with optional R/R and grade filters."""
    with open(filepath, 'r') as f:
        content = f.read()

    buy_trades = []
    sell_trades = []

    # Split into sections
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
            # Parse individual trades in this section
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
                    t1_match = re.search(r'Target 1:\s+\$?([\d.]+)', block)
                    t2_match = re.search(r'Target 2:\s+\$?([\d.]+)', block)
                    t3_match = re.search(r'Target 3:\s+\$?([\d.]+)', block)

                    # Extract risk/reward ratio
                    rr_match = re.search(r'Risk/Reward:\s+([\d.]+):1', block)

                    if not all([entry_match, stop_match, t1_match, t2_match, t3_match, rr_match]):
                        continue

                    risk_reward = float(rr_match.group(1))

                    # Filter by risk/reward ratio
                    if risk_reward < min_rr:
                        continue

                    # Filter by grade
                    if min_grade and not meets_min_grade(grade, min_grade):
                        continue

                    trade = Trade(
                        ticker=ticker,
                        signal_type=current_section,
                        pattern=pattern,
                        detected_date=detected_date,
                        entry_price=float(entry_match.group(1)),
                        stop_loss=float(stop_match.group(1)),
                        target1=float(t1_match.group(1)),
                        target2=float(t2_match.group(1)),
                        target3=float(t3_match.group(1)),
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


def analyze_trade(trade: Trade) -> Dict:
    """
    Analyze a single trade to determine if targets or stop loss were hit.
    Returns a dict with trade results including P&L.
    """
    try:
        # Get historical data from detected date to today
        start_date = trade.detected_date
        end_date = datetime.now()

        ticker_obj = yf.Ticker(trade.ticker)
        hist = ticker_obj.history(start=start_date, end=end_date)

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

        # Track what happened
        t1_hit = False
        t2_hit = False
        t3_hit = False
        stop_hit = False

        t1_date = None
        t2_date = None
        t3_date = None
        stop_date = None

        # Check each day's price action
        for date, row in hist.iterrows():
            high = row['High']
            low = row['Low']

            if trade.signal_type == 'BUY':
                # For long trades
                # Check stop loss (downside)
                if not stop_hit and low <= trade.stop_loss:
                    stop_hit = True
                    stop_date = date

                # Check targets (upside)
                if not t1_hit and high >= trade.target1:
                    t1_hit = True
                    t1_date = date

                if t1_hit and not t2_hit and high >= trade.target2:
                    t2_hit = True
                    t2_date = date

                if t2_hit and not t3_hit and high >= trade.target3:
                    t3_hit = True
                    t3_date = date

            else:  # SELL signal (short trade)
                # For short trades
                # Check stop loss (upside)
                if not stop_hit and high >= trade.stop_loss:
                    stop_hit = True
                    stop_date = date

                # Check targets (downside)
                if not t1_hit and low <= trade.target1:
                    t1_hit = True
                    t1_date = date

                if t1_hit and not t2_hit and low <= trade.target2:
                    t2_hit = True
                    t2_date = date

                if t2_hit and not t3_hit and low <= trade.target3:
                    t3_hit = True
                    t3_date = date

        # Calculate P&L based on $1000 initial investment
        initial_investment = 1000
        shares = initial_investment / trade.entry_price

        # Position sizing: T1=33%, T2=33%, T3=34%
        shares_t1 = shares * 0.33
        shares_t2 = shares * 0.33
        shares_t3 = shares * 0.34

        total_pnl = 0
        status_parts = []

        # Determine which targets were hit before stop loss (if any)
        # Use <= to handle same-day hits (assume targets hit before stop on same day)
        t1_hit_before_stop = t1_hit and (not stop_hit or (stop_hit and t1_date <= stop_date))
        t2_hit_before_stop = t2_hit and (not stop_hit or (stop_hit and t2_date <= stop_date))
        t3_hit_before_stop = t3_hit and (not stop_hit or (stop_hit and t3_date <= stop_date))

        # Calculate P&L for each target hit before stop loss
        remaining_position = 1.0  # Track remaining position percentage

        if t1_hit_before_stop:
            if trade.signal_type == 'BUY':
                pnl_t1 = shares_t1 * (trade.target1 - trade.entry_price)
            else:
                pnl_t1 = shares_t1 * (trade.entry_price - trade.target1)

            total_pnl += pnl_t1
            remaining_position -= 0.33
            status_parts.append(f"T1 on {t1_date.strftime('%Y-%m-%d')}")

        if t2_hit_before_stop:
            if trade.signal_type == 'BUY':
                pnl_t2 = shares_t2 * (trade.target2 - trade.entry_price)
            else:
                pnl_t2 = shares_t2 * (trade.entry_price - trade.target2)
            total_pnl += pnl_t2
            remaining_position -= 0.33
            status_parts.append(f"T2 on {t2_date.strftime('%Y-%m-%d')}")

        if t3_hit_before_stop:
            if trade.signal_type == 'BUY':
                pnl_t3 = shares_t3 * (trade.target3 - trade.entry_price)
            else:
                pnl_t3 = shares_t3 * (trade.entry_price - trade.target3)
            total_pnl += pnl_t3
            remaining_position -= 0.34
            status_parts.append(f"T3 on {t3_date.strftime('%Y-%m-%d')}")

        # Calculate P&L for remaining position
        if stop_hit and remaining_position > 0:
            # Stop loss hit on remaining shares
            remaining_shares = shares * remaining_position
            if trade.signal_type == 'BUY':
                stop_pnl = remaining_shares * (trade.stop_loss - trade.entry_price)
            else:
                stop_pnl = remaining_shares * (trade.entry_price - trade.stop_loss)
            total_pnl += stop_pnl
            status_parts.append(f"Stop on {stop_date.strftime('%Y-%m-%d')}")
        elif remaining_position > 0:
            # Position still open, calculate unrealized P&L on remaining shares
            remaining_shares = shares * remaining_position
            if trade.signal_type == 'BUY':
                unrealized_pnl = remaining_shares * (trade.current_price - trade.entry_price)
            else:
                unrealized_pnl = remaining_shares * (trade.entry_price - trade.current_price)
            total_pnl += unrealized_pnl

        pnl_percent = (total_pnl / initial_investment) * 100

        # Determine status based on final P&L
        if total_pnl < 0:
            # Negative P&L = loss, always STOPPED_OUT
            status = 'STOPPED_OUT'
            reason = ', '.join(status_parts)
        elif remaining_position == 0:
            # All targets hit
            status = 'FULL_WIN'
            reason = ', '.join(status_parts)
        elif len([s for s in status_parts if 'T' in s]) > 0:
            # Some targets hit and P&L positive
            status = 'PARTIAL_WIN'
            reason = ', '.join(status_parts)
            if remaining_position > 0 and not stop_hit:
                reason += f", remaining position open at ${trade.current_price}"
        else:
            # No targets hit, still open
            status = 'OPEN'
            reason = f"No targets hit yet, current price ${trade.current_price}"

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
            't1_hit': t1_hit,
            't2_hit': t2_hit,
            't3_hit': t3_hit,
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


# JSON Results Storage
RESULTS_JSON_FILE = Path(__file__).parent.parent / 'config_results.json'


def load_config_results() -> List[Dict]:
    """Load existing configuration results from JSON file."""
    if RESULTS_JSON_FILE.exists():
        with open(RESULTS_JSON_FILE, 'r') as f:
            return json.load(f)
    return []


def save_config_results(all_results: List[Dict]):
    """Save configuration results to JSON file, sorted by total_pnl_percentage (highest to lowest)."""
    # Sort by total_pnl_percentage descending
    sorted_results = sorted(all_results, key=lambda x: x['results']['total_pnl_percentage'], reverse=True)

    with open(RESULTS_JSON_FILE, 'w') as f:
        json.dump(sorted_results, f, indent=2)

    print(f"\nJSON results saved to: {RESULTS_JSON_FILE}")


def save_current_run(
    timeframe: str,
    min_risk_reward: float,
    swing_window: int,
    data_period: str,
    min_stop_loss_pct: float,
    max_stop_loss_pct: float,
    trading_algo: str,
    min_grade: str,
    total_trades: int,
    winning_trades: int,
    winning_longs: int,
    winning_shorts: int,
    losing_trades: int,
    longs_lost: int,
    shorts_lost: int,
    breakeven_trades: int,
    total_pnl_percentage: float,
    total_pnl_dollars: float,
    total_invested: float
):
    """
    Save the current analysis run to the JSON results file.
    Creates a new entry with config and results, then sorts all entries by total_pnl_percentage.
    """
    # Create new result entry
    new_entry = {
        "config": {
            "timeframe": timeframe,
            "MIN_RISK_REWARD": min_risk_reward,
            "SWING_WINDOW": swing_window,
            "DATA_PERIOD": data_period,
            "MIN_ALLOWED_STOP_LOSS_PCT": min_stop_loss_pct,
            "MAX_ALLOWED_STOP_LOSS_PCT": max_stop_loss_pct,
            "Trading Algorithm": trading_algo,
            "Min Pattern Grade": min_grade
        },
        "results": {
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "winning_longs": winning_longs,
            "winning_shorts": winning_shorts,
            "losing_trades": losing_trades,
            "longs_lost": longs_lost,
            "shorts_lost": shorts_lost,
            "breakeven_trades": breakeven_trades,
            "total_pnl_percentage": round(total_pnl_percentage, 2),
            "total_pnl_dollars": round(total_pnl_dollars, 2),
            "total_invested": total_invested
        },
        "metadata": {
            "analyzed_at": datetime.now().isoformat()
        }
    }

    # Load existing results
    all_results = load_config_results()

    # Add new entry
    all_results.append(new_entry)

    # Save sorted results
    save_config_results(all_results)


def main():
    date = '2025-12-10'
    timeframe = '1wk'
    min_grade = "B-"
    report_file = f'./reports/{date}/{timeframe}/harmonic_report_{date}_{timeframe}.txt'

    # Load configuration from config_timeframes.py
    config = get_timeframe_config(timeframe)

    # Configuration Parameters (can override MIN_RISK_REWARD if needed)
    MIN_RISK_REWARD = 3.0  # Set this to test different R/R ratios
    TRADING_ALGO_USED = TP_STRATEGY
    SWING_WINDOW = config['SWING_WINDOW']
    DATA_PERIOD = config['DATA_PERIOD']
    MIN_ALLOWED_STOP_LOSS_PCT = config['MIN_ALLOWED_STOP_LOSS_PCT']
    MAX_ALLOWED_STOP_LOSS_PCT = config['MAX_ALLOWED_STOP_LOSS_PCT']

    filter_msg_parts = []
    if MIN_RISK_REWARD > 0:
        filter_msg_parts.append(f"R/R >= {MIN_RISK_REWARD}")
    if min_grade:
        filter_msg_parts.append(f"Grade >= {min_grade}")
    filter_msg = f" (filtering for {', '.join(filter_msg_parts)})" if filter_msg_parts else ""

    print(f"Parsing report file{filter_msg}...")
    buy_trades, sell_trades = parse_report_file(report_file, min_rr=MIN_RISK_REWARD, min_grade=min_grade)

    print(f"\nFound {len(buy_trades)} BUY signals and {len(sell_trades)} SELL signals{filter_msg}")
    print(f"Total trades to analyze: {len(buy_trades) + len(sell_trades)}\n")

    all_trades = buy_trades + sell_trades
    results = []

    print("Analyzing trades...")
    for i, trade in enumerate(all_trades, 1):
        print(f"[{i}/{len(all_trades)}] Analyzing {trade.ticker} (R/R: {trade.risk_reward})...")
        result = analyze_trade(trade)
        results.append(result)

    # Calculate summary statistics
    total_invested = len(results) * 1000  # $1000 per trade
    total_pnl = sum(r['pnl'] for r in results)
    total_pnl_percent = (total_pnl / total_invested) * 100

    # Categorize results
    wins = [r for r in results if r['pnl'] > 0]
    losses = [r for r in results if r['pnl'] < 0]
    breakeven = [r for r in results if r['pnl'] == 0]

    longs_won = [r for r in wins if r['signal_type'] == 'BUY']
    shorts_won = [r for r in wins if r['signal_type'] == 'SELL']
    longs_lost = [r for r in losses if r['signal_type'] == 'BUY']
    shorts_lost = [r for r in losses if r['signal_type'] == 'SELL']

    print("\n" + "=" * 80)
    summary_title = f"TRADE ANALYSIS SUMMARY (R/R >= {MIN_RISK_REWARD})" if MIN_RISK_REWARD > 0 else "TRADE ANALYSIS SUMMARY"
    print(summary_title)
    print("=" * 80)
    print(f"\nTotal Trades Analyzed: {len(results)}")
    print(f"Total Capital Invested: ${total_invested:,.2f}")
    print(f"\nWinning Trades: {len(wins)}")
    print(f"Longs Won: {len(longs_won)} | Shorts Won: {len(shorts_won)}")
    print(f"Losing Trades: {len(losses)}")
    print(f"Longs Lost: {len(longs_lost)} | Shorts Lost: {len(shorts_lost)}")
    print(f"Breakeven/Open Trades: {len(breakeven)}")
    print(f"\nTotal P&L: ${total_pnl:,.2f}")
    print(f"Total P&L %: {total_pnl_percent:.2f}%")

    if wins:
        avg_win = sum(r['pnl'] for r in wins) / len(wins)
        print(f"\nAverage Win: ${avg_win:.2f}")

    if losses:
        avg_loss = sum(r['pnl'] for r in losses) / len(losses)
        print(f"Average Loss: ${avg_loss:.2f}")

    # Show detailed results
    print("\n" + "=" * 80)
    print("DETAILED TRADE RESULTS")
    print("=" * 80)

    for result in sorted(results, key=lambda x: x['pnl'], reverse=True):
        pnl_sign = '+' if result['pnl'] >= 0 else ''
        print(f"\n{result['ticker']} ({result['signal_type']}) - Entry: ${result.get('entry_price', 'N/A')} on {result.get('detected_date', 'N/A')} | R/R: {result.get('risk_reward', 'N/A')}")
        print(f"  Status: {result['status']}")
        print(f"  P&L: {pnl_sign}${result['pnl']:.2f} ({pnl_sign}{result['pnl_percent']:.2f}%)")
        print(f"  Details: {result['reason']}")

    # Save to JSON results file with configuration
    save_current_run(
        timeframe=timeframe,
        min_risk_reward=MIN_RISK_REWARD,
        swing_window=SWING_WINDOW,
        data_period=DATA_PERIOD,
        min_stop_loss_pct=MIN_ALLOWED_STOP_LOSS_PCT,
        max_stop_loss_pct=MAX_ALLOWED_STOP_LOSS_PCT,
        trading_algo=TRADING_ALGO_USED,
        min_grade=min_grade,
        total_trades=len(results),
        winning_trades=len(wins),
        winning_longs=len(longs_won),
        winning_shorts=len(shorts_won),
        losing_trades=len(losses),
        longs_lost=len(longs_lost),
        shorts_lost=len(shorts_lost),
        breakeven_trades=len(breakeven),
        total_pnl_percentage=total_pnl_percent,
        total_pnl_dollars=total_pnl,
        total_invested=total_invested
    )


if __name__ == '__main__':
    main()
