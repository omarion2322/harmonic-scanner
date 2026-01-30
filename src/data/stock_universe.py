"""
Stock Universe Selection Module
Fetches stock lists based on configuration settings
"""

import yfinance as yf
import pandas as pd
import requests
from typing import List
import time
import sys
import os

# Add parent directory to path to import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.config import DATA_PERIOD
from data_downloader import download_stock_data


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


def get_nasdaq_tickers_with_volume(min_volume_usd: float = 1_000_000, timeframe: str = '1d', limit: int = None) -> List[str]:
    """
    Get Nasdaq tickers filtered by average daily dollar volume (quick filter using current data).
    Much faster than downloading historical data for each ticker.

    Args:
        min_volume_usd: Minimum average daily dollar volume
        timeframe: Timeframe for scanning ('1d', '1wk', '1mo')
        limit: Maximum number of tickers to return (None = all that meet criteria)

    Returns:
        List of Nasdaq ticker symbols meeting volume criteria
    """
    # Note: This is just a quick pre-filter using snapshot data
    # The filter_by_volume() function performs thorough historical validation
    # For the quick filter, we just use the min_volume_usd as-is (daily requirement)
    adjusted_min_volume_usd = min_volume_usd

    limit_str = f" (limit: {limit})" if limit else ""
    print(f"Fetching Nasdaq tickers with volume > ${min_volume_usd:,.0f} USD{limit_str}...")

    # Try FinViz screener first
    try:
        print("  Trying FinViz screener...")
        url = 'https://finviz.com/screener.ashx?v=111&f=exch_nasd,sh_avgvol_o1000&ft=4'
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

        tables = pd.read_html(url, storage_options=headers)

        if len(tables) >= 2:
            df = tables[1] if len(tables) > 1 else tables[0]
            if 'Ticker' in df.columns:
                tickers = [str(t).strip() for t in df['Ticker'].tolist() if pd.notna(t)]

                # Apply limit if specified
                if limit and len(tickers) > limit:
                    tickers = tickers[:limit]
                    print(f"✓ Fetched {len(tickers)} Nasdaq tickers from FinViz screener (limited)")
                else:
                    print(f"✓ Fetched {len(tickers)} Nasdaq tickers from FinViz screener")
                return tickers
    except Exception as e:
        print(f"⚠ FinViz method failed: {e}")

    # Try NASDAQ API with dollar volume filter
    try:
        print("  Trying NASDAQ API...")
        api_url = 'https://api.nasdaq.com/api/screener/stocks'
        # Use limit parameter if provided, otherwise fetch all
        api_limit = str(limit) if limit else '25000'
        params = {
            'tableonly': 'true',
            'limit': api_limit,
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
            filtered_tickers = []

            for row in rows:
                if 'symbol' not in row:
                    continue

                try:
                    # Quick filter: current price × average volume
                    volume = float(row.get('volume', '0').replace(',', '')) if row.get('volume') else 0
                    price = float(row.get('lastsale', '0').replace('$', '').replace(',', '')) if row.get('lastsale') else 0
                    dollar_volume = volume * price

                    if dollar_volume >= adjusted_min_volume_usd:
                        filtered_tickers.append(row['symbol'])
                        # Stop if we've reached the limit
                        if limit and len(filtered_tickers) >= limit:
                            break
                except (ValueError, AttributeError):
                    filtered_tickers.append(row['symbol'])
                    if limit and len(filtered_tickers) >= limit:
                        break

            if filtered_tickers:
                print(f"✓ Fetched {len(filtered_tickers)} Nasdaq tickers from API (with volume filter)")
                return filtered_tickers

            # No tickers passed filter, return all (limited)
            all_tickers = [row['symbol'] for row in rows if 'symbol' in row]
            if limit and len(all_tickers) > limit:
                all_tickers = all_tickers[:limit]
            print(f"⚠ Could not filter by volume, returning {len(all_tickers)} Nasdaq tickers")
            return all_tickers

    except Exception as e:
        print(f"⚠ NASDAQ API method failed: {e}")

    # Fallback to curated list
    print("  All methods failed, using curated list of major Nasdaq stocks...")
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
                     min_volume_stocks: float = 1_000_000,
                     filter_by_stock_volume: bool = False,
                     lookback_days: int = 7, delay: float = 0.1,
                     min_bars: int = 30, interval: str = '1wk') -> List[str]:
    """
    Filter tickers by average daily volume (dollar or share volume) and minimum bar count.

    Args:
        tickers: List of ticker symbols to filter
        min_volume_usd: Minimum average daily dollar volume (default: $1M USD)
        min_volume_stocks: Minimum average daily share volume (default: 1M shares)
        filter_by_stock_volume: If True, use share volume; if False, use dollar volume
        lookback_days: Number of days to calculate average (default: 7)
        delay: Delay between API calls in seconds (default: 0.1)
        min_bars: Minimum bars required for pattern detection (default: 30)
        interval: Timeframe interval for bar count check (default: '1wk')

    Returns:
        List of tickers that meet volume and bar count criteria
    """
    if filter_by_stock_volume:
        print(f"\nFiltering {len(tickers)} tickers by SHARE volume (>{min_volume_stocks:,.0f} shares avg over {lookback_days} days)...")
    else:
        print(f"\nFiltering {len(tickers)} tickers by DOLLAR volume (>${min_volume_usd:,.0f} USD avg over {lookback_days} days)...")
    interval_name = {'1d': 'days', '1wk': 'weeks', '1mo': 'months'}.get(interval, 'bars')
    print(f"Also filtering for tickers with >= {min_bars} {interval_name} of history")
    print("This may take a few minutes...")

    filtered_tickers = []
    failed_count = 0
    insufficient_bars_count = 0

    for i, ticker in enumerate(tickers, 1):
        try:
            # Progress indicator
            if i % 50 == 0:
                print(f"  Progress: {i}/{len(tickers)} tickers processed, {len(filtered_tickers)} qualify...")

            # OPTIMIZATION: Download full historical data ONCE using the scanning interval
            # Works for all timeframes (1d, 1wk, 1mo):
            # - Downloads DATA_PERIOD at scanning interval (1d/1wk/1mo)
            # - Use full period to verify sufficient history exists
            # - Slice recent bars for volume calculation
            # - Pattern detection downloads same period+interval → CACHE HIT for ALL timeframes!
            hist_full = download_stock_data(
                ticker=ticker,
                period=DATA_PERIOD,
                interval=interval,
                use_cache=True
            )

            # Check if we have sufficient history (if we can download DATA_PERIOD, it's enough)
            if hist_full.empty or len(hist_full) < min_bars:
                insufficient_bars_count += 1
                continue

            # Need at least enough data for volume calculation
            if len(hist_full) < lookback_days + 1:
                failed_count += 1
                continue

            # Slice recent bars for volume check (exclude current/incomplete bar, use previous lookback_days bars)
            # For daily: exclude today, use last 4 days
            # For weekly: exclude current week, use last 20 weeks
            # For monthly: exclude current month, use last 90 months
            hist_filtered = hist_full.iloc[:-1].tail(lookback_days)

            # Calculate average volume based on filter mode
            if filter_by_stock_volume:
                # Share volume mode
                avg_volume = hist_filtered['Volume'].mean()
                meets_criteria = avg_volume >= min_volume_stocks
            else:
                # Dollar volume mode
                hist_filtered_copy = hist_filtered.copy()
                hist_filtered_copy['dollar_volume'] = hist_filtered_copy['Close'] * hist_filtered_copy['Volume']
                avg_volume = hist_filtered_copy['dollar_volume'].mean()
                meets_criteria = avg_volume >= min_volume_usd

            # Check if meets volume criteria
            if not meets_criteria:
                continue  # Skip to next ticker

            # Ticker meets both volume and bar count criteria
            filtered_tickers.append(ticker)

            # Rate limiting
            time.sleep(delay)

        except Exception as e:
            failed_count += 1
            if i % 100 == 0:  # Only show occasional errors to avoid spam
                print(f"  ⚠ Error fetching {ticker}: {e}")
            continue

    low_volume_count = len(tickers) - len(filtered_tickers) - failed_count - insufficient_bars_count

    print(f"\n✓ Filtering complete:")
    print(f"  - {len(filtered_tickers)} tickers meet all criteria (volume + history)")
    print(f"  - {failed_count} tickers failed to fetch or had insufficient data")
    print(f"  - {low_volume_count} tickers excluded due to low volume")
    print(f"  - {insufficient_bars_count} tickers excluded due to insufficient history (< {min_bars} {interval_name})")

    return filtered_tickers


