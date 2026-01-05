#!/usr/bin/env python3
"""
Paper Trading Monitor for Harmonic Pattern Trades
Tracks trades in real-time and evaluates P&L using live market data.
"""

import json
import sys
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple
import yfinance as yf
from dataclasses import dataclass

# Add src directory to path to import config
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
from config import POSITION_SIZE_T1, POSITION_SIZE_T2, POSITION_SIZE_T3


@dataclass
class TradeStatus:
    """Current status of a paper trade"""
    ticker: str
    signal_type: str
    pattern: str
    detected_date: str
    entry_price: float
    current_price: float
    stop_loss: float
    target1: float
    target2: float
    target3: float
    risk_reward: float
    grade: str
    timeframe: str

    # Status flags
    t1_hit: bool = False
    t2_hit: bool = False
    t3_hit: bool = False
    stop_hit: bool = False

    # Dates when targets hit
    t1_date: str = None
    t2_date: str = None
    t3_date: str = None
    stop_date: str = None

    # Actual prices when hit (can differ from planned due to gaps)
    stop_hit_price: float = None

    # P&L calculation
    total_pnl: float = 0.0
    total_pnl_percent: float = 0.0
    remaining_position: float = 1.0
    status: str = "OPEN"


def load_paper_trades(filepath: Path) -> List[Dict]:
    """Load paper trades from JSON file"""
    if not filepath.exists():
        print(f"Error: Paper trades file not found at {filepath}")
        return []

    with open(filepath, 'r') as f:
        return json.load(f)


def save_paper_trades(trades: List[Dict], filepath: Path):
    """Save updated paper trades to JSON file"""
    with open(filepath, 'w') as f:
        json.dump(trades, f, indent=2)


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


