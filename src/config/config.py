"""
Configuration File for Harmonic Pattern Trading System

Edit these settings to customize the scanner behavior without modifying the main code.
"""

# ============================================================================
# TIMEFRAME SELECTION (PRIMARY SETTING)
# ============================================================================

# Choose your trading timeframe - this will automatically load optimized settings
# Options: '1d' (daily), '3d' (3-day), '1wk' (weekly), '1mo' (monthly)
DATA_INTERVAL = '1wk'

# Import timeframe-specific optimized configurations
from .config_timeframes import get_timeframe_config

# Load optimized settings for selected timeframe
_TIMEFRAME_CONFIG = get_timeframe_config(DATA_INTERVAL)

# ============================================================================
# PATTERN DETECTION SETTINGS (Auto-loaded from timeframe config)
# ============================================================================

# These values are automatically set based on DATA_INTERVAL above
# You can override them manually if needed, but the defaults are optimized

# Fibonacci tolerance for pyharmonics (only when USE_PYHARMONICS_HARMONIC_SEARCH = True)
# Controls pattern matching precision: 0.03 = 3% tolerance, 0.05 = 5% (more lenient)
PYHARMONICS_FIB_TOLERANCE = 0.03

# Swing point detection window (higher = less sensitive, fewer patterns)
# Relevant only if using custom detection algorithm (USE_PYHARMONICS_HARMONIC_SEARCH = False)
SWING_WINDOW = _TIMEFRAME_CONFIG['SWING_WINDOW']

# Maximum days since pattern completion to generate BUY/SELL signal
# Relevant only if using custom detection algorithm (USE_PYHARMONICS_HARMONIC_SEARCH = False)
MAX_DAYS_SINCE_PATTERN = _TIMEFRAME_CONFIG['MAX_DAYS_SINCE_PATTERN']


# ============================================================================
# PATTERN DURATION FILTERS
# ============================================================================

# Reject patterns with unrealistic timeframes (e.g., 24-year patterns spanning multiple market cycles)
# Filters out invalid patterns like SHEN (1999-2023) or RANI (multi-year CD legs)

# Maximum ratio of CD duration to XA duration (CD can't be more than Nx longer than XA)
MAX_CD_TO_XA_TIME_RATIO = 5.0

# Maximum ratio of CD duration to AB duration
MAX_CD_TO_AB_TIME_RATIO = 10.0

# Maximum ratio of CD duration to BC duration
MAX_CD_TO_BC_TIME_RATIO = 8.0

# Maximum ratio of CD duration to combined XABC duration
MAX_CD_TO_XABC_TIME_RATIO = 4.0  # Relaxed from 3.0 to allow valid extended CD legs

# Maximum total pattern duration (X to D) in days
# Weekly: 7 years max (relaxed from 5), Daily: 2 years max, Monthly: 10 years max
MAX_TOTAL_PATTERN_DURATION_DAYS = 2555  # 7 years for weekly timeframe

# Maximum individual leg duration in days (prevents 19-year XA legs!)
# No single leg should span more than this
MAX_INDIVIDUAL_LEG_DURATION_DAYS = 1460  # 4 years max (relaxed from 3 years)

# Enable/disable pattern duration filters (set to False to allow patterns of any length)
ENABLE_TEMPORAL_VALIDATION = True

# ============================================================================
# DATA SETTINGS (Auto-loaded from timeframe config)
# ============================================================================

# Historical data period to analyze
DATA_PERIOD = _TIMEFRAME_CONFIG['DATA_PERIOD']

# Minimum bars required for pattern detection
# Harmonic patterns need sufficient history to identify valid XABCD points
# 50 bars = ~1 year for weekly, ~2.5 months for daily
# Reduce this to scan newer tickers (e.g., 30 bars), but may reduce pattern quality
MIN_BARS_REQUIRED = 30

# Deprecated: Use CRYPTOS_TO_SCAN instead (see line 109)
# CRYPTO_TICKERS = ['BTC-USD', 'ETH-USD', 'LTC-USD', 'XRP-USD']

# ============================================================================
# SCANNING SETTINGS
# ============================================================================

