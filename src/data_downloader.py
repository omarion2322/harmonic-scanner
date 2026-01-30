"""
Data Downloader with Retry Logic

Provides robust data downloading from yfinance with:
- Exponential backoff retry mechanism
- Rate limiting protection
- Error handling for common failures
- File-based caching to avoid duplicate downloads
"""

import yfinance as yf
import pandas as pd
import time
from typing import Optional
from logging_config import get_logger
from data_cache import get_cache

logger = get_logger(__name__)

# Get global cache instance
_cache = get_cache()


def download_stock_data(
    ticker: str,
    period: str = '1y',
    interval: str = '1d',
    auto_adjust: bool = False,
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    use_cache: bool = True
) -> pd.DataFrame:
    """
    Download stock data with retry logic and exponential backoff.

    Args:
        ticker: Stock ticker symbol
        period: Data period (e.g., '1y', '5y', 'max')
        interval: Data interval (e.g., '1d', '1wk', '1mo')
        auto_adjust: Whether to auto-adjust prices for dividends
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay before first retry (seconds)
        backoff_factor: Multiplier for exponential backoff
        use_cache: Whether to use file-based cache (default: True)

    Returns:
        DataFrame with OHLCV data, or empty DataFrame on failure

    Retry Strategy:
        - Attempt 1: Immediate
        - Attempt 2: Wait 1.0s (initial_delay)
        - Attempt 3: Wait 2.0s (initial_delay * backoff_factor)
        - Attempt 4: Wait 4.0s (initial_delay * backoff_factor^2)

    Caching:
        - Checks cache before downloading (8-hour TTL)
        - Saves successful downloads to cache
        - Avoids duplicate API calls within same session

    Logging:
        - Shows message on first failure
        - Shows message if retry succeeds
        - Shows message if all retries fail

    Example:
        >>> df = download_stock_data('AAPL', period='1y', interval='1wk')
        >>> if not df.empty:
        ...     print(f"Downloaded {len(df)} bars")
    """

    # Check cache first
    if use_cache:
        cached_data = _cache.get(ticker, period, interval)
        if cached_data is not None:
            return cached_data

    last_error = None
    delay = initial_delay
    first_failure_logged = False

    for attempt in range(max_retries):
        try:
            # Attempt download
            stock = yf.Ticker(ticker)
            df = stock.history(
                period=period,
                interval=interval,
                auto_adjust=auto_adjust,
                raise_errors=False  # Don't raise exceptions for warnings (e.g., dividend metadata issues)
            )

            # Check if download succeeded
            if not df.empty:
                # SUCCESS
                if attempt > 0:
                    # Retry succeeded - log it
                    logger.info("%s: Retry succeeded (attempt %d)", ticker, attempt + 1)

                # Cache the successful download
                if use_cache:
                    _cache.set(ticker, period, interval, df)

                return df
            else:
                # Empty DataFrame - stock might not exist or have no data
                last_error = f"No data returned (DataFrame is empty but no exception raised)"

        except (ValueError, KeyError, OSError) as e:
            # Common yfinance errors: ValueError (invalid params), KeyError (missing data), OSError (network)
            error_str = str(e)

            # Handle yfinance dividend metadata errors gracefully
        except Exception as e:
            # Catch-all for unexpected errors
            error_str = str(e)
            # These errors occur when dividend dates don't align with the requested interval
            # but don't actually prevent price data from being downloaded
            # Example: "The following 'Dividends' events are out-of-range..."
            if 'dividends' in error_str.lower() and 'out-of-range' in error_str.lower():
                # This is a yfinance bug with certain period/interval combinations
                # Try alternative periods that avoid the problematic dividend dates
                fallback_periods = []

                # Determine fallback periods based on requested period
                if period in ['5y', 'max']:
                    fallback_periods = ['2y', '3y', '1y']
                elif period == '2y':
                    fallback_periods = ['1y', '18mo']
                elif period == '1y':
                    fallback_periods = ['6mo', '1y']

                # Try fallback periods
                for fallback_period in fallback_periods:
                    try:
                        stock = yf.Ticker(ticker)
                        df = stock.history(
                            period=fallback_period,
                            interval=interval,
                            auto_adjust=auto_adjust,
                            raise_errors=False
                        )
                        if not df.empty:
                            if first_failure_logged:
                                logger.info("%s: Dividend error bypassed using period=%s", ticker, fallback_period)

                            # Cache the successful fallback download
                            if use_cache:
                                _cache.set(ticker, fallback_period, interval, df)

                            return df
                    except Exception:
                        continue  # Try next fallback period

                # If all fallbacks failed, continue to retry logic

            last_error = error_str

            # Check for specific errors that shouldn't be retried
            error_str_lower = error_str.lower()

            # Don't retry for these permanent errors
            # Note: "delisted" and "not found" are NOT in this list because yfinance
            # sometimes incorrectly reports these errors for valid tickers
            if any(x in error_str_lower for x in [
                'invalid ticker',
                'no timezone found'
            ]):
                return pd.DataFrame()

        # If we get here, the download failed
        # Log first failure
        if not first_failure_logged:
            error_msg = str(last_error)[:50] + "..." if len(str(last_error)) > 50 else str(last_error)
            logger.warning("%s: Download failed - %s", ticker, error_msg)
            first_failure_logged = True

        # Retry if attempts remain
        if attempt < max_retries - 1:  # Don't sleep on last attempt
            logger.info("%s: Retrying in %.1fs... (attempt %d/%d)", ticker, delay, attempt + 2, max_retries)
            time.sleep(delay)
            delay *= backoff_factor  # Exponential backoff

    # All retries exhausted
    logger.error("%s: All %d attempts failed", ticker, max_retries)
    return pd.DataFrame()