def check_trade_status(trade: Dict, investment_per_trade: float = 10000.0) -> TradeStatus:
    """
    Check current status of a trade and calculate P&L.

    Args:
        trade: Trade dictionary from JSON
        investment_per_trade: Dollar amount invested per trade

    Returns:
        TradeStatus object with current status and P&L
    """
    try:
        # Get historical data from detected date to now
        ticker_obj = yf.Ticker(trade['ticker'])
        hist = ticker_obj.history(start=trade['detected_date'], end=datetime.now())

        if hist.empty:
            # Return default status if no data
            return TradeStatus(
                ticker=trade['ticker'],
                signal_type=trade['signal_type'],
                pattern=trade['pattern'],
                detected_date=trade['detected_date'],
                entry_price=trade['entry_price'],
                current_price=trade['entry_price'],
                stop_loss=trade['stop_loss'],
                target1=trade['target1'],
                target2=trade['target2'],
                target3=trade['target3'],
                risk_reward=trade['risk_reward'],
                grade=trade['grade'],
                timeframe=trade['timeframe'],
                status='NO_DATA'
            )

        # Get current price
        current_price = hist['Close'].iloc[-1]

        # Track target and stop hits
        t1_hit, t2_hit, t3_hit, stop_hit = False, False, False, False
        t1_date, t2_date, t3_date, stop_date = None, None, None, None
        stop_hit_price = None

        # Check each day's price action
        for date, row in hist.iterrows():
            high, low, open_price = row['High'], row['Low'], row['Open']

            if trade['signal_type'] == 'BUY':
                # Long trades
                if not stop_hit and low <= trade['stop_loss']:
                    stop_hit, stop_date = True, date
                    # If gap down, use open price; otherwise use stop loss price
                    stop_hit_price = open_price if open_price < trade['stop_loss'] else trade['stop_loss']
                if not t1_hit and high >= trade['target1']:
                    t1_hit, t1_date = True, date
                if t1_hit and not t2_hit and high >= trade['target2']:
                    t2_hit, t2_date = True, date
                if t2_hit and not t3_hit and high >= trade['target3']:
                    t3_hit, t3_date = True, date
            else:
                # Short trades
                if not stop_hit and high >= trade['stop_loss']:
                    stop_hit, stop_date = True, date
                    # If gap up, use open price; otherwise use stop loss price
                    stop_hit_price = open_price if open_price > trade['stop_loss'] else trade['stop_loss']
                if not t1_hit and low <= trade['target1']:
                    t1_hit, t1_date = True, date
                if t1_hit and not t2_hit and low <= trade['target2']:
                    t2_hit, t2_date = True, date
                if t2_hit and not t3_hit and low <= trade['target3']:
                    t3_hit, t3_date = True, date

        # Calculate P&L with partial profit-taking
        shares = investment_per_trade / trade['entry_price']
        shares_t1 = shares * POSITION_SIZE_T1
        shares_t2 = shares * POSITION_SIZE_T2
        shares_t3 = shares * POSITION_SIZE_T3

        total_pnl = 0
        remaining_position = 1.0

        # Check which targets hit before stop
        t1_before_stop = target_hit_before_stop(t1_hit, t1_date, stop_hit, stop_date)
        t2_before_stop = target_hit_before_stop(t2_hit, t2_date, stop_hit, stop_date)
        t3_before_stop = target_hit_before_stop(t3_hit, t3_date, stop_hit, stop_date)

        # T1
        if t1_before_stop:
            total_pnl += calculate_position_pnl(shares_t1, trade['entry_price'], trade['target1'], trade['signal_type'])
            remaining_position -= POSITION_SIZE_T1

        # T2
        if t2_before_stop:
            total_pnl += calculate_position_pnl(shares_t2, trade['entry_price'], trade['target2'], trade['signal_type'])
            remaining_position -= POSITION_SIZE_T2

        # T3
        if t3_before_stop:
            total_pnl += calculate_position_pnl(shares_t3, trade['entry_price'], trade['target3'], trade['signal_type'])
            remaining_position -= POSITION_SIZE_T3

        # Remaining position
        if stop_hit and remaining_position > 0:
            remaining_shares = shares * remaining_position
            # Use actual stop hit price (which accounts for gaps) instead of planned stop loss
            total_pnl += calculate_position_pnl(remaining_shares, trade['entry_price'], stop_hit_price, trade['signal_type'])
        elif remaining_position > 0:
            # Use current price for open position
            remaining_shares = shares * remaining_position
            total_pnl += calculate_position_pnl(remaining_shares, trade['entry_price'], current_price, trade['signal_type'])

        # Determine status
        if stop_hit and remaining_position > 0:
            # Stop was hit and we still have remaining position = stopped out
            status = 'STOPPED_OUT'
        elif remaining_position == 0:
            status = 'FULL_WIN'
        elif t1_before_stop or t2_before_stop or t3_before_stop:
            status = 'PARTIAL_WIN'
        else:
            status = 'OPEN'

        pnl_percent = (total_pnl / investment_per_trade) * 100

        return TradeStatus(
            ticker=trade['ticker'],
            signal_type=trade['signal_type'],
            pattern=trade['pattern'],
            detected_date=trade['detected_date'],
            entry_price=trade['entry_price'],
            current_price=current_price,
            stop_loss=trade['stop_loss'],
            target1=trade['target1'],
            target2=trade['target2'],
            target3=trade['target3'],
            risk_reward=trade['risk_reward'],
            grade=trade['grade'],
            timeframe=trade['timeframe'],
            t1_hit=t1_before_stop,
            t2_hit=t2_before_stop,
            t3_hit=t3_before_stop,
            stop_hit=stop_hit,
            t1_date=t1_date.strftime('%Y-%m-%d') if t1_date is not None else None,
            t2_date=t2_date.strftime('%Y-%m-%d') if t2_date is not None else None,
            t3_date=t3_date.strftime('%Y-%m-%d') if t3_date is not None else None,
            stop_date=stop_date.strftime('%Y-%m-%d') if stop_date is not None else None,
            stop_hit_price=stop_hit_price,
            total_pnl=total_pnl,
            total_pnl_percent=pnl_percent,
            remaining_position=remaining_position,
            status=status
        )

    except Exception as e:
        print(f"Error checking {trade['ticker']}: {e}")
        return TradeStatus(
            ticker=trade['ticker'],
            signal_type=trade['signal_type'],
            pattern=trade['pattern'],
            detected_date=trade['detected_date'],
            entry_price=trade['entry_price'],
            current_price=trade['entry_price'],
            stop_loss=trade['stop_loss'],
            target1=trade['target1'],
            target2=trade['target2'],
            target3=trade['target3'],
            risk_reward=trade['risk_reward'],
            grade=trade['grade'],
            timeframe=trade['timeframe'],
            status='ERROR'
        )


def format_pnl(pnl: float, pnl_percent: float) -> str:
    """Format P&L with color and sign"""
    sign = '+' if pnl >= 0 else ''
    return f"{sign}${pnl:,.2f} ({sign}{pnl_percent:.2f}%)"


def print_section_header(title: str, width: int = 80, char: str = "="):
    """Print a section header"""
    print("\n" + char * width)
    print(title)
    print(char * width)


def print_trade_status(status: TradeStatus):
    """Print detailed status for a single trade"""
    # Direction emoji
    direction = "📈" if status.signal_type == "BUY" else "📉"

    # Price change emoji
    price_change = status.current_price - status.entry_price
    if status.signal_type == "BUY":
        change_emoji = "🟢" if price_change > 0 else "🔴" if price_change < 0 else "⚪"
    else:
        change_emoji = "🟢" if price_change < 0 else "🔴" if price_change > 0 else "⚪"

    # Targets compact
    t1 = "✅" if status.t1_hit else "❌"
    t2 = "✅" if status.t2_hit else "❌"
    t3 = "✅" if status.t3_hit else "❌"

    # Stop loss status
    stop_status = "🛑" if status.stop_hit else f"${status.stop_loss:.2f}"

    # P&L emoji
    pnl_emoji = "💰" if status.total_pnl > 0 else "📉" if status.total_pnl < 0 else "➖"

    # Line 1: Ticker and pattern
    print(f"\n{direction} {status.ticker} ({status.signal_type}) - {status.pattern}")

    # Line 2: Price action and status
    print(f"  {change_emoji} ${status.entry_price:.2f} → ${status.current_price:.2f} | "
          f"T1 {t1} T2 {t2} T3 {t3} | Stop: {stop_status} | "
          f"{pnl_emoji} {format_pnl(status.total_pnl, status.total_pnl_percent)}")

    # Line 3: Target prices
    print(f"  Targets: T1: ${status.target1:.2f} | T2: ${status.target2:.2f} | T3: ${status.target3:.2f}")


