#!/usr/bin/env python3
"""
Cryptocurrency Harmonic Pattern Scanner
Scans top cryptocurrencies for harmonic patterns using the same detection logic as stocks.
Reports are saved to crypto_reports/ directory.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from harmonic_scanner import HarmonicScanner
import config


def main():
    """Scan cryptocurrencies only"""
    # Override stock scanning settings to scan crypto only
    config.STOCKS_TO_SCAN = 'None'
    config.SCAN_ETFS = False
    config.SCAN_COMMODITIES = False

    # Get crypto list based on CRYPTOS_TO_SCAN config
    crypto_tickers = config.get_crypto_list()

    if not crypto_tickers:
        print("No cryptocurrencies configured.")
        print("Set CRYPTOS_TO_SCAN in src/config/config.py (e.g., 'Top100', 'Top50', 'Top20', 'Top500')")
        return

    print(f"Scanning {len(crypto_tickers)} cryptocurrencies for harmonic patterns...")
    print()

    # Create scanner with crypto asset type (routes to crypto_reports/)
    scanner = HarmonicScanner(asset_type='crypto')

    # Override the ticker list to use crypto tickers
    original_get_stock_list = config.get_stock_list

    def get_crypto_tickers():
        return crypto_tickers

    config.get_stock_list = get_crypto_tickers

    # Run the scan
    try:
        # Get max stocks setting
        max_stocks = scanner.config_helper.get_int('MAX_STOCKS_TO_SCAN', None)

        # Run scan
        results = scanner.run_scan(max_stocks=max_stocks)

        # Generate and display report
        report = scanner.generate_report(results)
        print(report)

        # Save report
        scanner.save_report(report)
    finally:
        # Restore original function
        config.get_stock_list = original_get_stock_list


if __name__ == '__main__':
    main()
