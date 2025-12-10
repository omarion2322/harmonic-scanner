"""
Configuration File for Harmonic Pattern Trading System

Edit these settings to customize the scanner behavior without modifying the main code.
"""

# ============================================================================
# TIMEFRAME SELECTION (PRIMARY SETTING)
# ============================================================================

# Choose your trading timeframe - this will automatically load optimized settings
# Options: '1d' (daily), '3d' (3-day), '1wk' (weekly), '1mo' (monthly)
DATA_INTERVAL = '1wk'  # <<< CHANGE THIS TO SELECT YOUR TIMEFRAME

# Import timeframe-specific optimized configurations
from config_timeframes import get_timeframe_config

# Load optimized settings for selected timeframe
_TIMEFRAME_CONFIG = get_timeframe_config(DATA_INTERVAL)

# ============================================================================
# PATTERN DETECTION SETTINGS (Auto-loaded from timeframe config)
# ============================================================================

# These values are automatically set based on DATA_INTERVAL above
# You can override them manually if needed, but the defaults are optimized

# Pattern Detection Engine Selection
# When True: Uses pyharmonics' HarmonicSearch to find and validate patterns
#   - Matrix-based detection with built-in Fibonacci validation
#   - Current algorithm adds: Carney trading specs, stop loss, targets, charting
# When False: Uses custom algorithm for complete pattern detection and validation
#   - Forward-search XABC → find D in PRZ
#   - Carney-specific validation rules and trading specs
USE_PYHARMONICS_HARMONIC_SEARCH = True

# Fibonacci tolerance for pyharmonics (only when USE_PYHARMONICS_HARMONIC_SEARCH = True)
# Controls pattern matching precision: 0.03 = 3% tolerance, 0.05 = 5% (more lenient)
PYHARMONICS_FIB_TOLERANCE = 0.03

# Swing point detection window (higher = less sensitive, fewer patterns)
# Relevant only if using custom detection algorithm (USE_PYHARMONICS_HARMONIC_SEARCH = False)
SWING_WINDOW = _TIMEFRAME_CONFIG['SWING_WINDOW']

# Maximum days since pattern completion to generate BUY/SELL signal
# Relevant only if using custom detection algorithm (USE_PYHARMONICS_HARMONIC_SEARCH = False)
MAX_DAYS_SINCE_PATTERN = _TIMEFRAME_CONFIG['MAX_DAYS_SINCE_PATTERN']

# Maximum swing points to search ahead for pattern D completion
# This controls how far ahead the detector looks for the D point after finding XABC
# Higher values allow detection of longer-duration patterns
# Relevant only if using custom detection algorithm (USE_PYHARMONICS_HARMONIC_SEARCH = False)
# Timeframe-specific: Daily=10, 3-Day=20, Weekly=100, Monthly=150
MAX_SEARCH_SWING_POINTS = _TIMEFRAME_CONFIG.get('MAX_SEARCH_SWING_POINTS', 10)

# Maximum gap (intervening swings) allowed between XABC points
# Controls how stretched out the XABC structure can be
# 0 = XABC must be consecutive (tight patterns)
# 3 = Allow up to 3 swings between each XABC point (longer patterns)
# This respects Carney's framework: still requires alternating peaks/troughs and precise Fibonacci ratios
# Relevant only if using custom detection algorithm (USE_PYHARMONICS_HARMONIC_SEARCH = False)
# Timeframe-specific: Daily=0, 3-Day=1, Weekly=3, Monthly=5
MAX_XABC_SWING_GAP = _TIMEFRAME_CONFIG.get('MAX_XABC_SWING_GAP', 0)

# ============================================================================
# ADVANCED SWING DETECTION SETTINGS FOR CUSTOM HARMONIC SEARCH
# ============================================================================

# Enable Micro-Swing Mode (2-bar minimum swing detection)
# When enabled, allows price swings formed by as little as 2 bars for
# Standard and Relaxed tolerance modes (Textbook always uses standard detection)
# Expected pattern increase: +35-60% with micro-swing mode
ENABLE_MICRO_SWING_MODE = False

# Enable Multi-Swing BC Leg Detection
# When enabled, allows BC leg to contain 2-8 internal micro-swings while still
# measuring BC as a single macro retracement from B to C
# Internal swings must be ≥0.236 of BC leg magnitude
# Validates that C remains terminal extreme and doesn't violate X
ENABLE_MULTI_SWING_BC = False

# Minimum internal swing magnitude (as fraction of BC leg)
# Internal swings below this magnitude will be filtered out
# Default: 0.236 (23.6% Fibonacci ratio)
MULTI_SWING_BC_MIN_MAGNITUDE = 0.236

# Multi-swing BC limits (2-8 internal swings)
MULTI_SWING_BC_MIN_COUNT = 2
MULTI_SWING_BC_MAX_COUNT = 8

# ============================================================================
# DATA SETTINGS (Auto-loaded from timeframe config)
# ============================================================================

# Historical data period to analyze
DATA_PERIOD = _TIMEFRAME_CONFIG['DATA_PERIOD']

CRYPTO_TICKERS = ['BTC-USD', 'ETH-USD', 'LTC-USD', 'XRP-USD']

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
STOCK_TICKERS = ['ONDS', 'RIVN', 'TIC', 'IQ', 'PANW', 'DOCU', 'LAC', 'URA', 'FRSH', 'EVEX', 'SSYS','BULL','TGT','CROX', 'CLSK', 'TEAM']

# ETF universe to scan
# Set to True to include all leading ETFs (135 total), False to skip ETFs
SCAN_ETFS = True

CRYPTOS_TO_SCAN = 'Top100'  # Options: 'Top100', 'Top50', 'Top20', or None

