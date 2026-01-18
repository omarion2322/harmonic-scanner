"""
Crypto Data Downloader with Cascading Fallbacks

Provides robust cryptocurrency data downloading with multiple sources:
1. Primary: Yahoo Finance (yfinance) - BTC-USD format
2. Fallback 1: Binance API - BTCUSDT format
3. Fallback 2: CoinGecko OHLCV API - coin ID format

Features:
- Automatic ticker format conversion
- Exponential backoff retry mechanism
- Rate limiting protection
- Consistent pandas DataFrame output format
"""

import yfinance as yf
import pandas as pd
import time
import requests
from typing import Optional, Dict
from datetime import datetime, timedelta
from binance.spot import Spot
from logging_config import get_logger

logger = get_logger(__name__)


# Ticker format conversion mappings
YAHOO_TO_BINANCE = {
    'BTC-USD': 'BTCUSDT',
    'ETH-USD': 'ETHUSDT',
    'BNB-USD': 'BNBUSDT',
    # Add more as needed, or use the conversion function below
}

SPECIAL_CASES = {
    'IOTA-USD': 'IOTAUSDT',  # MIOTA on CoinGecko, IOTA on Yahoo
    'WBTC-USD': 'BTCUSDT',   # Wrapped Bitcoin maps to Bitcoin
}

COINGECKO_ID_MAP = {
    'BTC-USD': 'bitcoin',
    'ETH-USD': 'ethereum',
    'BNB-USD': 'binancecoin',
    'XRP-USD': 'ripple',
    'SOL-USD': 'solana',
    'ADA-USD': 'cardano',
    'DOGE-USD': 'dogecoin',
    # Auto-generated for others
}


def convert_yahoo_to_binance(yahoo_ticker: str) -> str:
    """
    Convert Yahoo Finance ticker to Binance format.

    Examples:
        BTC-USD -> BTCUSDT
        ETH-USD -> ETHUSDT
        LINK-USD -> LINKUSDT
    """
    # Check special cases first
    if yahoo_ticker in SPECIAL_CASES:
        return SPECIAL_CASES[yahoo_ticker]

    # Check predefined mappings
    if yahoo_ticker in YAHOO_TO_BINANCE:
        return YAHOO_TO_BINANCE[yahoo_ticker]

    # Auto-convert: Remove -USD and add USDT
    if yahoo_ticker.endswith('-USD'):
        base = yahoo_ticker[:-4]  # Remove '-USD'
        return f"{base}USDT"

    return yahoo_ticker


def convert_yahoo_to_coingecko_id(yahoo_ticker: str) -> str:
    """
    Convert Yahoo Finance ticker to CoinGecko coin ID.

    Examples:
        BTC-USD -> bitcoin
        ETH-USD -> ethereum
    """
    # Check predefined mappings
    if yahoo_ticker in COINGECKO_ID_MAP:
        return COINGECKO_ID_MAP[yahoo_ticker]

    # Auto-generate: lowercase symbol without -USD
    if yahoo_ticker.endswith('-USD'):
        base = yahoo_ticker[:-4].lower()
        return base

    return yahoo_ticker.lower()


def interval_to_binance(interval: str) -> str:
    """
    Convert standard interval to Binance format.

    Args:
        interval: Standard interval ('1d', '1wk', '1mo')

    Returns:
        Binance interval format
    """
    mapping = {
        '1d': '1d',
        '1h': '1h',
        '4h': '4h',
        '1wk': '1w',
        '1mo': '1M',
    }
    return mapping.get(interval, '1d')


def interval_to_coingecko_days(period: str, interval: str) -> int:
    """
    Convert period/interval to CoinGecko days parameter.

    CoinGecko uses 'days' parameter for historical data.
    """
    # Map periods to days
    period_days = {
        '1mo': 30,
        '3mo': 90,
        '6mo': 180,
        '1y': 365,
        '2y': 730,
        '5y': 1825,
        'max': 'max'
    }

    return period_days.get(period, 365)


def download_from_yfinance(
    ticker: str,
    period: str = '1y',
    interval: str = '1d',
    auto_adjust: bool = False
) -> Optional[pd.DataFrame]:
    """
    Download crypto data from Yahoo Finance.

    Args:
        ticker: Crypto ticker in Yahoo format (BTC-USD)
        period: Data period
        interval: Data interval
        auto_adjust: Whether to auto-adjust prices

    Returns:
        DataFrame with OHLCV data or None on failure
    """
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(
            period=period,
            interval=interval,
            auto_adjust=auto_adjust,
            raise_errors=False
        )

        if not df.empty:
            return df
    except (ValueError, KeyError, OSError) as e:
        logger.debug("Yahoo Finance download failed: %s", e)
        pass  # Fall through to return None
    except Exception as e:
        logger.debug("Unexpected error in Yahoo Finance download: %s", e)
        pass  # Fall through to return None

    return None


