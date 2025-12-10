"""
Timeframe-Specific Configurations for Harmonic Pattern Detection
Optimized for real-life trading conditions based on Scott Carney's framework

Each timeframe has different optimal parameters for:
- Pattern detection sensitivity (SWING_WINDOW)
- Pattern age limits (MAX_DAYS_SINCE_PATTERN)
- Risk management (stop loss % and R/R ratio)
- Data lookback period

These are based on practical trading considerations:
- Daily: Active trading, quick moves, tighter stops
- Weekly: Swing trading, medium-term holds, balanced risk
- Monthly: Position trading, long-term holds, wider stops
"""

# ============================================================================
# DAILY TIMEFRAME CONFIGURATION (1d)
# Active Trading / Day Trading / Short-term Swing Trading
# ============================================================================
DAILY_CONFIG = {
    # Pattern Detection
    'SWING_WINDOW': 3,  # Lower for patterns on smaller time frames, extend to 10-20 for monthly patterns
    'MAX_DAYS_SINCE_PATTERN': 1450,  # Patterns valid for ~2 weeks max

    # Data Settings
    'DATA_PERIOD': '4y',  # 2 years sufficient for daily patterns

    # Risk Management (Daily patterns have tighter stops)
    'MIN_ALLOWED_STOP_LOSS_PCT': 8.0,  # Minimum 3% stop for daily trading
    'MAX_ALLOWED_STOP_LOSS_PCT': 12.0,  # Maximum 10% stop for daily trading
    'MIN_RISK_REWARD_RATIO': 1.5,  # Require 2:1 minimum for active trading

    # Trading Notes
    'TIMEFRAME_NOTES': 'Active trading - Quick pattern completion, tight stops, frequent monitoring required'
}

# ============================================================================
# 3-DAY TIMEFRAME CONFIGURATION (3d)
# Short-to-Medium Swing Trading
# ============================================================================
THREE_DAY_CONFIG = {
    # Pattern Detection
    'SWING_WINDOW': 4,  # Slightly lower than daily
    'MAX_DAYS_SINCE_PATTERN': 20,  # Patterns valid for ~3 weeks
    'MAX_SEARCH_SWING_POINTS': 20,  # Search next 20 swing points for D completion
    'MAX_XABC_SWING_GAP': 1,  # Allow up to 1 intervening swing between XABC points

    # Data Settings
    'DATA_PERIOD': '3y',  # 3 years for 3-day patterns

    # Risk Management
    'MIN_ALLOWED_STOP_LOSS_PCT': 2.5,  # Minimum 2.5% stop for 3-day trading
    'MAX_ALLOWED_STOP_LOSS_PCT': 7.0,  # Maximum 7% stop for 3-day trading
    'MIN_RISK_REWARD_RATIO': 1.8,  # Slightly relaxed from daily

    # Trading Notes
    'TIMEFRAME_NOTES': 'Swing trading - Balance between daily volatility and weekly trends'
}

# ============================================================================
# WEEKLY TIMEFRAME CONFIGURATION (1wk)
# Swing Trading / Medium-term Position Trading
# ============================================================================
WEEKLY_CONFIG = {
    # Pattern Detection
    'SWING_WINDOW': 4,  # Smaller swing_window is better for weekly patterns
    'MAX_DAYS_SINCE_PATTERN': 1450,  # Patterns valid for ~6 weeks (1.5 months)
    'MAX_SEARCH_SWING_POINTS': 10,  # Search next 100 swing points for D completion (allows longer patterns on weekly)
    'MAX_XABC_SWING_GAP': 2,  # Allow up to 3 intervening swings between XABC points (enables longer weekly patterns)

    # Data Settings
    'DATA_PERIOD': '4y',  # 5 years optimal for weekly patterns

    # Risk Management (Weekly patterns have medium stops)
    'MIN_ALLOWED_STOP_LOSS_PCT': 8.0,  # Minimum 5% stop for weekly trading
    'MAX_ALLOWED_STOP_LOSS_PCT': 15.0,  # Maximum 15% stop for weekly trading
    'MIN_RISK_REWARD_RATIO': 1.5,  # Standard Carney 1.5:1 minimum

    # Trading Notes
    'TIMEFRAME_NOTES': 'Swing/Position trading - Multi-week holds, balanced risk/reward, weekly monitoring'
}