# Minimum average daily volume in USD (applies to 'All' Nasdaq mode only)
# Filters stocks to ensure liquidity for harmonic pattern trading
# Default: $1,000,000 USD average daily dollar volume
MIN_VOLUME_USD = 1_000_000

# Maximum number of stocks to scan (None = all from selected universe)
# Use a smaller number for testing (e.g., 50)
MAX_STOCKS_TO_SCAN = 10000  # Set to 50 for testing

# Add delay between stock downloads to avoid rate limiting
# In seconds (0.1 = 100ms, 0.5 = 500ms)
# Increase if you get rate limit errors
DOWNLOAD_DELAY = 0.0


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
INCLUDE_HOLD_IN_REPORT = True

# Verbose mode: Generate detailed asset-specific explanations
# When True, reports include detailed analysis for each stock explaining
# why it received a BUY/SELL/HOLD signal with pattern-specific details
VERBOSE_REPORTS = False

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

# Minimum risk percentage (minimum acceptable stop loss distance)
# Stop losses tighter than this will be rejected as too risky (prone to noise)
# Auto-adjusted based on timeframe:
#   Daily: 3% min (avoid noise in active trading)
#   3-day: 2.5% min (slightly tighter)
#   Weekly: 5% min (avoid weekly volatility noise)
#   Monthly: 8% min (avoid monthly volatility noise)
MIN_ALLOWED_STOP_LOSS_PCT = _TIMEFRAME_CONFIG['MIN_ALLOWED_STOP_LOSS_PCT']

# Maximum risk percentage filter (distance from entry to stop loss)
# Patterns with risk > this percentage will be filtered out as HOLD
# This preserves market structure but filters excessively risky trades
# Auto-adjusted based on timeframe:
#   Daily: 10% max (tight stops for active trading)
#   3-day: 7% max (slightly wider)
#   Weekly: 10% max (medium stops for swing trading)
#   Monthly: 20% max (wider stops for position trading)
MAX_ALLOWED_STOP_LOSS_PCT = _TIMEFRAME_CONFIG['MAX_ALLOWED_STOP_LOSS_PCT']

# Minimum risk/reward ratio to generate BUY/SELL signal
# Auto-adjusted based on timeframe:
#   Daily: 2.0:1 (higher standard for active trading)
#   3-day: 1.8:1 (slightly relaxed)
#   Weekly: 1.5:1 (standard Carney minimum)
#   Monthly: 1.5:1 (standard Carney minimum)
MIN_RISK_REWARD_RATIO = _TIMEFRAME_CONFIG['MIN_RISK_REWARD_RATIO']

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
TP_STRATEGY = 'MITCH'  # <<< CHANGE THIS TO SELECT YOUR TAKE PROFIT STRATEGY

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_stock_list() -> list:
    """
    Get list of stocks and ETFs to scan based on STOCKS_TO_SCAN and ETFS_TO_SCAN settings.

    Returns:
        List of ticker symbols
    """
    from stock_universe import get_stock_universe

    return get_stock_universe(
        stocks_to_scan=STOCKS_TO_SCAN,
        etfs_to_scan=SCAN_ETFS,
        max_stocks=MAX_STOCKS_TO_SCAN,
        min_volume_usd=MIN_VOLUME_USD,
        download_delay=DOWNLOAD_DELAY
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
    detection_engine = "pyharmonics HarmonicSearch" if USE_PYHARMONICS_HARMONIC_SEARCH else "Custom XABC→D Search"
    print(f"  Detection Engine: {detection_engine}")
    if USE_PYHARMONICS_HARMONIC_SEARCH:
        print(f"    Fib Tolerance: {PYHARMONICS_FIB_TOLERANCE*100:.1f}%")
        print(f"    Grading: A+ (perfect textbook) to C- (borderline at tolerance limit)")
    else:
        print(f"    Tolerance Levels: Textbook/Standard/Relaxed")
    print(f"  Swing Window: {SWING_WINDOW}")
    print(f"  Max Days Since Pattern: {MAX_DAYS_SINCE_PATTERN} days")
    print()
    print("SWING DETECTION (Advanced Features):")
    print(f"  Micro-Swing Mode: {'Enabled' if ENABLE_MICRO_SWING_MODE else 'Disabled'} (2-bar minimum)")
    print(f"  Multi-Swing BC: {'Enabled' if ENABLE_MULTI_SWING_BC else 'Disabled'}")
    if ENABLE_MULTI_SWING_BC:
        print(f"    Min magnitude: {MULTI_SWING_BC_MIN_MAGNITUDE:.3f} of BC leg")
        print(f"    Internal swing range: {MULTI_SWING_BC_MIN_COUNT}-{MULTI_SWING_BC_MAX_COUNT} swings")
    print()
    print("DATA SETTINGS:")
    print(f"  Data Period: {DATA_PERIOD}")
    print(f"  Data Interval: {DATA_INTERVAL}")
    print()
    print("RISK MANAGEMENT (Optimized for timeframe):")
    print(f"  Stop Loss Range: {MIN_ALLOWED_STOP_LOSS_PCT}% - {MAX_ALLOWED_STOP_LOSS_PCT}%")
    print(f"  Min Risk/Reward Ratio: {MIN_RISK_REWARD_RATIO}:1")
    print()
    print("SCANNING SETTINGS:")
    # Stock Universe
    if STOCKS_TO_SCAN and STOCKS_TO_SCAN.upper() != 'NONE':
        if STOCKS_TO_SCAN.upper() == 'ALL':
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

    if STOCKS_TO_SCAN and STOCKS_TO_SCAN.upper() == 'ALL':
        print(f"  Min Volume Filter: ${MIN_VOLUME_USD:,} USD avg daily")
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
