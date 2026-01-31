"""
Data Downloader with Retry Logic.

Provides robust data downloading from defeatbeta-api with yfinance fallback:
- Primary: defeatbeta-api (NO rate limiting, pre-downloaded from Hugging Face)
- Fallback: yfinance (for tickers not in defeatbeta-api, e.g., some ETFs)
- Error handling for common failures
- File-based caching to avoid duplicate downloads
- Much faster than yfinance when available!
"""

from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

try:
    from defeatbeta_api.data.ticker import Ticker
    DEFEATBETA_AVAILABLE = True
except ImportError:
    DEFEATBETA_AVAILABLE = False

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False

from data_cache import get_cache
from logging_config import get_logger

logger = get_logger(__name__)

# Get global cache instance
_cache = get_cache()


def _parse_period_to_days(period: str) -> int:
    """
    Convert yfinance-style period strings to number of days.

    Args:
        period: Period string (e.g., '1y', '5y', 'max', '3mo')

    Returns:
        Number of days as integer
    """
    period = period.lower().strip()

    # Handle common periods
    period_map = {
        'max': 365 * 100,  # 100 years (essentially all data)
    }

    if period in period_map:
        return period_map[period]

    if period.endswith('d'):
        return int(period[:-1])
    elif period.endswith('mo'):
        months = int(period[:-2])
        return months * 30  # Approximate
    elif period.endswith('y'):
        years = int(period[:-1])
        return years * 365
    elif period.endswith('wk'):
        weeks = int(period[:-2])
        return weeks * 7
    else:
        # Default to 1 year if can't parse
        logger.warning("Unknown period format '%s', defaulting to 1 year", period)
        return 365


