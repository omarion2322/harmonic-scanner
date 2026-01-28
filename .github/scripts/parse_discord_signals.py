#!/usr/bin/env python3
import re
import json
import os

def parse_signals(filename, signal_type, max_signals=3):
    """Parse detailed signal information from report"""
    signals = []
    with open(filename, 'r') as f:
        content = f.read()

    section_marker = f"{signal_type} SIGNALS"
    if section_marker not in content:
        return signals

    parts = content.split('=' * 80)
    in_section = False

    for part in parts:
        if section_marker in part:
            in_section = True
            continue

        if in_section:
            if 'SIGNALS' in part and signal_type not in part:
                break

            ticker_match = re.search(r'Ticker:\s+(\S+)', part)
            if not ticker_match:
                continue

            ticker = ticker_match.group(1)
            price_match = re.search(r'Current Price:\s+\$([0-9.]+)', part)
            analysis_match = re.search(r'Analysis:\s+(\w+)\s+([\w-]+)\s+-\s+Grade\s+([A-F][+-]?)\s+-\s+Detected\s+([\d-]+)', part)
            entry_match = re.search(r'Entry:\s+\$([0-9.]+)', part)
            stop_match = re.search(r'Stop(?:\sLoss)?:\s+\$([0-9.]+)', part)
            t1_match = re.search(r'T(?:arget\s)?1:\s+\$([0-9.]+)', part)
            t2_match = re.search(r'T(?:arget\s)?2:\s+\$([0-9.]+)', part)
            t3_match = re.search(r'T(?:arget\s)?3:\s+\$([0-9.]+)', part)
            rr_match = re.search(r'Risk/Reward:\s+([0-9.]+):1', part)
            prz_match = re.search(r'Entry Zone \(PRZ\):\s+\$([0-9.]+)\s+-\s+\$([0-9.]+)', part)
            tp_strategy_match = re.search(r'TP Targets:\s+(\w+)', part)

            if analysis_match and entry_match:
                signal = {
                    'ticker': ticker,
                    'price': price_match.group(1) if price_match else 'N/A',
                    'direction': analysis_match.group(1),
                    'pattern': analysis_match.group(2),
                    'grade': analysis_match.group(3),
                    'entry': entry_match.group(1),
                    'stop': stop_match.group(1) if stop_match else 'N/A',
                    't1': t1_match.group(1) if t1_match else 'N/A',
                    't2': t2_match.group(1) if t2_match else 'N/A',
                    't3': t3_match.group(1) if t3_match else 'N/A',
                    'rr': rr_match.group(1) if rr_match else 'N/A',
                    'prz_low': prz_match.group(1) if prz_match else None,
                    'prz_high': prz_match.group(2) if prz_match else None,
                    'tp_strategy': tp_strategy_match.group(1) if tp_strategy_match else 'N/A'
                }
                signals.append(signal)
                if len(signals) >= max_signals:
                    break

    return signals

# Parse BUY and SELL signals
buy_signals = parse_signals(os.environ['REPORT_FILE'], "BUY", 3)
sell_signals = parse_signals(os.environ['REPORT_FILE'], "SELL", 3)

fields = []
for sig in buy_signals:
    # Build entry zone text
    entry_zone = f"${sig['prz_low']} - ${sig['prz_high']}" if sig['prz_low'] and sig['prz_high'] else f"${sig['entry']}"

    value = (
        f"**Current Price:** ${sig['price']}\n"
        f"**Pattern:** {sig['pattern']} ({sig['direction']}) - Grade {sig['grade']}\n"
        f"**Entry Zone:** {entry_zone}\n"
        f"**Entry:** ${sig['entry']} | **Stop:** ${sig['stop']}\n"
        f"**T1:** ${sig['t1']} | **T2:** ${sig['t2']} | **T3:** ${sig['t3']}\n"
        f"**Risk/Reward:** {sig['rr']}:1 | **TP Strategy:** {sig['tp_strategy']}"
    )
    fields.append({
        "name": f"🟢 {sig['ticker']}",
        "value": value,
        "inline": False
    })

for sig in sell_signals:
    # Build entry zone text
    entry_zone = f"${sig['prz_low']} - ${sig['prz_high']}" if sig['prz_low'] and sig['prz_high'] else f"${sig['entry']}"

    value = (
        f"**Current Price:** ${sig['price']}\n"
        f"**Pattern:** {sig['pattern']} ({sig['direction']}) - Grade {sig['grade']}\n"
        f"**Entry Zone:** {entry_zone}\n"
        f"**Entry:** ${sig['entry']} | **Stop:** ${sig['stop']}\n"
        f"**T1:** ${sig['t1']} | **T2:** ${sig['t2']} | **T3:** ${sig['t3']}\n"
        f"**Risk/Reward:** {sig['rr']}:1 | **TP Strategy:** {sig['tp_strategy']}"
    )
    fields.append({
        "name": f"🔴 {sig['ticker']}",
        "value": value,
        "inline": False
    })

payload = {
    "embeds": [{
        "title": os.environ['TITLE'],
        "description": os.environ['DESCRIPTION'].replace('\\n', '\n'),
        "color": int(os.environ['COLOR']),
        "fields": fields,
        "footer": {"text": "Harmonic Pattern Scanner"},
        "timestamp": os.environ['TIMESTAMP']
    }]
}

print(json.dumps(payload))
