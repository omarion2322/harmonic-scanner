"""
Stock Universe Selection Module
Fetches stock lists based on configuration settings
"""

import yfinance as yf
import pandas as pd
import requests
from typing import List
import time


def get_sp500_tickers() -> List[str]:
    """
    Get S&P 500 stock tickers from SlickCharts.

    Returns:
        List of S&P 500 ticker symbols
    """
    try:
        # Fetch S&P 500 list from SlickCharts
        url = 'https://www.slickcharts.com/sp500'
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        tables = pd.read_html(url, storage_options=headers)
        sp500_table = tables[0]

        # Get tickers from the 'Symbol' column
        tickers = sp500_table['Symbol'].tolist()

        # Clean tickers (replace dots with dashes for Yahoo Finance)
        tickers = [ticker.replace('.', '-') for ticker in tickers]

        print(f"✓ Fetched {len(tickers)} S&P 500 tickers from SlickCharts")
        return tickers
    except Exception as e:
        print(f"⚠ Error fetching S&P 500 list: {e}")
        print("  Using fallback list of major stocks...")
        # Fallback to major stocks if fetch fails
        return [
            'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA', 'BRK-B',
            'V', 'UNH', 'JNJ', 'WMT', 'JPM', 'MA', 'PG', 'XOM', 'HD', 'CVX',
            'MRK', 'ABBV', 'KO', 'PEP', 'COST', 'AVGO', 'LLY', 'TMO', 'MCD'
        ]


def get_nasdaq_tickers_with_volume(min_volume_usd: float = 1_000_000) -> List[str]:
    """
    Get Nasdaq tickers filtered by average daily volume (server-side filtering).
    Much faster than downloading data for each ticker individually.

    Args:
        min_volume_usd: Minimum average daily dollar volume

    Returns:
        List of Nasdaq ticker symbols meeting volume criteria
    """
    try:
        print(f"Fetching Nasdaq tickers with volume > ${min_volume_usd:,.0f} USD...")

        # Method 1: Use FinViz screener (web scraping with volume filter)
        try:
            print("  Trying FinViz screener...")

            # FinViz URL with filters:
            # - Exchange: NASDAQ
            # - Average Volume: > 1M shares (we'll filter by dollar volume after)
            url = 'https://finviz.com/screener.ashx?v=111&f=exch_nasd,sh_avgvol_o1000&ft=4'

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }

            tables = pd.read_html(url, storage_options=headers)

            # FinViz results are in a table
            if len(tables) >= 2:
                # The main data table is usually the second one
                df = tables[1] if len(tables) > 1 else tables[0]

                # Extract ticker symbols (usually in 'Ticker' column)
                if 'Ticker' in df.columns:
                    tickers = df['Ticker'].tolist()
                    # Clean tickers
                    tickers = [str(t).strip() for t in tickers if pd.notna(t)]

                    print(f"✓ Fetched {len(tickers)} Nasdaq tickers from FinViz screener")
                    return tickers

        except Exception as e:
            print(f"⚠ FinViz method failed: {e}")

        # Method 2: Use NASDAQ API with volume data
        try:
            print("  Trying NASDAQ API...")

            api_url = 'https://api.nasdaq.com/api/screener/stocks'
            params = {
                'tableonly': 'true',
                'limit': '25000',
                'exchange': 'nasdaq',
                'download': 'true'
            }
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json'
            }

            response = requests.get(api_url, params=params, headers=headers, timeout=30)
            data = response.json()

            if 'data' in data and 'rows' in data['data']:
                rows = data['data']['rows']

                # Filter by dollar volume if available
                filtered_tickers = []
                for row in rows:
                    if 'symbol' not in row:
                        continue

                    # Try to calculate or extract dollar volume
                    try:
                        # Some APIs provide 'dollarvolume' or we calculate from 'volume' and 'lastsale'
                        volume = float(row.get('volume', 0).replace(',', '')) if 'volume' in row else 0
                        price = float(row.get('lastsale', '0').replace('$', '').replace(',', '')) if 'lastsale' in row else 0

                        dollar_volume = volume * price

                        if dollar_volume >= min_volume_usd:
                            filtered_tickers.append(row['symbol'])
                    except:
                        # If we can't calculate, include it (we'll filter later if needed)
                        filtered_tickers.append(row['symbol'])

                if filtered_tickers:
                    print(f"✓ Fetched {len(filtered_tickers)} Nasdaq tickers from API (with volume filter)")
                    return filtered_tickers
                else:
                    # If filtering failed, return all Nasdaq tickers
                    all_tickers = [row['symbol'] for row in rows if 'symbol' in row]
                    print(f"⚠ Could not filter by volume, returning all {len(all_tickers)} Nasdaq tickers")
                    return all_tickers

        except Exception as e:
            print(f"⚠ NASDAQ API method failed: {e}")

        # Fallback: Return curated major Nasdaq list
        print("  All methods failed, using curated list of major Nasdaq stocks...")
        return get_major_nasdaq_tickers()

    except Exception as e:
        print(f"⚠ Error in get_nasdaq_tickers_with_volume: {e}")
        return get_major_nasdaq_tickers()


