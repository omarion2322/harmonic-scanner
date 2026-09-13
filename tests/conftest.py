"""
Pytest configuration and shared fixtures.
"""

import sys
from pathlib import Path
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Add src to path for imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))


@pytest.fixture
def sample_price_data():
    """Generate sample OHLC price data for testing."""
    dates = pd.date_range(start='2023-01-01', periods=100, freq='D')
    np.random.seed(42)

    # Generate realistic price data
    close_prices = 100 + np.cumsum(np.random.randn(100) * 2)
    high_prices = close_prices + np.random.rand(100) * 3
    low_prices = close_prices - np.random.rand(100) * 3
    open_prices = close_prices + np.random.randn(100)

    df = pd.DataFrame({
        'open': open_prices,
        'high': high_prices,
        'low': low_prices,
        'close': close_prices,
        'volume': np.random.randint(1000000, 10000000, 100)
    }, index=dates)

    return df


@pytest.fixture
def mock_config():
    """Create a mock config module for testing."""
    class MockConfig:
        DATA_INTERVAL = '1d'
        DATA_PERIOD = '6mo'
        SWING_WINDOW = 3
        MAX_DAYS_TO_INITIAL_ENTRY = 30
        MAX_DAYS_SINCE_PATTERN = 30
        MAX_BARS_TO_MONITOR_REACTION = 30
        PYHARMONICS_FIB_TOLERANCE = 0.03
        MIN_LONG_RISK_REWARD_RATIO = 1.5
        MIN_SHORT_RISK_REWARD_RATIO = 1.5
        MAX_ALLOWED_STOP_LOSS_PCT = 10.0
        MIN_ALLOWED_STOP_LOSS_PCT = 3.0
        AUTO_SAVE_CHARTS = False
        VERBOSE_REPORTS = False
        TP_STRATEGY = 'SCOTT'
        POSITION_SIZE_T1 = 0.5
        POSITION_SIZE_T2 = 0.3
        POSITION_SIZE_T3 = 0.2

        @staticmethod
        def get_stock_list():
            return ['AAPL', 'MSFT', 'GOOGL']

    return MockConfig()


@pytest.fixture
def sample_pattern_points():
    """Generate sample pattern points for testing."""
    from pattern_detector import Point

    base_date = datetime(2023, 1, 1)

    return {
        'x': Point(0, 100.0, pd.Timestamp(base_date), 'TROUGH'),
        'a': Point(1, 110.0, pd.Timestamp(base_date + timedelta(days=10)), 'PEAK'),
        'b': Point(2, 103.0, pd.Timestamp(base_date + timedelta(days=20)), 'TROUGH'),
        'c': Point(3, 108.0, pd.Timestamp(base_date + timedelta(days=30)), 'PEAK'),
        'd': Point(4, 101.5, pd.Timestamp(base_date + timedelta(days=40)), 'TROUGH'),
    }