def run_paper_trader(trades_file: str = None, investment_per_trade: float = 10000.0,
                     update_file: bool = False, filter_status: str = None):
    """
    Run paper trader to check all trades and display results.

    Args:
        trades_file: Path to paper trades JSON file
        investment_per_trade: Dollar amount invested per trade
        update_file: Whether to update the JSON file with current status
        filter_status: Only show trades with this status (OPEN, PARTIAL_WIN, etc.)
    """
    # Determine file path
    if trades_file is None:
        trades_file = Path(__file__).parent.parent / 'paper_trades.json'
    else:
        trades_file = Path(trades_file)

    # Load trades
    trades = load_paper_trades(trades_file)
    if not trades:
        print("No trades to monitor.")
        return

    print_section_header(f"PAPER TRADING MONITOR - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Check each trade
    trade_statuses = []

    for i, trade in enumerate(trades, 1):
        status = check_trade_status(trade, investment_per_trade)
        trade_statuses.append(status)

        # Update trade in JSON if requested
        if update_file:
            trade['status'] = status.status
            trade['current_price'] = float(status.current_price)
            trade['total_pnl'] = float(status.total_pnl)
            trade['total_pnl_percent'] = float(status.total_pnl_percent)
            trade['remaining_position'] = float(status.remaining_position)

            # Target hits
            trade['t1_hit'] = status.t1_hit
            trade['t2_hit'] = status.t2_hit
            trade['t3_hit'] = status.t3_hit
            trade['stop_hit'] = status.stop_hit

            # Dates when targets/stop hit
            trade['t1_hit_date'] = status.t1_date
            trade['t2_hit_date'] = status.t2_date
            trade['t3_hit_date'] = status.t3_date
            trade['stop_hit_date'] = status.stop_date

            # Actual stop hit price (can differ from planned due to gaps)
            trade['stop_hit_price'] = float(status.stop_hit_price) if status.stop_hit_price is not None else None

    # Calculate overall statistics
    total_trades = len(trade_statuses)
    total_invested = total_trades * investment_per_trade
    total_pnl = sum(s.total_pnl for s in trade_statuses)
    total_pnl_percent = (total_pnl / total_invested * 100) if total_invested > 0 else 0

    # Group by status
    status_groups = {}
    for status in trade_statuses:
        if status.status not in status_groups:
            status_groups[status.status] = []
        status_groups[status.status].append(status)

    # Print summary
    print(f"\nTotal P&L: {format_pnl(total_pnl, total_pnl_percent)} ({total_trades} trades)")

    # Print detailed trade statuses
    if filter_status:
        filtered_trades = [s for s in trade_statuses if s.status == filter_status]
        print_section_header(f"TRADES WITH STATUS: {filter_status}")
        for status in sorted(filtered_trades, key=lambda x: x.total_pnl, reverse=True):
            print_trade_status(status)
    else:
        # Show all trades sorted by P&L
        print_section_header("Bot Paper Trades - Start Date 15/12/2025")
        for status in sorted(trade_statuses, key=lambda x: x.total_pnl, reverse=True):
            print_trade_status(status)

    # Save updated trades if requested
    if update_file:
        save_paper_trades(trades, trades_file)
        print(f"\nUpdated trade statuses in {trades_file}")


def parse_arguments():
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(
        description='Monitor paper trades and evaluate P&L in real-time',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Monitor all trades
  python paper_trader.py

  # Monitor with custom investment amount
  python paper_trader.py --investment 5000

  # Update JSON file with current status
  python paper_trader.py --update

  # Show only open trades
  python paper_trader.py --filter OPEN

  # Show only winning trades
  python paper_trader.py --filter PARTIAL_WIN
        """
    )

    parser.add_argument('--trades-file', help='Path to paper trades JSON file (default: paper_trades.json)')
    parser.add_argument('--investment', type=float, default=10000.0,
                       help='Investment per trade in dollars (default: 10000.0)')
    parser.add_argument('--update', action='store_true',
                       help='Update JSON file with current trade statuses')
    parser.add_argument('--filter', choices=['OPEN', 'PARTIAL_WIN', 'FULL_WIN', 'STOPPED_OUT', 'ERROR', 'NO_DATA'],
                       help='Only show trades with this status')

    return parser.parse_args()


def main():
    """Entry point"""
    args = parse_arguments()

    run_paper_trader(
        trades_file=args.trades_file,
        investment_per_trade=args.investment,
        update_file=args.update,
        filter_status=args.filter
    )


if __name__ == '__main__':
    main()
