"""Tests for categorized TradingView watchlist exports."""

import sys
from pathlib import Path

scripts_path = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(scripts_path))

from export_tradingview import (  # noqa: E402
    ETFContext,
    NO_ETF_CONTEXT,
    build_watchlist,
    parse_etf_contexts,
)
from extract_trades import PaperTrade  # noqa: E402


def _trade(ticker: str, signal: str, risk_reward: float) -> PaperTrade:
    return PaperTrade(
        ticker=ticker,
        signal_type=signal,
        pattern="GARTLEY (BULLISH)",
        detected_date="2026-07-22",
        entry_price=10.0,
        stop_loss=9.0,
        target1=12.0,
        target2=14.0,
        target3=16.0,
        risk_reward=risk_reward,
        grade="B",
        timeframe="1d",
        extracted_date="2026-07-22",
    )


def test_build_watchlist_uses_approved_header_format():
    trades = [
        _trade("CDZI", "BUY", 5.0),
        _trade("INOD", "BUY", 4.0),
        _trade("INV", "BUY", 3.0),
    ]
    contexts = {
        ("BUY", "CDZI"): ETFContext(
            "Water Infrastructure",
            "CGW",
            "UP",
            True,
        ),
        ("BUY", "INOD"): ETFContext(
            "Artificial Intelligence",
            "IVES",
            "DOWN",
            False,
        ),
        ("BUY", "INV"): NO_ETF_CONTEXT,
    }

    output = build_watchlist(trades, contexts)

    assert "###LONG — Water Infrastructure | ETF: CGW | Trend: UP\nCDZI" in output
    assert (
        "###LONG — Artificial Intelligence | ETF: IVES | "
        "Trend: DOWN | NOT CONFIRMED\nINOD"
    ) in output
    assert (
        "###LONG — No Meaningful ETF | ETF: NONE | "
        "Trend: N/A | NOT CONFIRMED\nINV"
    ) in output
    assert "CONFIRMED\nCDZI" not in output


def test_build_watchlist_sorts_tickers_by_risk_reward():
    context = ETFContext("Biotechnology", "IBB", "UP", True)
    trades = [
        _trade("LOW", "BUY", 2.0),
        _trade("HIGH", "BUY", 8.0),
    ]

    output = build_watchlist(
        trades,
        {
            ("BUY", "LOW"): context,
            ("BUY", "HIGH"): context,
        },
    )

    assert "HIGH,LOW" in output


def test_parse_etf_contexts_reads_report_and_defaults_missing_match(tmp_path):
    report = tmp_path / "report.txt"
    report.write_text(
        """
BUY SIGNALS
================================================================================
Ticker: CDZI
  Relevant ETF: CGW (Water Infrastructure)
  ETF Trend: UP | 20-Period Return: +2.6%
  Signal Confluence: CONFIRMED
--------------------------------------------------------------------------------
Ticker: INV
--------------------------------------------------------------------------------
SELL SIGNALS
================================================================================
Ticker: TEST
  Relevant ETF: IBB (Biotechnology)
  ETF Trend: UP | 20-Period Return: +3.0%
  Signal Confluence: NOT CONFIRMED
--------------------------------------------------------------------------------
END OF REPORT
""",
        encoding="utf-8",
    )

    contexts = parse_etf_contexts(report)

    assert contexts[("BUY", "CDZI")] == ETFContext(
        "Water Infrastructure",
        "CGW",
        "UP",
        True,
    )
    assert contexts[("BUY", "INV")] == NO_ETF_CONTEXT
    assert contexts[("SELL", "TEST")].confirmed is False