# ============================================================================
# MONTHLY TIMEFRAME CONFIGURATION (1mo)
# Position Trading / Long-term Investing
# ============================================================================
MONTHLY_CONFIG = {
    # Pattern Detection
    'SWING_WINDOW': 4,  # Very low for monthly = only major multi-year peaks/troughs
    'MAX_DAYS_SINCE_PATTERN': 375,  # Patterns valid for ~3 months
    'MAX_SEARCH_SWING_POINTS': 10,  # Search next 150 swing points for D completion (allows very long patterns on monthly)
    'MAX_XABC_SWING_GAP': 3,  # Allow up to 5 intervening swings between XABC points (enables very long monthly patterns)

    # Data Settings
    'DATA_PERIOD': 'max',  # Maximum history for monthly (10-20 years)

    # Risk Management (Monthly patterns have wider stops)
    'MIN_ALLOWED_STOP_LOSS_PCT': 8.0,  # Minimum 8% stop for monthly trading
    'MAX_ALLOWED_STOP_LOSS_PCT': 20.0,  # Maximum 20% stop for monthly trading
    'MIN_RISK_REWARD_RATIO': 1.5,  # Keep 1.5:1 minimum even for long-term

    # Trading Notes
    'TIMEFRAME_NOTES': 'Position/Long-term trading - Multi-month holds, wider stops, monthly monitoring'
}

# ============================================================================
# CONFIGURATION SELECTOR
# ============================================================================

def get_timeframe_config(interval: str) -> dict:
    """
    Get optimal configuration for specified timeframe.

    Args:
        interval: Data interval ('1d', '3d', '1wk', '1mo')

    Returns:
        Dictionary with optimized settings for that timeframe
    """
    config_map = {
        '1d': DAILY_CONFIG,
        '3d': THREE_DAY_CONFIG,
        '1wk': WEEKLY_CONFIG,
        '1mo': MONTHLY_CONFIG
    }

    if interval not in config_map:
        print(f"⚠ Warning: Unknown interval '{interval}', defaulting to WEEKLY configuration")
        return WEEKLY_CONFIG

    return config_map[interval]


def print_timeframe_config(interval: str):
    """Print the configuration for a specific timeframe."""
    cfg = get_timeframe_config(interval)

    interval_names = {
        '1d': 'DAILY (1d)',
        '3d': '3-DAY (3d)',
        '1wk': 'WEEKLY (1wk)',
        '1mo': 'MONTHLY (1mo)'
    }

    print("="*70)
    print(f"TIMEFRAME CONFIGURATION: {interval_names.get(interval, interval)}")
    print("="*70)
    print(f"Trading Style:     {cfg['TIMEFRAME_NOTES']}")
    print()
    print("PATTERN DETECTION:")
    print(f"  Swing Window:           {cfg['SWING_WINDOW']}")
    print(f"  Max Days Since Pattern: {cfg['MAX_DAYS_SINCE_PATTERN']} days")
    print()
    print("DATA SETTINGS:")
    print(f"  Lookback Period:       {cfg['DATA_PERIOD']}")
    print()
    print("RISK MANAGEMENT:")
    print(f"  Stop Loss Range:       {cfg['MIN_ALLOWED_STOP_LOSS_PCT']}% - {cfg['MAX_ALLOWED_STOP_LOSS_PCT']}%")
    print(f"  Min Risk/Reward Ratio: {cfg['MIN_RISK_REWARD_RATIO']}:1")
    print("="*70)
    print()


# ============================================================================
# SCOTT CARNEY'S FRAMEWORK PRINCIPLES (Timeframe-Independent)
# ============================================================================

CARNEY_PRINCIPLES = """
Scott Carney's Framework Principles (Apply to ALL Timeframes):

1. PATTERN STRUCTURE:
   - Exact Fibonacci ratios define pattern validity
   - B point is critical (must be precise)
   - BC projection differentiates Gartley vs Bat (1.618 threshold)
   - D point completion defines entry

2. ENTRY RULES:
   - ALWAYS enter at Point D (PRZ completion)
   - Price must reverse IMMEDIATELY from PRZ
   - No "wait and see" - pattern is valid or it's not

3. STOP LOSS (Pattern-Specific):
   - Gartley: 1.13 x XA
   - Bat: 1.0 x XA (tightest stop)
   - Butterfly: 1.41 x XA
   - Crab: 2.0+ x XA (widest stop)
   - NEVER move stops once set

4. PROFIT TARGETS (I.P.O. Method):
   - Target 1: 0.382 retracement of pattern range
   - Target 2: 0.618 retracement of pattern range
   - Target 3: Point A (full pattern retracement)
   - Take partial profits at each level

5. PATTERN QUALITY:
   - Textbook patterns = most reliable
   - Pattern precision matters more than timeframe
   - Extension patterns (Butterfly/Crab) require more room

6. TIMEFRAME ADAPTATION:
   - Larger timeframes = larger patterns, longer holds, wider stops
   - Smaller timeframes = smaller patterns, quicker moves, tighter stops
   - Fibonacci ratios remain CONSTANT across all timeframes
   - Risk management scales with timeframe
"""

if __name__ == "__main__":
    print("\n")
    print("="*70)
    print("SCOTT CARNEY HARMONIC PATTERN FRAMEWORK")
    print("Timeframe-Optimized Configurations")
    print("="*70)
    print()

    # Show all timeframe configurations
    for interval in ['1d', '3d', '1wk', '1mo']:
        print_timeframe_config(interval)
        print()

    # Print Carney's principles
    print(CARNEY_PRINCIPLES)