def get_major_nasdaq_tickers() -> List[str]:
    """
    Get a curated list of major Nasdaq-traded stocks as fallback.

    Returns:
        List of major Nasdaq ticker symbols
    """
    print("  Using curated list of major Nasdaq stocks...")
    return [
        # Technology
        'AAPL', 'MSFT', 'GOOGL', 'GOOG', 'AMZN', 'NVDA', 'META', 'TSLA', 'AVGO', 'ORCL',
        'ADBE', 'CRM', 'CSCO', 'ACN', 'AMD', 'INTC', 'QCOM', 'TXN', 'AMAT', 'INTU',
        'MU', 'ADI', 'LRCX', 'KLAC', 'SNPS', 'CDNS', 'MCHP', 'NXPI', 'MRVL', 'FTNT',
        # Consumer
        'COST', 'SBUX', 'BKNG', 'ABNB', 'EBAY', 'ETSY', 'CHTR', 'CMCSA', 'NFLX', 'DIS',
        # Healthcare/Biotech
        'AMGN', 'GILD', 'REGN', 'VRTX', 'BIIB', 'ILMN', 'MRNA', 'DXCM', 'ISRG', 'ALGN',
        # Other
        'PAYX', 'ADP', 'PCAR', 'MDLZ', 'PEP', 'MELI', 'LULU', 'ODFL', 'CTAS', 'FAST',
        'PANW', 'CRWD', 'ZS', 'DDOG', 'NET', 'SNOW', 'TEAM', 'WDAY', 'DOCU', 'ZM'
    ]


def filter_by_volume(tickers: List[str], min_volume_usd: float = 1_000_000,
                     lookback_days: int = 7, delay: float = 0.1) -> List[str]:
    """
    Filter tickers by average daily volume in USD.

    Args:
        tickers: List of ticker symbols to filter
        min_volume_usd: Minimum average daily volume in USD (default: $1M)
        lookback_days: Number of days to calculate average (default: 7)
        delay: Delay between API calls in seconds (default: 0.1)

    Returns:
        List of tickers that meet volume criteria
    """
    print(f"\nFiltering {len(tickers)} tickers by volume (>${min_volume_usd:,.0f} USD avg over {lookback_days} days)...")
    print("This may take a few minutes...")

    filtered_tickers = []
    failed_count = 0

    for i, ticker in enumerate(tickers, 1):
        try:
            # Progress indicator
            if i % 50 == 0:
                print(f"  Progress: {i}/{len(tickers)} tickers processed, {len(filtered_tickers)} qualify...")

            # Fetch recent data (fetch extra day to exclude today)
            stock = yf.Ticker(ticker)
            hist = stock.history(period=f"{lookback_days + 1}d")

            if hist.empty or len(hist) < 3:  # Need at least 3 days of data
                failed_count += 1
                continue

            # Exclude today (last row) and use the previous lookback_days
            hist_filtered = hist.iloc[:-1].tail(lookback_days)

            # Calculate average daily volume in USD (price * volume)
            hist_filtered['dollar_volume'] = hist_filtered['Close'] * hist_filtered['Volume']
            avg_volume_usd = hist_filtered['dollar_volume'].mean()

            # Check if meets criteria
            if avg_volume_usd >= min_volume_usd:
                filtered_tickers.append(ticker)

            # Rate limiting
            time.sleep(delay)

        except Exception as e:
            failed_count += 1
            if i % 100 == 0:  # Only show occasional errors to avoid spam
                print(f"  ⚠ Error fetching {ticker}: {e}")
            continue

    print(f"\n✓ Volume filtering complete:")
    print(f"  - {len(filtered_tickers)} tickers meet volume criteria")
    print(f"  - {failed_count} tickers failed to fetch or had insufficient data")
    print(f"  - {len(tickers) - len(filtered_tickers) - failed_count} tickers excluded due to low volume")

    return filtered_tickers


