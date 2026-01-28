#!/usr/bin/env python3
import re
import json
import os

def parse_signals(filename, signal_type, max_signals=3):
    """Parse detailed signal information from report"""
    signals = []
    with open(filename, 'r') as f:
        content = f.read()

    # Find the section for this signal type
    section_marker = f"{signal_type} SIGNALS"
    if section_marker not in content:
        return signals

    # Extract the section from header to next major section (MONITORING or other SIGNALS)
    start_idx = content.find(section_marker)
    if start_idx == -1:
        return signals

    # Find end of section (next SIGNALS or MONITORING section)
    end_markers = ['MONITORING', 'SELL SIGNALS', 'BUY SIGNALS', 'HOLD SIGNALS']
    end_idx = len(content)
    for marker in end_markers:
        marker_idx = content.find(marker, start_idx + len(section_marker))
        if marker_idx != -1 and marker_idx < end_idx:
            # Make sure we didn't find our own section header again
            if marker != section_marker or marker_idx > start_idx + len(section_marker):
                end_idx = marker_idx

    section_content = content[start_idx:end_idx]

    # Split by signal separators (dashes)
    signal_blocks = re.split(r'-{70,}', section_content)

    for block in signal_blocks:
        if len(signals) >= max_signals:
            break

        # Parse each signal block
        ticker_match = re.search(r'Ticker:\s+(\S+)', block)
        if not ticker_match:
            continue

        ticker = ticker_match.group(1)
        price_match = re.search(r'Current Price:\s+\$([0-9.]+)', block)
        analysis_match = re.search(r'Analysis:\s+(\w+)\s+([\w\s-]+?)\s+-\s+Grade\s+([A-F][+-]?)', block)
        entry_match = re.search(r'Entry:\s+\$([0-9.]+)', block)
        stop_match = re.search(r'Stop(?:\sLoss)?:\s+\$([0-9.]+)', block)
        t1_match = re.search(r'T(?:arget\s)?1:\s+\$([0-9.]+)', block)
        t2_match = re.search(r'T(?:arget\s)?2:\s+\$([0-9.]+)', block)
        t3_match = re.search(r'T(?:arget\s)?3:\s+\$([0-9.]+)', block)
        rr_match = re.search(r'Risk/Reward:\s+([0-9.]+):1', block)
        prz_match = re.search(r'Entry Zone \(PRZ\):\s+\$([0-9.]+)\s+-\s+\$([0-9.]+)', block)
        tp_strategy_match = re.search(r'TP Targets:\s+([\w\s]+)', block)

        if analysis_match and entry_match:
            signal = {
                'ticker': ticker,
                'price': price_match.group(1) if price_match else 'N/A',
                'direction': analysis_match.group(1),
                'pattern': analysis_match.group(2).strip(),
                'grade': analysis_match.group(3),
                'entry': entry_match.group(1),
                'stop': stop_match.group(1) if stop_match else 'N/A',
                't1': t1_match.group(1) if t1_match else 'N/A',
                't2': t2_match.group(1) if t2_match else 'N/A',
                't3': t3_match.group(1) if t3_match else 'N/A',
                'rr': rr_match.group(1) if rr_match else 'N/A',
                'prz_low': prz_match.group(1) if prz_match else None,
                'prz_high': prz_match.group(2) if prz_match else None,
                'tp_strategy': tp_strategy_match.group(1).strip() if tp_strategy_match else 'N/A'
            }
            signals.append(signal)

    return signals

# Parse BUY and SELL signals (show all)
buy_signals = parse_signals(os.environ['REPORT_FILE'], "BUY", 999)
sell_signals = parse_signals(os.environ['REPORT_FILE'], "SELL", 999)

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
