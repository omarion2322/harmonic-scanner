"""
Data Downloader with Retry Logic

Provides robust data downloading from yfinance with:
- Exponential backoff retry mechanism
- Rate limiting protection
- Error handling for common failures
"""

import yfinance as yf
import pandas as pd
import time
from typing import Optional


def download_stock_data(
    ticker: str,
    period: str = '1y',
    interval: str = '1d',
    auto_adjust: bool = False,
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0
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

    Returns:
        DataFrame with OHLCV data, or empty DataFrame on failure

    Retry Strategy:
        - Attempt 1: Immediate
        - Attempt 2: Wait 1.0s (initial_delay)
        - Attempt 3: Wait 2.0s (initial_delay * backoff_factor)
        - Attempt 4: Wait 4.0s (initial_delay * backoff_factor^2)

    Logging:
        - Shows message on first failure
        - Shows message if retry succeeds
        - Shows message if all retries fail

    Example:
        >>> df = download_stock_data('AAPL', period='1y', interval='1wk')
        >>> if not df.empty:
        ...     print(f"Downloaded {len(df)} bars")
    """

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
                auto_adjust=auto_adjust
            )

            # Check if download succeeded
            if not df.empty:
                # SUCCESS
                if attempt > 0:
                    # Retry succeeded - log it
                    print(f"${ticker}: ✓ Retry succeeded (attempt {attempt + 1})")
                return df
            else:
                # Empty DataFrame - stock might not exist or have no data
                last_error = f"No data returned"

        except Exception as e:
            last_error = str(e)

            # Check for specific errors that shouldn't be retried
            error_str = str(e).lower()

            # Don't retry for these permanent errors
            if any(x in error_str for x in [
                'invalid ticker',
                'no timezone found',
                'delisted',
                'not found'
            ]):
                return pd.DataFrame()

        # If we get here, the download failed
        # Log first failure
        if not first_failure_logged:
            error_msg = str(last_error)[:50] + "..." if len(str(last_error)) > 50 else str(last_error)
            print(f"${ticker}: ⚠ Download failed - {error_msg}")
            first_failure_logged = True

        # Retry if attempts remain
        if attempt < max_retries - 1:  # Don't sleep on last attempt
            print(f"${ticker}: ⟳ Retrying in {delay:.1f}s... (attempt {attempt + 2}/{max_retries})")
            time.sleep(delay)
            delay *= backoff_factor  # Exponential backoff

    # All retries exhausted
    print(f"${ticker}: ✗ All {max_retries} attempts failed")
    return pd.DataFrame()


def download_with_rate_limit(
    ticker: str,
    period: str = '1y',
    interval: str = '1d',
    auto_adjust: bool = False,
    rate_limit_delay: float = 0.1,
    max_retries: int = 3
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

    Returns:
        DataFrame with OHLCV data, or empty DataFrame on failure

    Example:
        >>> # Download with 0.2s delay between requests
        >>> df = download_with_rate_limit('AAPL', period='1y', rate_limit_delay=0.2)
    """

    # Download with retries
    df = download_stock_data(
        ticker=ticker,
        period=period,
        interval=interval,
        auto_adjust=auto_adjust,
        max_retries=max_retries
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
    print("Testing Data Downloader with Retry Logic")
    print("="*60)

    # Test 1: Valid ticker
    print("\nTest 1: Valid ticker (AAPL)")
    df = download_stock_data('AAPL', period='1mo', interval='1d')
    print(f"  Result: {'Success' if not df.empty else 'Failed'} - {len(df)} bars")

    # Test 2: Invalid ticker (should fail gracefully)
    print("\nTest 2: Invalid ticker (INVALID123)")
    df = download_stock_data('INVALID123', period='1mo', interval='1d')
    print(f"  Result: {'Success' if not df.empty else 'Failed'} - {len(df)} bars")

    # Test 3: With rate limiting
    print("\nTest 3: Multiple downloads with rate limiting")
    tickers = ['MSFT', 'GOOGL', 'TSLA']
    for ticker in tickers:
        df = download_with_rate_limit(ticker, period='1mo', rate_limit_delay=0.2)
        print(f"  {ticker}: {len(df)} bars")

    print("\n" + "="*60)
    print("Testing complete!")
