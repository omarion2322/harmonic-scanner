#!/usr/bin/env python3
"""Export scan signals as categorized TradingView watchlists."""

import argparse
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

BASE_PATH = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))

from extract_trades import PaperTrade, parse_report_file  # noqa: E402


@dataclass(frozen=True)
class ETFContext:
    theme: str
    ticker: str
    trend: str
    confirmed: bool


NO_ETF_CONTEXT = ETFContext(
    theme="No Meaningful ETF",
    ticker="NONE",
    trend="N/A",
    confirmed=False,
)


def parse_etf_contexts(report_path: Path) -> Dict[Tuple[str, str], ETFContext]:
    """Extract relevant ETF context keyed by signal and stock ticker."""
    content = report_path.read_text(encoding="utf-8")
    contexts: Dict[Tuple[str, str], ETFContext] = {}

    section_patterns = (
        ("BUY", r"BUY SIGNALS(.*?)(?:SELL SIGNALS|HOLD SIGNALS|MONITORING|END OF REPORT)"),
        ("SELL", r"SELL SIGNALS(.*?)(?:HOLD SIGNALS|MONITORING|END OF REPORT)"),
    )
    for signal, pattern in section_patterns:
        section_match = re.search(pattern, content, re.DOTALL)
        if not section_match:
            continue

        for block in re.split(r"-{80}", section_match.group(1)):
            ticker_match = re.search(r"Ticker:\s+(\S+)", block)
            if not ticker_match:
                continue

            ticker = ticker_match.group(1)
            etf_match = re.search(
                r"Relevant ETF:\s+(\S+)\s+\(([^)]+)\)",
                block,
            )
            trend_match = re.search(r"ETF Trend:\s+(\w+)", block)
            confluence_match = re.search(
                r"Signal Confluence:\s+(CONFIRMED|NOT CONFIRMED)",
                block,
            )

            if etf_match and trend_match:
                contexts[(signal, ticker)] = ETFContext(
                    theme=etf_match.group(2).strip(),
                    ticker=etf_match.group(1).strip(),
                    trend=trend_match.group(1).strip(),
                    confirmed=(
                        confluence_match is not None
                        and confluence_match.group(1) == "CONFIRMED"
                    ),
                )
            else:
                contexts[(signal, ticker)] = NO_ETF_CONTEXT

    return contexts


def _header(signal: str, context: ETFContext) -> str:
    direction = "LONG" if signal == "BUY" else "SHORT"
    header = (
        f"###{direction} — {context.theme} | "
        f"ETF: {context.ticker} | Trend: {context.trend}"
    )
    if not context.confirmed:
        header += " | NOT CONFIRMED"
    return header


def _group_trades(
    trades: List[PaperTrade],
    contexts: Dict[Tuple[str, str], ETFContext],
) -> Dict[Tuple[str, ETFContext], List[PaperTrade]]:
    grouped: Dict[Tuple[str, ETFContext], List[PaperTrade]] = defaultdict(list)
    for trade in trades:
        context = contexts.get(
            (trade.signal_type, trade.ticker),
            NO_ETF_CONTEXT,
        )
        grouped[(trade.signal_type, context)].append(trade)

    for grouped_trades in grouped.values():
        grouped_trades.sort(key=lambda trade: trade.risk_reward, reverse=True)
    return grouped