# Stock universe to scan
# Options:
#   'All'   - Scan all Nasdaq stocks with avg daily volume > MIN_VOLUME_USD
#   'SP500' - Scan S&P 500 stocks
#   'None'  - Don't scan any stocks (ETFs only)
STOCKS_TO_SCAN = 'All'

# Add additional stock tickers to scan (beyond S&P 500)
# Example: ['TSLA', 'NVDA']
STOCK_TICKERS = ['SSNC','HUT','AVGO','LAES','ONDS', 'RIVN', 'TIC', 'IQ', 'PANW', 'DOCU', 'LAC', 'URA', 'FRSH', 'EVEX', 'SSYS','BULL','TGT','CROX', 'CLSK', 'TEAM','REMX','SNDK','RGTI']

# ETF universe to scan
# Set to True to include all leading ETFs (135 total), False to skip ETFs
SCAN_ETFS = True

# Commodity universe to scan
# Set to True to include major commodity futures, False to skip commodities
SCAN_COMMODITIES = True

CRYPTOS_TO_SCAN = 'Top500'  # Options: 'Top100', 'Top50', 'Top20', or None

# Volume filtering mode (applies to 'All' Nasdaq mode only)
# If True: Filter by share volume (MIN_VOLUME_STOCKS)
# If False: Filter by dollar volume (MIN_VOLUME_USD)
FILTER_BY_STOCK_VOLUME = False

# Minimum average daily DOLLAR volume (used when FILTER_BY_STOCK_VOLUME = False)
# Filters stocks to ensure liquidity for harmonic pattern trading
# Default: $1,000,000 USD average daily dollar volume (price × shares)
MIN_VOLUME_USD = 1_000_000

# Minimum average daily SHARE volume (used when FILTER_BY_STOCK_VOLUME = True)
# Filters stocks by number of shares traded, regardless of price
# Default: 1,000,000 shares average daily volume
MIN_VOLUME_STOCKS = 1_000_000

# Maximum number of stocks to scan (None = all from selected universe)
# Use a smaller number for testing (e.g., 50)
MAX_STOCKS_TO_SCAN = 10000

# Add delay between stock downloads to avoid rate limiting
# Yahoo Finance limit: 60 requests per minute (1 request per second)
# With parallel workers: total_rate = workers / delay
# Formula: delay = workers / 60 requests_per_min = workers / 1 request_per_sec
# Example: 10 workers with 10s delay = 60 requests/min (at the limit)
DOWNLOAD_DELAY = 0.1

# Maximum number of retry attempts for failed downloads
# Uses exponential backoff: 1s, 2s, 4s delays between retries
# Recommended: 3 retries (handles temporary network issues and rate limits)
MAX_DOWNLOAD_RETRIES = 3

# Parallel processing settings
# Number of parallel workers for scanning tickers
# Yahoo Finance rate limit: 60 requests/min
# To stay under limit: workers × (60 / DOWNLOAD_DELAY) <= 60
# With DOWNLOAD_DELAY=10.0: 10 workers = 60 req/min (optimal)
PARALLEL_WORKERS = 10

# Enable/disable parallel processing
# When True, scan multiple tickers concurrently using ThreadPoolExecutor
# When False, scan tickers sequentially (slower but uses less resources)
ENABLE_PARALLEL_PROCESSING = True

# Parallel processing mode
# 'thread' - Use ThreadPoolExecutor (I/O-bound tasks like downloads, shares memory)
# 'process' - Use ProcessPoolExecutor (bypasses GIL for CPU-bound tasks)
# Recommended: 'thread' - downloads are I/O-bound, avoids rate limit issues
PARALLEL_MODE = 'thread'


# ============================================================================
# CONFIRMATION SETTINGS (for future enhancements)
# ============================================================================

# Require RSI confirmation (if implemented)
REQUIRE_RSI_CONFIRMATION = False

# RSI thresholds for buy/sell
RSI_OVERSOLD = 30    # Buy signal confirmation
RSI_OVERBOUGHT = 70  # Sell signal confirmation

# Require volume confirmation
REQUIRE_VOLUME_CONFIRMATION = False

# Volume must be X times average
VOLUME_MULTIPLIER = 1.5