def download_from_binance(
    ticker: str,
    period: str = '1y',
    interval: str = '1d'
) -> Optional[pd.DataFrame]:
    """
    Download crypto data from Binance API.

    Args:
        ticker: Crypto ticker in Yahoo format (BTC-USD)
        period: Data period
        interval: Data interval

    Returns:
        DataFrame with OHLCV data in yfinance format or None on failure
    """
    try:
        # Convert ticker format
        binance_symbol = convert_yahoo_to_binance(ticker)
        binance_interval = interval_to_binance(interval)

        # Calculate start time based on period
        period_days = {
            '1mo': 30,
            '3mo': 90,
            '6mo': 180,
            '1y': 365,
            '2y': 730,
            '5y': 1825,
            'max': 1825  # Binance has ~5 years of data for most pairs
        }

        days = period_days.get(period, 365)
        start_time = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)

        # Initialize Binance client (no API key needed for public data)
        client = Spot()

        # Fetch klines (candlestick data)
        klines = client.klines(
            symbol=binance_symbol,
            interval=binance_interval,
            startTime=start_time,
            limit=1000  # Max limit per request
        )

        if not klines:
            return None

        # Convert to pandas DataFrame matching yfinance format
        df = pd.DataFrame(klines, columns=[
            'timestamp', 'Open', 'High', 'Low', 'Close', 'Volume',
            'close_time', 'quote_volume', 'trades', 'taker_buy_base',
            'taker_buy_quote', 'ignore'
        ])

        # Convert timestamp to datetime
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        df.index.name = 'Date'

        # Convert to numeric types
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        # Keep only OHLCV columns to match yfinance format
        df = df[['Open', 'High', 'Low', 'Close', 'Volume']]

        return df

    except (ValueError, KeyError) as e:
        # Expected errors from Binance API
        logger.debug("Binance download failed (data error): %s", e)
        return None
    except OSError as e:
        # Network errors
        logger.debug("Binance download failed (network error): %s", e)
        return None
    except Exception as e:
        # Unexpected errors
        logger.debug("Unexpected error in Binance download: %s", e)
        return None


def download_from_coingecko(
    ticker: str,
    period: str = '1y',
    interval: str = '1d'
) -> Optional[pd.DataFrame]:
    """
    Download crypto data from CoinGecko OHLCV API.

    Args:
        ticker: Crypto ticker in Yahoo format (BTC-USD)
        period: Data period
        interval: Data interval (only 1d supported by CoinGecko free tier)

    Returns:
        DataFrame with OHLCV data in yfinance format or None on failure
    """
    try:
        # Convert ticker to CoinGecko ID
        coin_id = convert_yahoo_to_coingecko_id(ticker)

        # Calculate days parameter
        days = interval_to_coingecko_days(period, interval)

        # CoinGecko OHLC endpoint
        url = f'https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc'
        params = {
            'vs_currency': 'usd',
            'days': days
        }

        response = requests.get(url, params=params, timeout=30)

        if response.status_code != 200:
            return None

        data = response.json()

        if not data or not isinstance(data, list):
            return None

        # CoinGecko OHLC format: [[timestamp, open, high, low, close], ...]
        df = pd.DataFrame(data, columns=['timestamp', 'Open', 'High', 'Low', 'Close'])

        # Convert timestamp to datetime
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        df.index.name = 'Date'

        # CoinGecko doesn't provide volume in OHLC endpoint, set to 0
        df['Volume'] = 0.0

        # Convert to numeric types
        for col in ['Open', 'High', 'Low', 'Close']:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        return df

    except (ValueError, KeyError) as e:
        # Expected errors from CoinGecko API
        logger.debug("CoinGecko download failed (data error): %s", e)
        return None
    except OSError as e:
        # Network errors
        logger.debug("CoinGecko download failed (network error): %s", e)
        return None
    except Exception as e:
        # Unexpected errors
        logger.debug("Unexpected error in CoinGecko download: %s", e)
        return None