def build_watchlist(
    trades: List[PaperTrade],
    contexts: Dict[Tuple[str, str], ETFContext],
) -> str:
    """Build a TradingView import file containing only sections and symbols."""
    grouped = _group_trades(trades, contexts)
    lines: List[str] = []

    for signal in ("BUY", "SELL"):
        signal_groups = [
            (context, grouped_trades)
            for (group_signal, context), grouped_trades in grouped.items()
            if group_signal == signal
        ]
        signal_groups.sort(
            key=lambda item: (
                item[0].theme.lower(),
                item[0].ticker,
                item[0].trend,
            )
        )
        for context, grouped_trades in signal_groups:
            lines.append(_header(signal, context))
            lines.append(",".join(trade.ticker for trade in grouped_trades))
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def build_notes(
    trades: List[PaperTrade],
    contexts: Dict[Tuple[str, str], ETFContext],
    report_date: str,
    timeframe: str,
) -> str:
    """Build a companion file containing trade levels and pattern details."""
    grouped = _group_trades(trades, contexts)
    lines = [
        f"TradingView Signal Notes | {report_date} | {timeframe}",
        "=" * 72,
        "",
    ]

    for signal in ("BUY", "SELL"):
        signal_groups = [
            (context, grouped_trades)
            for (group_signal, context), grouped_trades in grouped.items()
            if group_signal == signal
        ]
        signal_groups.sort(
            key=lambda item: (
                item[0].theme.lower(),
                item[0].ticker,
                item[0].trend,
            )
        )
        for context, grouped_trades in signal_groups:
            lines.append(_header(signal, context))
            for trade in grouped_trades:
                lines.extend([
                    f"{trade.ticker} [{trade.pattern} | Grade {trade.grade}]",
                    (
                        f"  Entry: ${trade.entry_price:g} | "
                        f"Stop: ${trade.stop_loss:g} | "
                        f"R/R: {trade.risk_reward:g}:1"
                    ),
                    (
                        f"  Targets: ${trade.target1:g} / "
                        f"${trade.target2:g} / ${trade.target3:g}"
                    ),
                ])
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def export(
    report_date: str = None,
    timeframe: str = "1wk",
    min_grade: str = "C-",
    min_long_rr: float = 0.0,
    min_short_rr: float = 0.0,
    output_file: str = None,
    notes_output_file: str = None,
) -> Tuple[Path, Path]:
    if report_date is None:
        report_date = datetime.now().strftime("%Y-%m-%d")

    report_path = (
        BASE_PATH
        / "reports"
        / report_date
        / timeframe
        / f"harmonic_report_{report_date}_{timeframe}.txt"
    )
    if not report_path.exists():
        raise FileNotFoundError(f"Report file not found at {report_path}")

    trades = parse_report_file(
        report_path,
        timeframe,
        min_grade,
        min_long_rr,
        min_short_rr,
    )
    contexts = parse_etf_contexts(report_path)

    output_path = (
        Path(output_file)
        if output_file
        else report_path.parent
        / f"tradingview_watchlist_{report_date}_{timeframe}.txt"
    )
    notes_path = (
        Path(notes_output_file)
        if notes_output_file
        else report_path.parent
        / f"tradingview_notes_{report_date}_{timeframe}.txt"
    )

    output_path.write_text(
        build_watchlist(trades, contexts),
        encoding="utf-8",
    )
    notes_path.write_text(
        build_notes(trades, contexts, report_date, timeframe),
        encoding="utf-8",
    )
    return output_path, notes_path


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export categorized TradingView watchlist artifacts.",
    )
    parser.add_argument("--date", help="Report date (YYYY-MM-DD)")
    parser.add_argument(
        "--timeframe",
        default="1wk",
        choices=["1d", "1wk", "1mo"],
    )
    parser.add_argument("--min-grade", default="C-")
    parser.add_argument("--min-long-rr", type=float, default=0.0)
    parser.add_argument("--min-short-rr", type=float, default=0.0)
    parser.add_argument("--output")
    parser.add_argument("--notes-output")
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    try:
        watchlist_path, notes_path = export(
            report_date=args.date,
            timeframe=args.timeframe,
            min_grade=args.min_grade,
            min_long_rr=args.min_long_rr,
            min_short_rr=args.min_short_rr,
            output_file=args.output,
            notes_output_file=args.notes_output,
        )
    except FileNotFoundError as exc:
        print(f"Error: {exc}")
        sys.exit(1)

    print(f"Saved TradingView watchlist to {watchlist_path}")
    print(f"Saved TradingView notes to {notes_path}")


if __name__ == "__main__":
    main()
