from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from generate_market_snapshot import generate_snapshot


def _report(total: int, buys: int, sells: int) -> str:
    return f"""================================================================================
SUMMARY
--------------------------------------------------------------------------------
Total Stocks Scanned: {total}
BUY Signals: {buys}
SELL Signals: {sells}
HOLD Signals: 7
Type 2 Confirmed: 2
Type 2 Candidates: 1
================================================================================
BUY SIGNALS
================================================================================

Ticker: BUY
Target 1: N/A
--------------------------------------------------------------------------------

================================================================================
SELL SIGNALS
================================================================================

Ticker: SELL
Target 1: $90.00
--------------------------------------------------------------------------------

================================================================================
HOLD SIGNALS
================================================================================
"""


def test_generate_snapshot_includes_signals_and_missing_timeframes(tmp_path):
    report = tmp_path / "reports" / "2026-10-24" / "1d"
    report.mkdir(parents=True)
    (report / "harmonic_report_2026-10-24_1d.txt").write_text(
        _report(10, 1, 1), encoding="utf-8"
    )

    output = generate_snapshot(
        "2026-10-24",
        tmp_path / "reports",
        tmp_path / "market_snapshots",
        ["1d", "1wk"],
        workflow_run_id="123",
        workflow_run_url="https://github.com/example/run/123",
        tp_strategy="MITCH",
    )

    assert output == tmp_path / "market_snapshots" / "2026-10-24"
    snapshot = (output / "MARKET_SNAPSHOT.md").read_text(encoding="utf-8")
    metadata = (output / "snapshot_metadata.json").read_text(encoding="utf-8")
    assert "| 1d | 10 | 1 | 1 | 7 | 2 | 1 |" in snapshot
    assert "| 1wk | Missing report | - | - | - | - | - |" in snapshot
    assert "Ticker: BUY" in snapshot
    assert "Ticker: SELL" in snapshot
    assert '"status": "included"' in metadata
    assert '"status": "missing_report"' in metadata


def test_generate_snapshot_skips_output_when_no_report_exists(tmp_path):
    assert generate_snapshot(
        "2026-10-24",
        tmp_path / "reports",
        tmp_path / "market_snapshots",
        ["1d"],
    ) is None