def get_stock_universe(stocks_to_scan: str = 'SP500',
                       etfs_to_scan: bool = False,
                       max_stocks: int = None,
                       min_volume_usd: float = 1_000_000,
                       download_delay: float = 0.1) -> List[str]:
    """
    Get list of stocks and ETFs to scan based on configuration.

    Args:
        stocks_to_scan: Stock universe selection - 'All', 'SP500', or 'None'
        etfs_to_scan: Whether to include ETFs (True/False)
        max_stocks: Maximum number of stocks to return (None = all)
        min_volume_usd: Minimum average daily volume in USD (for 'All' mode)
        download_delay: Delay between API calls for volume filtering

    Returns:
        List of ticker symbols to scan
    """
    from etf_universe import get_all_etfs

    print("="*80)
    print("FETCHING STOCK UNIVERSE")
    print("="*80)
    print()

    all_tickers = []
    scan_types = []

    # Add stocks based on configuration
    if stocks_to_scan and stocks_to_scan.upper() != 'NONE':
        if stocks_to_scan.upper() == 'ALL':
            print(f"Selected: ALL - All Nasdaq stocks (filtered by volume > ${min_volume_usd:,} USD)")
            print()
            nasdaq_tickers = get_nasdaq_tickers_with_volume(min_volume_usd=min_volume_usd)
            all_tickers.extend(nasdaq_tickers)
            scan_types.append('Nasdaq (All)')

        elif stocks_to_scan.upper() == 'SP500':
            print("Selected: SP500 - S&P 500 stocks")
            print()
            sp500_tickers = get_sp500_tickers()
            all_tickers.extend(sp500_tickers)
            scan_types.append('S&P 500')

    # Add ETFs if requested
    if etfs_to_scan:
        print("Selected: ETFs - All leading ETFs across categories")
        print()
        etf_tickers = get_all_etfs()
        print(f"✓ Loaded {len(etf_tickers)} ETFs")
        all_tickers.extend(etf_tickers)
        scan_types.append('ETFs')

    # Remove duplicates while preserving order
    seen = set()
    unique_tickers = []
    for ticker in all_tickers:
        if ticker not in seen:
            seen.add(ticker)
            unique_tickers.append(ticker)

    tickers = unique_tickers

    # Apply max stocks limit if specified
    if max_stocks and max_stocks < len(tickers):
        print(f"\n⚠ Limiting to first {max_stocks} tickers (MAX_STOCKS_TO_SCAN setting)")
        tickers = tickers[:max_stocks]

    print()
    if scan_types:
        print(f"Final universe: {len(tickers)} tickers from {', '.join(scan_types)}")
    else:
        print("⚠ No universe selected - check STOCKS_TO_SCAN and ETFS_TO_SCAN settings")
    print("="*80)
    print()

    return tickers


if __name__ == "__main__":
    # Test the module
    print("\nTesting S&P 500 fetch:")
    sp500 = get_sp500_tickers()
    print(f"Sample tickers: {sp500[:10]}")

    print("\n" + "="*80)
    print("\nTesting Nasdaq fetch:")
    nasdaq = get_nasdaq_tickers()
    print(f"Sample tickers: {nasdaq[:10]}")

    print("\n" + "="*80)
    print("\nTesting volume filter (first 10 tickers only):")
    filtered = filter_by_volume(nasdaq[:10], min_volume_usd=1_000_000, lookback_days=7, delay=0.2)
    print(f"Filtered tickers: {filtered}")