def download_crypto_data(
    ticker: str,
    period: str = '1y',
    interval: str = '1d',
    auto_adjust: bool = False,
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    verbose: bool = True
) -> pd.DataFrame:
    """
    Download cryptocurrency data with cascading fallbacks.

    Tries sources in order:
    1. Yahoo Finance (yfinance)
    2. Binance API
    3. CoinGecko OHLCV API

    Args:
        ticker: Crypto ticker in Yahoo format (BTC-USD, ETH-USD, etc.)
        period: Data period (e.g., '1y', '5y', 'max')
        interval: Data interval (e.g., '1d', '1wk', '1mo')
        auto_adjust: Whether to auto-adjust prices (yfinance only)
        max_retries: Maximum number of retry attempts per source
        initial_delay: Initial delay before first retry (seconds)
        backoff_factor: Multiplier for exponential backoff
        verbose: Whether to print status messages

    Returns:
        DataFrame with OHLCV data, or empty DataFrame on failure

    Example:
        >>> df = download_crypto_data('BTC-USD', period='1y', interval='1d')
        >>> if not df.empty:
        ...     print(f"Downloaded {len(df)} bars")
    """

    last_error = None
    delay = initial_delay

    # Try each source with retries
    sources = [
        ('Yahoo Finance', lambda: download_from_yfinance(ticker, period, interval, auto_adjust)),
        ('Binance', lambda: download_from_binance(ticker, period, interval)),
        ('CoinGecko', lambda: download_from_coingecko(ticker, period, interval))
    ]

    for source_name, download_func in sources:
        for attempt in range(max_retries):
            try:
                df = download_func()

                if df is not None and not df.empty:
                    # SUCCESS
                    if verbose and (source_name != 'Yahoo Finance' or attempt > 0):
                        logger.info("%s: Downloaded from %s%s", ticker, source_name,
                                  f" (attempt {attempt + 1})" if attempt > 0 else "")
                    return df

            except (ValueError, KeyError, OSError) as e:
                # Expected errors
                last_error = f"{source_name} error: {str(e)}"
                logger.debug("%s: %s", ticker, last_error)
            except Exception as e:
                # Unexpected errors
                last_error = f"{source_name} unexpected error: {str(e)}"
                logger.debug("%s: %s", ticker, last_error)

            # Retry with backoff if attempts remain for this source
            if attempt < max_retries - 1:
                if verbose:
                    logger.info("%s: Retrying %s in %.1fs... (attempt %d/%d)", ticker, source_name, delay, attempt + 2, max_retries)
                time.sleep(delay)
                delay *= backoff_factor

        # Reset delay for next source
        delay = initial_delay

    # All sources and retries exhausted
    if verbose:
        logger.error("%s: All sources failed (Yahoo Finance, Binance, CoinGecko)", ticker)
    return pd.DataFrame()


def download_crypto_with_rate_limit(
    ticker: str,
    period: str = '1y',
    interval: str = '1d',
    auto_adjust: bool = False,
    rate_limit_delay: float = 0.1,
    max_retries: int = 3,
    verbose: bool = True
) -> pd.DataFrame:
    """
    Download crypto data with built-in rate limiting and cascading fallbacks.

    Args:
        ticker: Crypto ticker in Yahoo format
        period: Data period
        interval: Data interval
        auto_adjust: Whether to auto-adjust prices
        rate_limit_delay: Delay between downloads (seconds)
        max_retries: Maximum retry attempts per source
        verbose: Whether to print status messages

    Returns:
        DataFrame with OHLCV data, or empty DataFrame on failure
    """

    # Download with cascading fallbacks
    df = download_crypto_data(
        ticker=ticker,
        period=period,
        interval=interval,
        auto_adjust=auto_adjust,
        max_retries=max_retries,
        verbose=verbose
    )

    # Apply rate limiting delay
    if rate_limit_delay > 0:
        time.sleep(rate_limit_delay)

    return df


# Convenience functions

def download_crypto_daily(ticker: str, period: str = '1y') -> pd.DataFrame:
    """Download daily crypto data with cascading fallbacks."""
    return download_crypto_data(ticker, period=period, interval='1d')


def download_crypto_weekly(ticker: str, period: str = '2y') -> pd.DataFrame:
    """Download weekly crypto data with cascading fallbacks."""
    return download_crypto_data(ticker, period=period, interval='1wk')


def download_crypto_monthly(ticker: str, period: str = '5y') -> pd.DataFrame:
    """Download monthly crypto data with cascading fallbacks."""
    return download_crypto_data(ticker, period=period, interval='1mo')


if __name__ == "__main__":
    # Test the cascading fallback system
    logger.info("Testing Crypto Data Downloader with Cascading Fallbacks")
    logger.info("="*70)

    # Test 1: Major crypto (should work with Yahoo Finance)
    logger.info("\nTest 1: Major crypto - BTC-USD (should use Yahoo Finance)")
    df = download_crypto_data('BTC-USD', period='1mo', interval='1d')
    logger.info("  Result: %s - %d bars", 'Success' if not df.empty else 'Failed', len(df))

    # Test 2: Altcoin that might not be on Yahoo (will try Binance/CoinGecko)
    logger.info("\nTest 2: Altcoin - LINK-USD (may use Binance or CoinGecko)")
    df = download_crypto_data('LINK-USD', period='1mo', interval='1d')
    logger.info("  Result: %s - %d bars", 'Success' if not df.empty else 'Failed', len(df))

    # Test 3: Invalid crypto
    logger.info("\nTest 3: Invalid crypto - INVALID-USD (should fail all sources)")
    df = download_crypto_data('INVALID-USD', period='1mo', interval='1d', max_retries=1)
    logger.info("  Result: %s - %d bars", 'Success' if not df.empty else 'Failed', len(df))

    # Test 4: Multiple downloads with rate limiting
    logger.info("\nTest 4: Multiple downloads with rate limiting")
    cryptos = ['ETH-USD', 'SOL-USD', 'ADA-USD']
    for crypto in cryptos:
        df = download_crypto_with_rate_limit(crypto, period='1mo', rate_limit_delay=0.5, verbose=False)
        logger.info("  %s: %d bars", crypto, len(df))

    logger.info("\n" + "="*70)
    logger.info("Testing complete!")
