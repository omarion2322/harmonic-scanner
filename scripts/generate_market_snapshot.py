"""Create a durable market snapshot from harmonic scan reports."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SUMMARY_FIELDS = (
    "Total Stocks Scanned",
    "BUY Signals",
    "SELL Signals",
    "HOLD Signals",
    "Type 2 Confirmed",
    "Type 2 Candidates",
)


def parse_timeframes(value: str) -> list[str]:
    """Parse a comma-separated list of requested timeframes."""
    return [timeframe.strip() for timeframe in value.split(",") if timeframe.strip()]


def find_report(report_root: Path, report_date: str, timeframe: str) -> Path | None:
    """Find a report by its generated filename, regardless of report directory."""
    matches = sorted(
        report_root.rglob(f"harmonic_report_{report_date}_{timeframe}.txt")
    )
    return matches[-1] if matches else None


def extract_summary(report: str) -> dict[str, int]:
    """Extract scan counts from a harmonic report."""
    summary: dict[str, int] = {}
    for field in SUMMARY_FIELDS:
        match = re.search(rf"^{re.escape(field)}:\s*(\d+)\s*$", report, re.MULTILINE)
        if match:
            summary[field] = int(match.group(1))
    return summary


def extract_section(report: str, heading: str) -> str:
    """Return a signal section excluding the next all-caps report heading."""
    lines = report.splitlines()
    start = next((index for index, line in enumerate(lines) if line == heading), None)
    if start is None:
        return ""

    end = len(lines)
    for index in range(start + 1, len(lines)):
        if (
            lines[index]
            and set(lines[index]) == {"="}
            and index + 1 < len(lines)
            and lines[index + 1].isupper()
        ):
            end = index
            break
    return "\n".join(lines[start:end]).strip()


def current_commit() -> str | None:
    """Return the scanned repository commit when Git is available."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def snapshot_metadata(
    report_date: str,
    timeframes: Iterable[str],
    reports: dict[str, Path],
    workflow_run_id: str | None,
    workflow_run_url: str | None,
    tp_strategy: str | None,
) -> dict[str, Any]:
    """Build machine-readable provenance and scan status."""
    return {
        "snapshot_date": report_date,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": current_commit(),
        "workflow_run_id": workflow_run_id,
        "workflow_run_url": workflow_run_url,
        "tp_strategy": tp_strategy,
        "timeframes": [
            {
                "timeframe": timeframe,
                "status": "included" if timeframe in reports else "missing_report",
                "source_report": str(reports[timeframe]) if timeframe in reports else None,
            }
            for timeframe in timeframes
        ],
    }


def render_snapshot(
    report_date: str,
    reports: dict[str, Path],
    metadata: dict[str, Any],
) -> str:
    """Render all available BUY and SELL details as Markdown."""
    lines = [
        f"# Market Snapshot - {report_date}",
        "",
        f"Generated at (UTC): `{metadata['generated_at_utc']}`",
        f"Scanned commit: `{metadata['source_commit'] or 'unavailable'}`",
        f"Take-profit strategy: `{metadata['tp_strategy'] or 'unavailable'}`",
        "",
        "## Scan Summary",
        "",
        "| Timeframe | Total scanned | BUY | SELL | HOLD | Type 2 confirmed | Type 2 candidates |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]

    for timeframe in metadata["timeframes"]:
        report_path = reports.get(timeframe["timeframe"])
        if report_path is None:
            lines.append(
                f"| {timeframe['timeframe']} | Missing report | - | - | - | - | - |"
            )
            continue

        summary = extract_summary(report_path.read_text(encoding="utf-8"))
        lines.append(
            f"| {timeframe['timeframe']} | "
            f"{summary.get('Total Stocks Scanned', 'N/A')} | "
            f"{summary.get('BUY Signals', 'N/A')} | "
            f"{summary.get('SELL Signals', 'N/A')} | "
            f"{summary.get('HOLD Signals', 'N/A')} | "
            f"{summary.get('Type 2 Confirmed', 'N/A')} | "
            f"{summary.get('Type 2 Candidates', 'N/A')} |"
        )

    for timeframe, report_path in reports.items():
        report = report_path.read_text(encoding="utf-8")
        lines.extend(
            [
                "",
                f"## {timeframe} Signals",
                "",
                f"Source report: `{report_path}`",
            ]
        )
        for heading in ("BUY SIGNALS", "SELL SIGNALS"):
            section = extract_section(report, heading)
            lines.extend(
                [
                    "",
                    f"### {heading.title()}",
                    "",
                    "```text",
                    section or "No signals.",
                    "```",
                ]
            )

    return "\n".join(lines) + "\n"


def generate_snapshot(
    report_date: str,
    report_root: Path,
    output_root: Path,
    timeframes: Iterable[str],
    workflow_run_id: str | None = None,
    workflow_run_url: str | None = None,
    tp_strategy: str | None = None,
) -> Path | None:
    """Generate a dated snapshot when at least one requested report exists."""
    requested_timeframes = list(timeframes)
    reports = {
        timeframe: report
        for timeframe in requested_timeframes
        if (report := find_report(report_root, report_date, timeframe)) is not None
    }
    if not reports:
        return None

    output_dir = output_root / report_date
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata = snapshot_metadata(
        report_date,
        requested_timeframes,
        reports,
        workflow_run_id,
        workflow_run_url,
        tp_strategy,
    )
    (output_dir / "snapshot_metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "MARKET_SNAPSHOT.md").write_text(
        render_snapshot(report_date, reports, metadata), encoding="utf-8"
    )
    return output_dir


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a dated market snapshot from harmonic reports."
    )
    parser.add_argument("--report-date", required=True)
    parser.add_argument("--report-root", type=Path, default=Path("reports"))
    parser.add_argument("--output-root", type=Path, default=Path("market_snapshots"))
    parser.add_argument("--timeframes", required=True)
    parser.add_argument("--workflow-run-id", default=os.getenv("GITHUB_RUN_ID"))
    parser.add_argument("--workflow-run-url", default=os.getenv("GITHUB_SERVER_URL"))
    parser.add_argument("--tp-strategy", default=os.getenv("TP_STRATEGY"))
    args = parser.parse_args()

    output_dir = generate_snapshot(
        args.report_date,
        args.report_root,
        args.output_root,
        parse_timeframes(args.timeframes),
        args.workflow_run_id,
        args.workflow_run_url,
        args.tp_strategy,
    )
    if output_dir is None:
        print(f"No reports found for {args.report_date}; snapshot not generated.")
        return 0

    print(f"Generated market snapshot: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