def _normalize_yfinance_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize yfinance data to match defeatbeta-api format.

    Args:
        df: DataFrame from yfinance

    Returns:
        Normalized DataFrame with consistent format
    """
    if df.empty:
        return df

    # Remove timezone info from index for consistency
    if hasattr(df.index, 'tz') and df.index.tz is not None:
        df.index = df.index.tz_localize(None)

    # Keep only OHLCV columns (remove Dividends, Stock Splits, etc.)
    ohlcv_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
    available_columns = [col for col in ohlcv_columns if col in df.columns]
    df = df[available_columns].copy()

    return df


def _resample_to_interval(df: pd.DataFrame, interval: str) -> pd.DataFrame:
    """
    Resample daily data to the specified interval.

    Args:
        df: DataFrame with report_date and OHLCV columns
        interval: Target interval (e.g., '1d', '1wk', '1mo')

    Returns:
        Resampled DataFrame with Date, Open, High, Low, Close, Volume columns
    """
    if df.empty:
        return df

    # Ensure report_date is datetime
    if df['report_date'].dtype == 'object':
        df['report_date'] = pd.to_datetime(df['report_date'])

    # Set index to report_date for resampling
    df = df.set_index('report_date')

    interval = interval.lower().strip()

    # Map interval to pandas resample rule
    if interval in ('1d', 'd'):
        # Already daily, no resampling needed
        return df.reset_index()

    interval_map = {
        '1wk': 'W',
        'wk': 'W',
        '1mo': 'M',
        'mo': 'M',
        '3mo': 'Q',
    }

    if interval in interval_map:
        rule = interval_map[interval]
    elif interval in ('1h', '5m', '15m', '30m'):
        logger.warning("Intraday data not supported by defeatbeta-api, using daily instead")
        return df.reset_index()
    else:
        logger.warning("Unknown interval '%s', using daily data", interval)
        return df.reset_index()

    # Resample OHLCV data (maintain standard OHLCV order)
    resampled = pd.DataFrame({
        'open': df['open'].resample(rule).first(),
        'high': df['high'].resample(rule).max(),
        'low': df['low'].resample(rule).min(),
        'close': df['close'].resample(rule).last(),
        'volume': df['volume'].resample(rule).sum()
    })[['open', 'high', 'low', 'close', 'volume']]  # Explicit order

    # Remove rows with NaN (incomplete periods)
    resampled = resampled.dropna()

    # Reset index to get report_date back as column
    resampled = resampled.reset_index()

    # Capitalize column names to match yfinance format
    resampled.columns = [
        col.capitalize() if col != 'report_date' else 'Date'
        for col in resampled.columns
    ]

    # Rename Date to match expected format
    resampled.index.name = None

    return resampled


def download_stock_data(
    ticker: str,
    period: str = '1y',
    interval: str = '1d',
    auto_adjust: bool = False,
    max_retries: int = 1,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    use_cache: bool = True
) -> pd.DataFrame:
    """
    Download stock data using defeatbeta-api (Hugging Face hosted data).

    Args:
        ticker: Stock ticker symbol
        period: Data period (e.g., '1y', '5y', 'max')
        interval: Data interval (e.g., '1d', '1wk', '1mo')
        auto_adjust: Whether to auto-adjust prices for dividends (not used with defeatbeta-api)
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay before first retry (seconds)
        backoff_factor: Multiplier for exponential backoff
        use_cache: Whether to use file-based cache (default: True)

    Returns:
        DataFrame with OHLCV data (columns: Date, Open, High, Low, Close, Volume)
        Empty DataFrame on failure

    Benefits over yfinance:
        - NO rate limiting - data is pre-downloaded from Hugging Face
        - Much faster - no API calls needed
        - More reliable - no HTTP errors or timeouts
        - Hosted on Hugging Face infrastructure

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

    last_error: Optional[str] = None
    delay = initial_delay
    first_failure_logged = False

    # If defeatbeta-api is not available, use yfinance directly
    if not DEFEATBETA_AVAILABLE:
        if not YFINANCE_AVAILABLE:
            logger.error("%s: Neither defeatbeta-api nor yfinance available", ticker)
            return pd.DataFrame()

        logger.debug("%s: Using yfinance (defeatbeta-api not installed)", ticker)
        try:
            stock = yf.Ticker(ticker)
            df = stock.history(
                period=period,
                interval=interval,
                auto_adjust=auto_adjust,
                raise_errors=False
            )

            if not df.empty:
                # Normalize yfinance data to match defeatbeta-api format
                df = _normalize_yfinance_data(df)

                if use_cache:
                    _cache.set(ticker, period, interval, df)

            return df
        except Exception as e:
            logger.error("%s: Yfinance error: %s", ticker, str(e))
            return pd.DataFrame()

    for attempt in range(max_retries):
        try:
            # Download data from defeatbeta-api (Hugging Face)
            ticker_obj = Ticker(ticker)
            df = ticker_obj.price()

            # Check if download succeeded
            if not df.empty:
                # Convert report_date to datetime
                df['report_date'] = pd.to_datetime(df['report_date'])

                # Filter by period (get last N days)
                days = _parse_period_to_days(period)
                cutoff_date = datetime.now() - timedelta(days=days)
                df = df[df['report_date'] >= cutoff_date].copy()

                # Resample to requested interval if needed
                if interval != '1d':
                    df = _resample_to_interval(df, interval)
                else:
                    # Rename columns to match yfinance format for 1d
                    df = df.rename(columns={
                        'report_date': 'Date',
                        'open': 'Open',
                        'high': 'High',
                        'low': 'Low',
                        'close': 'Close',
                        'volume': 'Volume'
                    })

                    # Drop symbol column if it exists
                    if 'symbol' in df.columns:
                        df = df.drop(columns=['symbol'])

                # Set Date as index to match yfinance format
                if 'Date' in df.columns:
                    df = df.set_index('Date')
                elif 'report_date' in df.columns:
                    df = df.rename(columns={'report_date': 'Date'})
                    df = df.set_index('Date')

                # Reorder columns to standard OHLCV format (matches yfinance)
                standard_order = ['Open', 'High', 'Low', 'Close', 'Volume']
                available_cols = [col for col in standard_order if col in df.columns]
                df = df[available_cols]

                # SUCCESS
                if attempt > 0:
                    logger.info("%s: Retry succeeded (attempt %d)", ticker, attempt + 1)

                # Cache the successful download
                if use_cache:
                    _cache.set(ticker, period, interval, df)

                return df
            else:
                # Empty DataFrame
                last_error = f"No data returned for {ticker}"

        except Exception as e:
            # Handle any errors
            error_str = str(e)
            last_error = error_str

            # Check for specific errors that shouldn't be retried
            error_str_lower = error_str.lower()

            # Don't retry for these permanent errors
            if any(x in error_str_lower for x in ['invalid ticker', 'not found', 'no data']):
                if not first_failure_logged:
                    logger.warning("%s: Ticker not found or has no data", ticker)
                return pd.DataFrame()

        # If we get here, the download failed
        # Log first failure
        if not first_failure_logged:
            error_msg = str(last_error)[:50] + "..." if last_error and len(str(last_error)) > 50 else str(last_error)
            logger.warning("%s: Download failed - %s", ticker, error_msg)
            first_failure_logged = True

        # Retry if attempts remain
        if attempt < max_retries - 1:  # Don't sleep on last attempt
            logger.info(
                "%s: Retrying in %.1fs... (attempt %d/%d)",
                ticker, delay, attempt + 2, max_retries
            )
            import time
            time.sleep(delay)
            delay *= backoff_factor  # Exponential backoff

    # All defeatbeta-api retries exhausted - try yfinance fallback (single attempt, no retries)
    if YFINANCE_AVAILABLE:
        logger.info("%s: Falling back to yfinance (single attempt, no retries)", ticker)
        try:
            stock = yf.Ticker(ticker)
            df = stock.history(
                period=period,
                interval=interval,
                auto_adjust=auto_adjust,
                raise_errors=False
            )

            if not df.empty:
                logger.info("%s: Yfinance fallback succeeded", ticker)

                # Normalize yfinance data to match defeatbeta-api format
                df = _normalize_yfinance_data(df)

                # Cache the successful download
                if use_cache:
                    _cache.set(ticker, period, interval, df)

                return df
            else:
                logger.warning("%s: Yfinance fallback returned no data", ticker)
        except Exception as e:
            logger.warning("%s: Yfinance fallback error: %s", ticker, str(e))
    else:
        logger.error("%s: All %d defeatbeta-api attempts failed and yfinance not available", ticker, max_retries)

    return pd.DataFrame()


