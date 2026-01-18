"""
Crypto Universe Selection Module
Fetches cryptocurrency lists based on market cap from CoinGecko API
"""

import requests
import time
from typing import List, Optional
import json
import os
from pathlib import Path
from datetime import datetime, timedelta


def parse_cryptos_to_scan_config(config_value: str) -> int:
    """
    Parse CRYPTOS_TO_SCAN config value.

    Args:
        config_value: String like "Top100", "Top50", "Top20", "Top500", or None

    Returns:
        Integer N for top N cryptos, or 0 if disabled

    Examples:
        "Top100" -> 100
        "Top20" -> 20
        "None" -> 0
    """
    if not config_value or config_value.upper() == 'NONE':
        return 0

    # Extract number from string like "Top100"
    try:
        if config_value.upper().startswith('TOP'):
            return int(config_value[3:])
        else:
            return int(config_value)
    except (ValueError, IndexError):
        print(f"⚠ Could not parse CRYPTOS_TO_SCAN value: {config_value}, defaulting to 100")
        return 100


def get_coingecko_top_cryptos(top_n: int = 500, use_cache: bool = True) -> List[str]:
    """
    Fetch top N cryptocurrencies by market cap from CoinGecko API.

    Args:
        top_n: Number of top cryptos to fetch (20, 50, 100, 500)
        use_cache: Whether to use cached results (default: True, cache expires after 24h)

    Returns:
        List of Yahoo Finance format tickers (e.g., ['BTC-USD', 'ETH-USD'])
    """
    # Cache file path
    cache_dir = Path('/tmp')
    cache_file = cache_dir / f'coingecko_cache_{datetime.now().strftime("%Y-%m-%d")}.json'

    # Try to load from cache if enabled
    if use_cache and cache_file.exists():
        try:
            cache_age = datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
            if cache_age < timedelta(hours=24):
                with open(cache_file, 'r') as f:
                    cached_data = json.load(f)
                    if 'cryptos' in cached_data:
                        all_cryptos = cached_data['cryptos']
                        result = all_cryptos[:top_n]
                        print(f"✓ Loaded {len(result)} cryptos from cache (age: {cache_age.seconds // 3600}h)")
                        return result
        except Exception as e:
            print(f"⚠ Cache read error: {e}, fetching fresh data...")

    # Fetch from CoinGecko API
    print(f"Fetching top {top_n} cryptocurrencies from CoinGecko...")

    base_url = 'https://api.coingecko.com/api/v3/coins/markets'
    all_cryptos = []

    # CoinGecko allows max 250 per page
    pages_needed = (top_n + 249) // 250  # Round up

    for page in range(1, pages_needed + 1):
        params = {
            'vs_currency': 'usd',
            'order': 'market_cap_desc',
            'per_page': min(250, top_n - len(all_cryptos)),
            'page': page,
            'sparkline': 'false'
        }

        # Retry logic with exponential backoff
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = requests.get(base_url, params=params, timeout=30)

                if response.status_code == 429:  # Rate limited
                    wait_time = 2 ** attempt  # 1s, 2s, 4s
                    print(f"  Rate limited, waiting {wait_time}s...")
                    time.sleep(wait_time)
                    continue

                response.raise_for_status()
                data = response.json()

                # Convert to Yahoo Finance format
                for crypto in data:
                    symbol = crypto['symbol'].upper()

                    # Handle special cases
                    symbol_map = {
                        'MIOTA': 'IOTA',  # IOTA ticker mapping
                        'WBTC': 'BTC',    # Wrapped Bitcoin (use BTC-USD instead)
                    }
                    symbol = symbol_map.get(symbol, symbol)

                    ticker = f"{symbol}-USD"
                    all_cryptos.append(ticker)

                print(f"  Fetched page {page}/{pages_needed} ({len(all_cryptos)} cryptos)")
                break  # Success, exit retry loop

            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    print(f"  Request failed (attempt {attempt + 1}/{max_retries}): {e}")
                    print(f"  Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    print(f"⚠ Failed to fetch from CoinGecko after {max_retries} attempts: {e}")
                    return get_fallback_crypto_list(top_n)

        # Rate limiting between pages (respect free tier limits)
        if page < pages_needed:
            time.sleep(1.5)  # 1.5s between requests to stay under rate limits

    # Filter out stablecoins (they have no price patterns)
    stablecoin_symbols = ['USDT', 'USDC', 'BUSD', 'DAI', 'UST', 'TUSD', 'USDP', 'USDD', 'FRAX', 'GUSD']
    filtered_cryptos = [c for c in all_cryptos if not any(stable in c for stable in stablecoin_symbols)]

    removed_count = len(all_cryptos) - len(filtered_cryptos)
    if removed_count > 0:
        print(f"  Filtered out {removed_count} stablecoins")

    # Cache the results
    try:
        with open(cache_file, 'w') as f:
            json.dump({'cryptos': filtered_cryptos, 'timestamp': datetime.now().isoformat()}, f)
        print(f"  Cached results to {cache_file}")
    except Exception as e:
        print(f"⚠ Failed to cache results: {e}")

    result = filtered_cryptos[:top_n]
    print(f"✓ Fetched {len(result)} cryptocurrencies from CoinGecko")
    return result


def get_fallback_crypto_list(top_n: int = 100) -> List[str]:
    """
    Fallback crypto list if CoinGecko API fails.
    Hardcoded list of top cryptocurrencies by market cap (manually updated).

    Args:
        top_n: Number of top cryptos to return

    Returns:
        List of crypto tickers in Yahoo Finance format
    """
    print("  Using fallback list of top cryptocurrencies...")

    # Top 100 cryptocurrencies by market cap (as of 2025)
    fallback_list = [
        # Top 10
        'BTC-USD', 'ETH-USD', 'BNB-USD', 'XRP-USD', 'SOL-USD',
        'ADA-USD', 'AVAX-USD', 'DOGE-USD', 'DOT-USD', 'TRX-USD',

        # Top 20
        'LINK-USD', 'MATIC-USD', 'SHIB-USD', 'LTC-USD', 'UNI-USD',
        'ATOM-USD', 'XLM-USD', 'ETC-USD', 'BCH-USD', 'XMR-USD',

        # Top 40
        'APT-USD', 'FIL-USD', 'NEAR-USD', 'ALGO-USD', 'VET-USD',
        'ICP-USD', 'HBAR-USD', 'AAVE-USD', 'EOS-USD', 'THETA-USD',
        'AXS-USD', 'XTZ-USD', 'SAND-USD', 'MANA-USD', 'EGLD-USD',
        'FLOW-USD', 'GRT-USD', 'FTM-USD', 'KLAY-USD', 'CHZ-USD',

        # Top 60
        'ZEC-USD', 'ENJ-USD', 'KSM-USD', 'BAT-USD', 'LRC-USD',
        'COMP-USD', 'DASH-USD', 'ZIL-USD', 'WAVES-USD', 'QTUM-USD',
        'ICX-USD', 'ONT-USD', 'ZRX-USD', 'RVN-USD', 'OMG-USD',
        'SC-USD', 'NANO-USD', 'DGB-USD', 'BTT-USD', 'HOT-USD',

        # Top 80
        'WOO-USD', 'CRV-USD', 'SNX-USD', 'SUSHI-USD', 'YFI-USD',
        'BAL-USD', 'REN-USD', 'KNC-USD', '1INCH-USD', 'BNT-USD',
        'OCEAN-USD', 'ANKR-USD', 'STORJ-USD', 'SKL-USD', 'BAND-USD',
        'NKN-USD', 'CELO-USD', 'RSR-USD', 'OGN-USD', 'REP-USD',

        # Top 100
        'INJ-USD', 'RUNE-USD', 'KAVA-USD', 'AR-USD', 'IMX-USD',
        'GALA-USD', 'ENS-USD', 'GMT-USD', 'APE-USD', 'OP-USD',
        'ARB-USD', 'LDO-USD', 'STX-USD', 'MKR-USD', 'BLUR-USD',
        'RNDR-USD', 'PEPE-USD', 'FLOKI-USD', 'FET-USD', 'AGIX-USD',
    ]

    return fallback_list[:top_n]


def get_crypto_universe(cryptos_to_scan: str = 'Top100',
                        min_volume_usd: float = 1_000_000,
                        download_delay: float = 0.1,
                        timeframe: str = '1d',
                        min_bars: int = 30) -> List[str]:
    """
    Get cryptocurrency universe based on configuration.

    Args:
        cryptos_to_scan: Config value like "Top100", "Top50", "Top20", "Top500"
        min_volume_usd: Minimum 24h volume (for additional filtering, not currently used)
        download_delay: Rate limiting delay (not currently used)
        timeframe: Trading timeframe (not currently used)
        min_bars: Minimum bars required (validation handled by scanner)

    Returns:
        List of crypto tickers in Yahoo Finance format

    Note:
        Volume and bar count filtering are handled by the scanner itself,
        similar to how stock_universe works. CoinGecko API already filters
        by market cap, which is a good proxy for liquidity/volume.
    """
    # Parse config to get top N
    top_n = parse_cryptos_to_scan_config(cryptos_to_scan)

    if top_n == 0:
        return []

    # Fetch from CoinGecko (with caching and fallback)
    try:
        cryptos = get_coingecko_top_cryptos(top_n=top_n, use_cache=True)
    except Exception as e:
        print(f"⚠ Error fetching from CoinGecko: {e}")
        cryptos = get_fallback_crypto_list(top_n)

    if not cryptos:
        print("⚠ No cryptocurrencies fetched, using fallback list")
        cryptos = get_fallback_crypto_list(top_n)

    return cryptos
