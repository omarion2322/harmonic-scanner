"""
Data Cache Module

Provides file-based caching for yfinance data downloads to avoid duplicate API calls.
Works in both local and GitHub Actions environments.

Cache Features:
- File-based storage using Parquet format (fast I/O)
- 8-hour TTL for data freshness
- Automatic expiration cleanup
- Thread-safe (file system handles locking)
- Works across multiple processes
"""

import pandas as pd
from pathlib import Path
from datetime import datetime

try:
    from logging_config import get_logger
except ModuleNotFoundError:
    from src.logging_config import get_logger

logger = get_logger(__name__)


class DataCache:
    """File-based cache for yfinance data downloads."""

    def __init__(self, cache_dir='.cache/yfinance_data', ttl_hours=8):
        """
        Initialize data cache.

        Args:
            cache_dir: Directory for cache files (default: .cache/yfinance_data)
            ttl_hours: Time-to-live in hours (default: 8 hours)
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_hours = ttl_hours
        self._cleanup_on_init()

    def _cleanup_on_init(self):
        """Clean up expired cache files on initialization."""
        try:
            self.clear_expired()
        except Exception as e:
            logger.warning("Failed to cleanup cache on init: %s", e)

    def _get_cache_key(self, ticker, period, interval):
        """
        Generate cache filename.

        Format: TICKER_INTERVAL_PERIOD_TIMESTAMP.parquet
        Example: AAPL_1d_1y_20260130_140532.parquet
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        # Use timestamp in filename for easy age checking
        return f"{ticker}_{interval}_{period}_{timestamp}.parquet"

    def _find_cache_file(self, ticker, period, interval):
        """
        Find the most recent cache file for given parameters.

        Returns:
            Path to cache file if found and fresh, None otherwise
        """
        pattern = f"{ticker}_{interval}_{period}_*.parquet"
        cache_files = sorted(self.cache_dir.glob(pattern), key=lambda f: f.stat().st_mtime, reverse=True)

        if not cache_files:
            return None

        # Get most recent file
        latest_file = cache_files[0]

        # Check if it's still fresh
        file_age_hours = (datetime.now().timestamp() - latest_file.stat().st_mtime) / 3600

        if file_age_hours < self.ttl_hours:
            return latest_file

        return None

    def get(self, ticker, period, interval):
        """
        Get cached data if available and fresh.

        Args:
            ticker: Stock ticker symbol
            period: Data period (e.g., '1y', '5y')
            interval: Data interval (e.g., '1d', '1wk')

        Returns:
            DataFrame with cached data, or None if not cached/expired
        """
        try:
            cache_file = self._find_cache_file(ticker, period, interval)

            if cache_file and cache_file.exists():
                df = pd.read_parquet(cache_file)

                if not df.empty:
                    file_age_minutes = (datetime.now().timestamp() - cache_file.stat().st_mtime) / 60
                    logger.debug("%s: Cache hit (age: %.1f min)", ticker, file_age_minutes)
                    return df

        except Exception as e:
            logger.warning("%s: Failed to read cache: %s", ticker, e)
            # If cache file is corrupted, try to delete it
            try:
                if cache_file and cache_file.exists():
                    cache_file.unlink()
            except:
                pass

        return None

    def set(self, ticker, period, interval, data: pd.DataFrame):
        """
        Save data to cache.

        Args:
            ticker: Stock ticker symbol
            period: Data period (e.g., '1y', '5y')
            interval: Data interval (e.g., '1d', '1wk')
            data: DataFrame to cache
        """
        if data.empty:
            return

        try:
            cache_file = self.cache_dir / self._get_cache_key(ticker, period, interval)
            data.to_parquet(cache_file, compression='snappy')
            logger.debug("%s: Cached data (%d bars)", ticker, len(data))

            # Clean up old cache files for this ticker/period/interval
            self._cleanup_old_versions(ticker, period, interval)

        except Exception as e:
            logger.warning("%s: Failed to cache data: %s", ticker, e)

    def _cleanup_old_versions(self, ticker, period, interval):
        """Remove old cache files for the same ticker/period/interval."""
        try:
            pattern = f"{ticker}_{interval}_{period}_*.parquet"
            cache_files = sorted(self.cache_dir.glob(pattern), key=lambda f: f.stat().st_mtime, reverse=True)

            # Keep only the most recent file, delete the rest
            for old_file in cache_files[1:]:
                old_file.unlink()

        except Exception as e:
            logger.debug("Failed to cleanup old versions: %s", e)

    def clear_expired(self):
        """Remove expired cache files."""
        try:
            cutoff_time = datetime.now().timestamp() - (self.ttl_hours * 3600)
            deleted_count = 0

            for cache_file in self.cache_dir.glob('*.parquet'):
                if cache_file.stat().st_mtime < cutoff_time:
                    cache_file.unlink()
                    deleted_count += 1

            if deleted_count > 0:
                logger.info("Cleaned up %d expired cache files", deleted_count)

        except Exception as e:
            logger.warning("Failed to clear expired cache: %s", e)

    def clear_all(self):
        """Remove all cache files."""
        try:
            deleted_count = 0
            for cache_file in self.cache_dir.glob('*.parquet'):
                cache_file.unlink()
                deleted_count += 1

            logger.info("Cleared all cache (%d files)", deleted_count)

        except Exception as e:
            logger.warning("Failed to clear cache: %s", e)

    def get_stats(self):
        """
        Get cache statistics.

        Returns:
            Dict with cache stats (file count, total size, location)
        """
        try:
            files = list(self.cache_dir.glob('*.parquet'))
            total_size = sum(f.stat().st_size for f in files)

            # Count fresh vs expired
            cutoff_time = datetime.now().timestamp() - (self.ttl_hours * 3600)
            fresh_count = sum(1 for f in files if f.stat().st_mtime >= cutoff_time)
            expired_count = len(files) - fresh_count

            return {
                'total_files': len(files),
                'fresh_files': fresh_count,
                'expired_files': expired_count,
                'total_size_mb': round(total_size / (1024 * 1024), 2),
                'location': str(self.cache_dir.absolute()),
                'ttl_hours': self.ttl_hours
            }
        except Exception as e:
            logger.warning("Failed to get cache stats: %s", e)
            return {
                'total_files': 0,
                'fresh_files': 0,
                'expired_files': 0,
                'total_size_mb': 0,
                'location': str(self.cache_dir.absolute()),
                'ttl_hours': self.ttl_hours
            }