# ============================================================================
# REPORTING SETTINGS
# ============================================================================


# Include stocks with HOLD signals in report
# When True: Shows up to 50 HOLD signals with reasons
# When False: Only counts HOLD signals in summary
# Note: HOLD reasons are always generated in verbose mode
INCLUDE_HOLD_IN_REPORT = False

# Verbose mode: Generate detailed asset-specific explanations
# When True, reports include detailed analysis for each stock explaining
# why it received a BUY/SELL/HOLD signal with pattern-specific details
VERBOSE_REPORTS = False

# Maximum number of maturing patterns to display in "MONITORING - PATTERNS MATURING" section
# Shows the X patterns closest to completion (highest completion percentage)
# Set to a higher value if you want to see more patterns (e.g., 50, 100, 200)
# Set to None to show all maturing patterns
MAX_MATURING_PATTERNS_DISPLAY_IN_REPORT = 50

# ============================================================================
# ADVANCED SETTINGS
# ============================================================================

# Automatically generate pattern chart visualizations
# When True, creates PNG charts ONLY for BUY/SELL signals (not HOLD)
# Charts are saved to reports/<date>/charts/ directory
# HOLD patterns are logged in reports without charts to save resources
AUTO_SAVE_CHARTS = True

# Chart save directory (deprecated - charts now saved in reports/<date>/charts/)
CHART_SAVE_DIR = './charts'


# ============================================================================
# RISK MANAGEMENT SETTINGS (Auto-loaded from timeframe config)
# ============================================================================

MIN_ALLOWED_STOP_LOSS_PCT = _TIMEFRAME_CONFIG['MIN_ALLOWED_STOP_LOSS_PCT']

MAX_ALLOWED_STOP_LOSS_PCT = _TIMEFRAME_CONFIG['MAX_ALLOWED_STOP_LOSS_PCT']

# Separate R/R filters for LONG (BUY) and SHORT (SELL) trades
# LONG trades typically have higher R/R potential due to unlimited upside
# SHORT trades have lower R/R due to limited downside (price can't go below 0)
MIN_LONG_RISK_REWARD_RATIO = _TIMEFRAME_CONFIG['MIN_LONG_RISK_REWARD_RATIO']
MIN_SHORT_RISK_REWARD_RATIO = _TIMEFRAME_CONFIG['MIN_SHORT_RISK_REWARD_RATIO']

# Deprecated: Use MIN_LONG_RISK_REWARD_RATIO or MIN_SHORT_RISK_REWARD_RATIO instead
MIN_RISK_REWARD_RATIO = MIN_LONG_RISK_REWARD_RATIO  # Backward compatibility

# Maximum pattern age to include in signals (in days)
# Filters out very old patterns that may no longer be relevant for trading
# Long-term harmonic patterns should still be recent enough to be actionable
# Default: 730 days (2 years) - focuses on patterns with recent market structure
MAX_PATTERN_AGE_DAYS = 1850

# ============================================================================
# POSITION SIZING SETTINGS
# ============================================================================
# Position sizing for partial exits at T1, T2, T3
# These percentages must sum to 1.0 (100%)
# Based on deep dive analysis showing:
#   - T1 hitting 66.7% of LONG trades (take more profit early)
#   - T2 hitting 40.7% of LONG trades (median move)
#   - T3 hitting 27.8% of LONG trades (reduced allocation)

POSITION_SIZE_T1 = 0.20  # 20% exit at Target 1
POSITION_SIZE_T2 = 0.30  # 30% exit at Target 2
POSITION_SIZE_T3 = 0.50  # 50% exit at Target 3

# Verify position sizing sums to 100%
assert abs(POSITION_SIZE_T1 + POSITION_SIZE_T2 + POSITION_SIZE_T3 - 1.0) < 0.001, \
    "Position sizing must sum to 100%"

# ============================================================================
# TAKE PROFIT STRATEGY SETTINGS
# ============================================================================