def download_with_rate_limit(
    ticker: str,
    period: str = '1y',
    interval: str = '1d',
    auto_adjust: bool = False,
    rate_limit_delay: float = 0.0,  # Default to 0 since no rate limits with defeatbeta-api
    max_retries: int = 3,
    use_cache: bool = True
) -> pd.DataFrame:
    """
    Download stock data with built-in rate limiting and retry logic.

    Note: With defeatbeta-api, rate limiting is not needed since data is
    pre-downloaded from Hugging Face. This function is kept for compatibility.

    Args:
        ticker: Stock ticker symbol
        period: Data period (e.g., '1y', '5y', 'max')
        interval: Data interval (e.g., '1d', '1wk', '1mo')
        auto_adjust: Whether to auto-adjust prices for dividends (not used)
        rate_limit_delay: Delay between downloads (seconds) - default 0 for defeatbeta-api
        max_retries: Maximum number of retry attempts
        use_cache: Whether to use file-based cache (default: True)

    Returns:
        DataFrame with OHLCV data, or empty DataFrame on failure

    Example:
        >>> # Download without delay (defeatbeta-api doesn't need rate limiting)
        >>> df = download_with_rate_limit('AAPL', period='1y')
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

    # Apply rate limiting delay (if specified, though not needed for defeatbeta-api)
    if rate_limit_delay > 0:
        import time
        time.sleep(rate_limit_delay)

    return df


# Convenience functions for common use cases

def download_daily_data(ticker: str, period: str = '1y') -> pd.DataFrame:
    """
    Download daily data with retry logic.

    Args:
        ticker: Stock ticker symbol
        period: Data period (default: '1y')

    Returns:
        DataFrame with daily OHLCV data
    """
    return download_stock_data(ticker, period=period, interval='1d')


def download_weekly_data(ticker: str, period: str = '2y') -> pd.DataFrame:
    """
    Download weekly data with retry logic.

    Args:
        ticker: Stock ticker symbol
        period: Data period (default: '2y')

    Returns:
        DataFrame with weekly OHLCV data
    """
    return download_stock_data(ticker, period=period, interval='1wk')


def download_monthly_data(ticker: str, period: str = '5y') -> pd.DataFrame:
    """
    Download monthly data with retry logic.

    Args:
        ticker: Stock ticker symbol
        period: Data period (default: '5y')

    Returns:
        DataFrame with monthly OHLCV data
    """
    return download_stock_data(ticker, period=period, interval='1mo')


if __name__ == "__main__":
    # Test the defeatbeta-api integration
    logger.info("Testing Data Downloader with defeatbeta-api (Hugging Face)")
    logger.info("=" * 60)

    # Test 1: Valid ticker
    logger.info("\nTest 1: Valid ticker (AAPL)")
    df = download_stock_data('AAPL', period='1mo', interval='1d')
    logger.info("  Result: %s - %d bars", 'Success' if not df.empty else 'Failed', len(df))
    if not df.empty:
        logger.info("  Date range: %s to %s", df.index[0], df.index[-1])
        logger.info("  Columns: %s", df.columns.tolist())

    # Test 2: Invalid ticker (should fail gracefully)
    logger.info("\nTest 2: Invalid ticker (INVALID123)")
    df = download_stock_data('INVALID123', period='1mo', interval='1d')
    logger.info("  Result: %s - %d bars", 'Success' if not df.empty else 'Failed', len(df))

    # Test 3: Multiple downloads (no rate limiting needed!)
    logger.info("\nTest 3: Multiple downloads (NO rate limiting needed with defeatbeta-api)")
    tickers = ['MSFT', 'GOOGL', 'TSLA']
    for ticker in tickers:
        df = download_with_rate_limit(ticker, period='1mo', rate_limit_delay=0.0)
        logger.info("  %s: %d bars", ticker, len(df))

    # Test 4: Weekly data
    logger.info("\nTest 4: Weekly data (1 year)")
    df = download_stock_data('AAPL', period='1y', interval='1wk')
    logger.info("  Result: %s - %d bars", 'Success' if not df.empty else 'Failed', len(df))
    if not df.empty:
        logger.info("  Date range: %s to %s", df.index[0], df.index[-1])

    logger.info("\n" + "=" * 60)
    logger.info("Testing complete!")