def download_with_rate_limit(
    ticker: str,
    period: str = '1y',
    interval: str = '1d',
    auto_adjust: bool = False,
    rate_limit_delay: float = 0.1,
    max_retries: int = 3,
    use_cache: bool = True
) -> pd.DataFrame:
    """
    Download stock data with built-in rate limiting and retry logic.

    This combines exponential backoff retries with a consistent delay
    between downloads to avoid overwhelming the API.

    Args:
        ticker: Stock ticker symbol
        period: Data period (e.g., '1y', '5y', 'max')
        interval: Data interval (e.g., '1d', '1wk', '1mo')
        auto_adjust: Whether to auto-adjust prices for dividends
        rate_limit_delay: Delay between downloads (seconds)
        max_retries: Maximum number of retry attempts
        use_cache: Whether to use file-based cache (default: True)

    Returns:
        DataFrame with OHLCV data, or empty DataFrame on failure

    Example:
        >>> # Download with 0.2s delay between requests
        >>> df = download_with_rate_limit('AAPL', period='1y', rate_limit_delay=0.2)
    """

    # Download with retries (and caching)
    df = download_stock_data(
        ticker=ticker,
        period=period,
        interval=interval,
        auto_adjust=auto_adjust,
        max_retries=max_retries,
        use_cache=use_cache
    )

    # Apply rate limiting delay
    if rate_limit_delay > 0:
        time.sleep(rate_limit_delay)

    return df


# Convenience functions for common use cases

def download_daily_data(ticker: str, period: str = '1y') -> pd.DataFrame:
    """Download daily data with retry logic."""
    return download_stock_data(ticker, period=period, interval='1d')


def download_weekly_data(ticker: str, period: str = '2y') -> pd.DataFrame:
    """Download weekly data with retry logic."""
    return download_stock_data(ticker, period=period, interval='1wk')


def download_monthly_data(ticker: str, period: str = '5y') -> pd.DataFrame:
    """Download monthly data with retry logic."""
    return download_stock_data(ticker, period=period, interval='1mo')


if __name__ == "__main__":
    # Test the retry mechanism
    logger.info("Testing Data Downloader with Retry Logic")
    logger.info("="*60)

    # Test 1: Valid ticker
    logger.info("\nTest 1: Valid ticker (AAPL)")
    df = download_stock_data('AAPL', period='1mo', interval='1d')
    logger.info("  Result: %s - %d bars", 'Success' if not df.empty else 'Failed', len(df))

    # Test 2: Invalid ticker (should fail gracefully)
    logger.info("\nTest 2: Invalid ticker (INVALID123)")
    df = download_stock_data('INVALID123', period='1mo', interval='1d')
    logger.info("  Result: %s - %d bars", 'Success' if not df.empty else 'Failed', len(df))

    # Test 3: With rate limiting
    logger.info("\nTest 3: Multiple downloads with rate limiting")
    tickers = ['MSFT', 'GOOGL', 'TSLA']
    for ticker in tickers:
        df = download_with_rate_limit(ticker, period='1mo', rate_limit_delay=0.2)
        logger.info("  %s: %d bars", ticker, len(df))

    logger.info("\n" + "="*60)
    logger.info("Testing complete!")
