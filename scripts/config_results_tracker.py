#!/usr/bin/env python3
"""
Configuration Results Tracker for Harmonic Pattern Trading
Tracks and saves results from different configuration combinations
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from analyze_trades import parse_report_file, analyze_trade

# Results storage file
RESULTS_FILE = Path(__file__).parent.parent / 'config_results.json'


def load_existing_results() -> List[Dict]:
    """Load existing results from JSON file."""
    if RESULTS_FILE.exists():
        with open(RESULTS_FILE, 'r') as f:
            return json.load(f)
    return []


def save_results(results: List[Dict]):
    """Save results to JSON file, sorted by total_pnl_percentage."""
    # Sort by total_pnl_percentage descending
    sorted_results = sorted(results, key=lambda x: x['results']['total_pnl_percentage'], reverse=True)

    with open(RESULTS_FILE, 'w') as f:
        json.dump(sorted_results, f, indent=2)

    print(f"\nResults saved to: {RESULTS_FILE}")


def analyze_with_config(
    report_file: str,
    timeframe: str,
    min_risk_reward: float,
    swing_window: int,
    data_period: str,
    min_stop_loss_pct: float,
    max_stop_loss_pct: float
) -> Dict:
    """
    Run trade analysis and return results with configuration.

    Returns:
        Dictionary with 'config' and 'results' keys
    """
    print(f"\nAnalyzing configuration:")
    print(f"  Timeframe: {timeframe}")
    print(f"  MIN_RISK_REWARD: {min_risk_reward}")
    print(f"  SWING_WINDOW: {swing_window}")
    print(f"  DATA_PERIOD: {data_period}")
    print(f"  Stop Loss Range: {min_stop_loss_pct}% - {max_stop_loss_pct}%")

    # Parse trades with risk/reward filter
    buy_trades, sell_trades = parse_report_file(report_file, min_rr=min_risk_reward)

    print(f"\nFound {len(buy_trades)} BUY signals and {len(sell_trades)} SELL signals")

    all_trades = buy_trades + sell_trades
    results_list = []

    print("Analyzing trades...")
    for i, trade in enumerate(all_trades, 1):
        print(f"[{i}/{len(all_trades)}] Analyzing {trade.ticker}...")
        result = analyze_trade(trade)
        results_list.append(result)

    # Calculate summary statistics
    total_trades = len(results_list)
    total_invested = total_trades * 1000
    total_pnl = sum(r['pnl'] for r in results_list)
    total_pnl_percentage = (total_pnl / total_invested * 100) if total_invested > 0 else 0

    # Categorize results
    wins = [r for r in results_list if r['pnl'] > 0]
    losses = [r for r in results_list if r['pnl'] < 0]
    breakeven = [r for r in results_list if r['pnl'] == 0]

    longs_won = len([r for r in wins if r['signal_type'] == 'BUY'])
    shorts_won = len([r for r in wins if r['signal_type'] == 'SELL'])
    longs_lost = len([r for r in losses if r['signal_type'] == 'BUY'])
    shorts_lost = len([r for r in losses if r['signal_type'] == 'SELL'])

    # Build result object
    result_obj = {
        "config": {
            "timeframe": timeframe,
            "MIN_RISK_REWARD": min_risk_reward,
            "SWING_WINDOW": swing_window,
            "DATA_PERIOD": data_period,
            "MIN_ALLOWED_STOP_LOSS_PCT": min_stop_loss_pct,
            "MAX_ALLOWED_STOP_LOSS_PCT": max_stop_loss_pct
        },
        "results": {
            "total_trades": total_trades,
            "winning_trades": len(wins),
            "winning_longs": longs_won,
            "winning_shorts": shorts_won,
            "losing_trades": len(losses),
            "longs_lost": longs_lost,
            "shorts_lost": shorts_lost,
            "breakeven_trades": len(breakeven),
            "total_pnl_percentage": round(total_pnl_percentage, 2),
            "total_pnl_dollars": round(total_pnl, 2),
            "total_invested": total_invested
        },
        "metadata": {
            "report_file": report_file,
            "analyzed_at": datetime.now().isoformat()
        }
    }

    # Print summary
    print("\n" + "=" * 80)
    print("RESULTS SUMMARY")
    print("=" * 80)
    print(f"Total Trades: {total_trades}")
    print(f"Winning Trades: {len(wins)} (Longs: {longs_won}, Shorts: {shorts_won})")
    print(f"Losing Trades: {len(losses)} (Longs: {longs_lost}, Shorts: {shorts_lost})")
    print(f"Breakeven Trades: {len(breakeven)}")
    print(f"Total P&L: ${total_pnl:,.2f} ({total_pnl_percentage:.2f}%)")
    print("=" * 80)

    return result_obj


def add_result(
    report_file: str,
    timeframe: str,
    min_risk_reward: float,
    swing_window: int,
    data_period: str,
    min_stop_loss_pct: float,
    max_stop_loss_pct: float
):
    """Analyze a configuration and add it to the results file."""
    # Run analysis
    result = analyze_with_config(
        report_file=report_file,
        timeframe=timeframe,
        min_risk_reward=min_risk_reward,
        swing_window=swing_window,
        data_period=data_period,
        min_stop_loss_pct=min_stop_loss_pct,
        max_stop_loss_pct=max_stop_loss_pct
    )

    # Load existing results
    all_results = load_existing_results()

    # Add new result
    all_results.append(result)

    # Save (will auto-sort)
    save_results(all_results)

    return result


def print_all_results():
    """Print all saved results in a readable format."""
    results = load_existing_results()

    if not results:
        print("No results found.")
        return

    print("\n" + "=" * 100)
    print("ALL CONFIGURATION RESULTS (Sorted by P&L %)")
    print("=" * 100)

    for i, entry in enumerate(results, 1):
        config = entry['config']
        res = entry['results']

        print(f"\n#{i} - P&L: {res['total_pnl_percentage']:+.2f}%")
        print(f"  Config: {config['timeframe']} | RR≥{config['MIN_RISK_REWARD']} | SW={config['SWING_WINDOW']} | Period={config['DATA_PERIOD']} | SL={config['MIN_ALLOWED_STOP_LOSS_PCT']}-{config['MAX_ALLOWED_STOP_LOSS_PCT']}%")
        print(f"  Results: {res['total_trades']} trades | {res['winning_trades']} wins ({res['winning_longs']}L/{res['winning_shorts']}S) | {res['losing_trades']} losses ({res['longs_lost']}L/{res['shorts_lost']}S) | {res['breakeven_trades']} BE")

    print("\n" + "=" * 100)


def main():
    """Example usage - customize for your needs."""
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == 'show':
        # Show all results
        print_all_results()
        return

    # Example: Add a new configuration result
    # Customize these parameters for each run
    date = '2025-12-09'
    timeframe = '1wk'
    report_file = f'./reports/{date}/{timeframe}/harmonic_report_{date}_{timeframe}.txt'

    # Configuration parameters (from config_timeframes.py)
    from sys.path import insert
    from pathlib import Path
    insert(0, str(Path(__file__).parent.parent / 'src'))
    from config_timeframes import get_timeframe_config

    config = get_timeframe_config(timeframe)

    # Run with specific MIN_RISK_REWARD (can vary this)
    min_risk_reward = 3.0

    add_result(
        report_file=report_file,
        timeframe=timeframe,
        min_risk_reward=min_risk_reward,
        swing_window=config['SWING_WINDOW'],
        data_period=config['DATA_PERIOD'],
        min_stop_loss_pct=config['MIN_ALLOWED_STOP_LOSS_PCT'],
        max_stop_loss_pct=config['MAX_ALLOWED_STOP_LOSS_PCT']
    )

    # Show all results after adding
    print("\n")
    print_all_results()


if __name__ == '__main__':
    main()