# Take Profit Strategy Selection
# Options:
#   'SCOTT' - Scott Carney's Fibonacci-based approach
#             Uses 38.2% and 61.8% retracement levels for intermediate targets
#             Final take profit at 100% (full pattern projection)
#             Conservative, rule-based exits tied to pattern geometry
#
#   'MITCH' - Mitch Ray's External Market Structure approach
#             Focuses on measured moves, previous support/resistance levels
#             Uses broader market context (moving averages, trendlines)
#             Targets exist outside the pattern based on market structure
#             Adapts to external technical levels and price action
#
#   'POSITION' - Long-term combined MITCH and SCOTT strategy
#                Blends Fibonacci levels with external market structure
#                Targets much larger timeframes (months to years)
#                Aims for x2-x5 gains on the asset
#                Holds through intermediate levels for maximum profit potential
TP_STRATEGY = 'MITCH'

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_stock_list() -> list:
    """
    Get list of stocks, ETFs, and commodities to scan based on configuration settings.

    Returns:
        List of ticker symbols
    """
    from data.stock_universe import get_stock_universe

    return get_stock_universe(
        stocks_to_scan=STOCKS_TO_SCAN,
        etfs_to_scan=SCAN_ETFS,
        commodities_to_scan=SCAN_COMMODITIES,
        max_stocks=MAX_STOCKS_TO_SCAN,
        min_volume_usd=MIN_VOLUME_USD,
        min_volume_stocks=MIN_VOLUME_STOCKS,
        filter_by_stock_volume=FILTER_BY_STOCK_VOLUME,
        download_delay=DOWNLOAD_DELAY,
        timeframe=DATA_INTERVAL,
        min_bars=MIN_BARS_REQUIRED
    )


def get_crypto_list() -> list:
    """
    Get list of cryptocurrencies to scan based on CRYPTOS_TO_SCAN configuration.

    Returns:
        List of crypto ticker symbols in Yahoo Finance format (e.g., ['BTC-USD', 'ETH-USD'])
    """
    from data.crypto_universe import get_crypto_universe

    if CRYPTOS_TO_SCAN is None or CRYPTOS_TO_SCAN.upper() == 'NONE':
        return []

    return get_crypto_universe(
        cryptos_to_scan=CRYPTOS_TO_SCAN,
        min_volume_usd=MIN_VOLUME_USD,
        download_delay=DOWNLOAD_DELAY,
        timeframe=DATA_INTERVAL,
        min_bars=MIN_BARS_REQUIRED
    )


