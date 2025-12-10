#!/usr/bin/env python3
"""
View Configuration Results
Display saved configuration test results in a readable format
"""

import json
from pathlib import Path


def view_results():
    """Load and display all configuration results."""
    results_file = Path(__file__).parent.parent / 'config_results.json'

    if not results_file.exists():
        print(f"No results file found at: {results_file}")
        print("Run analyze_trades.py first to generate results.")
        return

    with open(results_file, 'r') as f:
        results = json.load(f)

    if not results:
        print("No results found in file.")
        return

    print("\n" + "=" * 148)
    print("CONFIGURATION TEST RESULTS (Sorted by Total P&L %)")
    print("=" * 148)
    print(f"\nTotal Configurations Tested: {len(results)}\n")

    # Print header
    print(f"{'#':<4} {'P&L %':<10} {'Trades':<8} {'Win %':<8} {'Wins':<8} {'W-Long':<8} {'W-Short':<9} "
          f"{'Losses':<9} {'L-Long':<8} {'L-Short':<9} {'BE':<6} {'TF':<6} "
          f"{'R/R':<6} {'SW':<5} {'Period':<8} {'SL Range':<12} {'TP Algo':<10} {'Min Grade':<10}")
    print("-" * 148)

    for i, entry in enumerate(results, 1):
        cfg = entry['config']
        res = entry['results']

        # Format P&L with color indicators
        pnl_str = f"{res['total_pnl_percentage']:+.2f}%"

        # Calculate win percentage
        win_pct = (res['winning_trades'] / res['total_trades'] * 100) if res['total_trades'] > 0 else 0
        win_pct_str = f"{win_pct:.1f}%"

        # Build the row
        tp_algo = cfg.get('Trading Algorithm', 'N/A')
        min_grade = cfg.get('Min Pattern Grade', 'N/A')
        print(f"{i:<4} {pnl_str:<10} {res['total_trades']:<8} {win_pct_str:<8} {res['winning_trades']:<8} "
              f"{res['winning_longs']:<8} {res['winning_shorts']:<9} "
              f"{res['losing_trades']:<9} {res['longs_lost']:<8} {res['shorts_lost']:<9} "
              f"{res['breakeven_trades']:<6} {cfg['timeframe']:<6} "
              f"{cfg['MIN_RISK_REWARD']:<6} {cfg['SWING_WINDOW']:<5} "
              f"{cfg['DATA_PERIOD']:<8} "
              f"{cfg['MIN_ALLOWED_STOP_LOSS_PCT']:.1f}-{cfg['MAX_ALLOWED_STOP_LOSS_PCT']:.1f}%  {tp_algo:<10} {min_grade:<10}")

    print("=" * 148)

    # Show top 3 configurations
    print("\nTOP 3 CONFIGURATIONS:")
    print("-" * 148)
    for i, entry in enumerate(results[:3], 1):
        cfg = entry['config']
        res = entry['results']

        print(f"\n#{i} - Total P&L: {res['total_pnl_percentage']:+.2f}% (${res['total_pnl_dollars']:+,.2f})")
        print(f"  Configuration:")
        print(f"    Timeframe: {cfg['timeframe']}")
        print(f"    MIN_RISK_REWARD: {cfg['MIN_RISK_REWARD']}")
        print(f"    SWING_WINDOW: {cfg['SWING_WINDOW']}")
        print(f"    DATA_PERIOD: {cfg['DATA_PERIOD']}")
        print(f"    Stop Loss Range: {cfg['MIN_ALLOWED_STOP_LOSS_PCT']}% - {cfg['MAX_ALLOWED_STOP_LOSS_PCT']}%")
        print(f"    Trading Algorithm: {cfg.get('Trading Algorithm', 'N/A')}")
        print(f"    Min Pattern Grade: {cfg.get('Min Pattern Grade', 'N/A')}")
        print(f"  Results:")
        print(f"    Total Trades: {res['total_trades']}")
        print(f"    Winning: {res['winning_trades']} ({res['winning_longs']} longs, {res['winning_shorts']} shorts)")
        print(f"    Losing: {res['losing_trades']} ({res['longs_lost']} longs, {res['shorts_lost']} shorts)")
        print(f"    Breakeven: {res['breakeven_trades']}")
        print(f"    Win Rate: {(res['winning_trades'] / res['total_trades'] * 100) if res['total_trades'] > 0 else 0:.1f}%")

    print("\n" + "=" * 130)


if __name__ == '__main__':
    view_results()
