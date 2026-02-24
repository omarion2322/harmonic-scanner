"""
Timeframe-Specific Configurations for Harmonic Pattern Detection

Each timeframe has different optimal parameters for:
- Pattern detection sensitivity (SWING_WINDOW)
- Risk management (stop loss % and R/R ratio)
- Data lookback period

Based on practical trading considerations:
- Daily (1d): Active trading, quick moves, tighter stops
- Weekly (1wk): Swing trading, medium-term holds, balanced risk
- Monthly (1mo): Position trading, long-term holds, wider stops
"""

# ============================================================================
# DAILY TIMEFRAME (1d)
# Active Trading / Short-term Swing Trading
# ============================================================================
DAILY_CONFIG = {
    'SWING_WINDOW': 4,
    'MAX_DAYS_SINCE_PATTERN': 7,
    'DATA_PERIOD': '4y',
    'MIN_ALLOWED_STOP_LOSS_PCT': 8.0,
    'MAX_ALLOWED_STOP_LOSS_PCT': 15.0,
    'MIN_LONG_RISK_REWARD_RATIO': 6.0,   # LONG (BUY) patterns
    'MIN_SHORT_RISK_REWARD_RATIO': 3.0,  # SHORT (SELL) patterns - lower due to limited downside
    'TIMEFRAME_NOTES': 'Active trading - Quick moves, tight stops, frequent monitoring'
}

# ============================================================================
# 3-DAY TIMEFRAME (3d)
# Short-to-Medium Swing Trading
# ============================================================================
THREE_DAY_CONFIG = {
    'SWING_WINDOW': 4,
    'MAX_DAYS_SINCE_PATTERN': 20,
    'DATA_PERIOD': '3y',
    'MIN_ALLOWED_STOP_LOSS_PCT': 2.5,
    'MAX_ALLOWED_STOP_LOSS_PCT': 7.0,
    'MIN_LONG_RISK_REWARD_RATIO': 1.8,   # LONG (BUY) patterns
    'MIN_SHORT_RISK_REWARD_RATIO': 1.5,  # SHORT (SELL) patterns - lower due to limited downside
    'TIMEFRAME_NOTES': 'Swing trading - Balance between daily volatility and weekly trends'
}

# ============================================================================
# WEEKLY TIMEFRAME (1wk)
# Swing Trading / Medium-term Position Trading
# ============================================================================
WEEKLY_CONFIG = {
    'SWING_WINDOW': 4,
    'MAX_DAYS_SINCE_PATTERN': 14,
    'DATA_PERIOD': '5y',
    'MIN_ALLOWED_STOP_LOSS_PCT': 8.0,
    'MAX_ALLOWED_STOP_LOSS_PCT': 15.0,
    'MIN_LONG_RISK_REWARD_RATIO': 5.0,   # LONG (BUY) patterns - Ideal is 10.0
    'MIN_SHORT_RISK_REWARD_RATIO': 3.0,  # SHORT (SELL) patterns - Ideal is 4.0
    'TIMEFRAME_NOTES': 'Swing/Position trading - Multi-week holds, balanced risk/reward'
}

# ============================================================================
# MONTHLY TIMEFRAME (1mo)
# Position Trading / Long-term Investing
# ============================================================================
MONTHLY_CONFIG = {
    'SWING_WINDOW': 3,
    'MAX_DAYS_SINCE_PATTERN': 60,
    'DATA_PERIOD': 'max',
    'MIN_ALLOWED_STOP_LOSS_PCT': 8.0,
    'MAX_ALLOWED_STOP_LOSS_PCT': 15.0,
    'MIN_LONG_RISK_REWARD_RATIO': 10.0,   # LONG (BUY) patterns
    'MIN_SHORT_RISK_REWARD_RATIO': 4.0,  # SHORT (SELL) patterns - lower due to limited downside
    'TIMEFRAME_NOTES': 'Position/Long-term trading - Multi-month holds, wider stops'
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
        print(f"⚠ Warning: Unknown interval '{interval}', defaulting to WEEKLY")
        return WEEKLY_CONFIG

    return config_map[interval]


def print_timeframe_config(interval: str):
    """Print configuration summary for a specific timeframe."""
    cfg = get_timeframe_config(interval)

    interval_names = {
        '1d': 'DAILY (1d)',
        '3d': '3-DAY (3d)',
        '1wk': 'WEEKLY (1wk)',
        '1mo': 'MONTHLY (1mo)'
    }

    print("="*70)
    print(f"TIMEFRAME: {interval_names.get(interval, interval)}")
    print("="*70)
    print(f"Trading Style: {cfg['TIMEFRAME_NOTES']}")
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
    print(f"  Min R/R - LONG (BUY):  {cfg['MIN_LONG_RISK_REWARD_RATIO']}:1")
    print(f"  Min R/R - SHORT (SELL): {cfg['MIN_SHORT_RISK_REWARD_RATIO']}:1")
    print("="*70)


if __name__ == "__main__":
    print("\n")
    print("="*70)
    print("HARMONIC PATTERN SCANNER - TIMEFRAME CONFIGURATIONS")
    print("="*70)
    print()

    # Show all timeframe configurations
    for interval in ['1d', '3d', '1wk', '1mo']:
        print_timeframe_config(interval)
        print()