def get_settings_summary():
    """Print current configuration settings"""
    interval_names = {
        '1d': 'Daily (1d) - Active Trading',
        '3d': '3-Day (3d) - Swing Trading',
        '1wk': 'Weekly (1wk) - Swing/Position Trading',
        '1mo': 'Monthly (1mo) - Position/Long-term Trading'
    }

    print("="*70)
    print("CURRENT CONFIGURATION SETTINGS")
    print("="*70)
    print(f"TIMEFRAME: {interval_names.get(DATA_INTERVAL, DATA_INTERVAL)}")
    print(f"  Trading Style: {_TIMEFRAME_CONFIG.get('TIMEFRAME_NOTES', 'N/A')}")
    print()
    print("PATTERN DETECTION (Optimized for timeframe):")
    print(f"  Swing Window: {SWING_WINDOW}")
    print(f"  Max Days Since Pattern: {MAX_DAYS_SINCE_PATTERN} days")
    print()
    print("DATA SETTINGS:")
    print(f"  Data Period: {DATA_PERIOD}")
    print(f"  Data Interval: {DATA_INTERVAL}")
    print()
    print("RISK MANAGEMENT (Optimized for timeframe):")
    print(f"  Stop Loss Range: {MIN_ALLOWED_STOP_LOSS_PCT}% - {MAX_ALLOWED_STOP_LOSS_PCT}%")
    print(f"  Min R/R - LONG (BUY):  {MIN_LONG_RISK_REWARD_RATIO}:1")
    print(f"  Min R/R - SHORT (SELL): {MIN_SHORT_RISK_REWARD_RATIO}:1")
    print()
    print("POSITION SIZING:")
    print(f"  T1 Exit: {POSITION_SIZE_T1*100:.0f}%")
    print(f"  T2 Exit: {POSITION_SIZE_T2*100:.0f}%")
    print(f"  T3 Exit: {POSITION_SIZE_T3*100:.0f}%")
    print()
    print("SCANNING SETTINGS:")
    # Parallel Processing
    if ENABLE_PARALLEL_PROCESSING:
        mode_desc = "processes (bypasses GIL)" if PARALLEL_MODE == 'process' else "threads (I/O-bound)"
        print(f"  Parallel Processing: Enabled ({PARALLEL_WORKERS} {mode_desc})")
    else:
        print(f"  Parallel Processing: Disabled (sequential scanning)")

    # Stock Universe
    if STOCKS_TO_SCAN and STOCKS_TO_SCAN.upper() != 'NONE':
        if STOCKS_TO_SCAN.upper() == 'ALL':
            if FILTER_BY_STOCK_VOLUME:
                stock_desc = f"All Nasdaq stocks (volume > {MIN_VOLUME_STOCKS:,} shares)"
            else:
                stock_desc = f"All Nasdaq stocks (volume > ${MIN_VOLUME_USD:,} USD)"
        elif STOCKS_TO_SCAN.upper() == 'SP500':
            stock_desc = "S&P 500 stocks"
        else:
            stock_desc = STOCKS_TO_SCAN
        print(f"  Stock Universe: {stock_desc}")
    else:
        print(f"  Stock Universe: None (stocks disabled)")

    # ETF Universe
    if SCAN_ETFS:
        print(f"  ETF Universe: All leading ETFs (135 total)")
    else:
        print(f"  ETF Universe: Disabled")

    # Commodity Universe
    if SCAN_COMMODITIES:
        print(f"  Commodity Universe: All major commodity futures (~25 total)")
    else:
        print(f"  Commodity Universe: Disabled")

    # Crypto Universe
    if CRYPTOS_TO_SCAN and CRYPTOS_TO_SCAN.upper() != 'NONE':
        print(f"  Crypto Universe: {CRYPTOS_TO_SCAN} cryptocurrencies by market cap")
    else:
        print(f"  Crypto Universe: Disabled")

    if STOCKS_TO_SCAN and STOCKS_TO_SCAN.upper() == 'ALL':
        if FILTER_BY_STOCK_VOLUME:
            print(f"  Min Volume Filter: {MIN_VOLUME_STOCKS:,} shares avg daily (SHARE volume mode)")
        else:
            print(f"  Min Volume Filter: ${MIN_VOLUME_USD:,} USD avg daily (DOLLAR volume mode)")
    print(f"  Max Tickers to Scan: {MAX_STOCKS_TO_SCAN if MAX_STOCKS_TO_SCAN else 'All from universe'}")
    print(f"  Download Delay: {DOWNLOAD_DELAY}s")
    print()
    print("REPORTING:")
    print(f"  Detailed Reports: {'Enabled' if VERBOSE_REPORTS else 'Disabled'}")
    print(f"  Auto-Save Charts: {'Enabled' if AUTO_SAVE_CHARTS else 'Disabled'}")

    print("="*70)

def validate_config():
    """Validate configuration settings"""
    errors = []

    if DATA_INTERVAL not in ['1d', '3d', '1wk', '1mo']:
        errors.append(f"Invalid DATA_INTERVAL: {DATA_INTERVAL}. Must be '1d', '3d', '1wk', or '1mo'")

    if SWING_WINDOW < 2:
        errors.append("SWING_WINDOW must be >= 2")

    if MAX_DAYS_SINCE_PATTERN < 1:
        errors.append("MAX_DAYS_SINCE_PATTERN must be >= 1")

    if DATA_PERIOD not in ['1mo', '3mo', '6mo', '1y', '2y', '3y', '5y', '10y', 'max']:
        errors.append(f"Invalid DATA_PERIOD: {DATA_PERIOD}")

    if errors:
        print("Configuration Errors:")
        for error in errors:
            print(f"  - {error}")
        return False

    return True


if __name__ == "__main__":
    # Test configuration
    get_settings_summary()
    if validate_config():
        print("\n✓ Configuration is valid!")
    else:
        print("\n✗ Configuration has errors. Please fix them.")