# Global cache instance (8-hour TTL)
_global_cache = DataCache(cache_dir='.cache/yfinance_data', ttl_hours=8)


def get_cache():
    """Get the global cache instance."""
    return _global_cache


if __name__ == "__main__":
    # Test the cache
    logger.info("Testing Data Cache")
    logger.info("=" * 60)

    cache = DataCache(cache_dir='.cache/test_cache', ttl_hours=8)

    # Test stats
    stats = cache.get_stats()
    logger.info("Cache stats: %s", stats)

    # Test cache operations
    import yfinance as yf

    logger.info("\nTest 1: Cache miss (should download)")
    data = cache.get('AAPL', '1mo', '1d')
    if data is None:
        logger.info("  Cache miss - downloading...")
        stock = yf.Ticker('AAPL')
        data = stock.history(period='1mo', interval='1d')
        cache.set('AAPL', '1mo', '1d', data)
        logger.info("  Downloaded and cached %d bars", len(data))

    logger.info("\nTest 2: Cache hit (should use cache)")
    data = cache.get('AAPL', '1mo', '1d')
    if data is not None:
        logger.info("  Cache hit! Retrieved %d bars", len(data))

    # Final stats
    stats = cache.get_stats()
    logger.info("\nFinal cache stats:")
    logger.info("  Files: %d (fresh: %d, expired: %d)",
                stats['total_files'], stats['fresh_files'], stats['expired_files'])
    logger.info("  Size: %.2f MB", stats['total_size_mb'])
    logger.info("  Location: %s", stats['location'])

    # Cleanup test cache
    import shutil
    shutil.rmtree('.cache/test_cache', ignore_errors=True)
    logger.info("\nTest cache cleaned up")
    logger.info("=" * 60)