def get_stock_universe(stocks_to_scan: str = 'SP500',
                       etfs_to_scan: bool = False,
                       commodities_to_scan: bool = False,
                       max_stocks: int = None,
                       min_volume_usd: float = 1_000_000,
                       min_volume_stocks: float = 1_000_000,
                       filter_by_stock_volume: bool = False,
                       download_delay: float = 0.1,
                       timeframe: str = '1d',
                       min_bars: int = 30) -> List[str]:
    """
    Get list of stocks, ETFs, and commodities to scan based on configuration.

    Args:
        stocks_to_scan: Stock universe selection - 'All', 'SP500', or 'None'
        etfs_to_scan: Whether to include ETFs (True/False)
        commodities_to_scan: Whether to include commodity futures (True/False)
        max_stocks: Maximum number of stocks to return (None = all)
        min_volume_usd: Minimum average daily dollar volume (for 'All' mode)
        min_volume_stocks: Minimum average daily share volume (for 'All' mode)
        filter_by_stock_volume: If True, use share volume; if False, use dollar volume
        download_delay: Delay between API calls for volume filtering
        timeframe: Timeframe for scanning ('1d', '1wk', '1mo')
        min_bars: Minimum bars required for pattern detection (default: 30)

    Returns:
        List of ticker symbols to scan
    """
    from .etf_universe import get_all_etfs
    from .commodity_universe import get_all_commodities

    print("="*80)
    print("FETCHING STOCK UNIVERSE")
    print("="*80)
    print()

    all_tickers = []
    scan_types = []

    # Add stocks based on configuration
    if stocks_to_scan and stocks_to_scan.upper() != 'NONE':
        if stocks_to_scan.upper() == 'ALL':
            if filter_by_stock_volume:
                print(f"Selected: ALL - All Nasdaq stocks (filtered by volume > {min_volume_stocks:,} shares)")
            else:
                print(f"Selected: ALL - All Nasdaq stocks (filtered by volume > ${min_volume_usd:,} USD)")
            print()
            # Pass max_stocks to limit initial fetch - much faster!
            nasdaq_tickers = get_nasdaq_tickers_with_volume(
                min_volume_usd=min_volume_usd,
                timeframe=timeframe,
                limit=max_stocks  # Limit API fetch to max_stocks from the start
            )

            # Apply historical volume validation to ensure stocks consistently meet volume requirements
            # This filters out stocks that may have passed the quick screener but don't have sustained volume
            # Lookback period matches the scanning timeframe: 1d=1 day, 3d=3 days, 1wk=5 days, 1mo=23 days
            timeframe_lookback = {
                '1d': 4,   # 1 trading day, multiplied by 4
                '3d': 12,   # 3 trading days, multiplied by 4
                '1wk': 20,  # 1 week = 5 trading days, multiplied by 4
                '1mo': 90  # 1 month ≈ 23 trading days, multipled by 4
            }
            lookback = timeframe_lookback.get(timeframe, 7)  # Default to 7 if unknown timeframe

            print(f"\nApplying historical volume validation (this may take a few minutes)...")
            nasdaq_tickers = filter_by_volume(
                nasdaq_tickers,
                min_volume_usd=min_volume_usd,
                min_volume_stocks=min_volume_stocks,
                filter_by_stock_volume=filter_by_stock_volume,
                lookback_days=lookback,
                delay=download_delay,
                min_bars=min_bars,
                interval=timeframe
            )

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

    # Add Commodities if requested
    if commodities_to_scan:
        print("Selected: Commodities - All major commodity futures")
        print()
        commodity_tickers = get_all_commodities()
        print(f"✓ Loaded {len(commodity_tickers)} commodity futures")
        all_tickers.extend(commodity_tickers)
        scan_types.append('Commodities')

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

