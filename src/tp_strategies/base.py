"""
Base Take Profit Strategy Interface

Defines the interface that all TP strategies must implement.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, List
import pandas as pd


@dataclass
class TPTargets:
    """Take profit targets returned by strategy"""
    primary: float  # First take profit level
    secondary: float  # Second take profit level
    final: Optional[float] = None  # Final take profit level (if applicable)
    description: str = ""  # Description of the strategy targets


class TPStrategy(ABC):
    """
    Abstract base class for take profit strategies.

    All strategies must implement calculate_targets() which receives:
    - Pattern extremes (high/low)
    - Direction (bullish/bearish)
    - Full price history for context
    - Pattern points for reference
    """

    @abstractmethod
    def calculate_targets(self,
                         pattern_high: float,
                         pattern_low: float,
                         is_bullish: bool,
                         price_data: pd.DataFrame,
                         x_price: float,
                         a_price: float,
                         b_price: float,
                         c_price: float,
                         d_price: float,
                         d_index: int) -> TPTargets:
        """
        Calculate take profit targets based on the strategy.

        Args:
            pattern_high: Highest price in completed pattern
            pattern_low: Lowest price in completed pattern
            is_bullish: True for bullish pattern
            price_data: Full price history DataFrame with OHLC data
            x_price: Point X price
            a_price: Point A price
            b_price: Point B price
            c_price: Point C price
            d_price: Point D price (entry point)
            d_index: Index of point D in price_data

        Returns:
            TPTargets object with primary, secondary, and optional final targets
        """
        pass

    @abstractmethod
    def get_strategy_name(self) -> str:
        """Return the name of this strategy"""
        pass

    def calculate_stop_loss(self,
                           pattern_high: float,
                           pattern_low: float,
                           is_bullish: bool,
                           price_data: pd.DataFrame,
                           x_price: float,
                           a_price: float,
                           b_price: float,
                           c_price: float,
                           d_price: float,
                           d_index: int,
                           max_allowed_stop_loss_pct: float,
                           min_allowed_stop_loss_pct: float = None) -> Optional[float]:
        """
        Calculate stop loss based on the strategy.

        This is an optional method. If not implemented by a strategy,
        the pattern detector will use Carney's pattern-specific stop loss.

        Args:
            pattern_high: Highest price in completed pattern
            pattern_low: Lowest price in completed pattern
            is_bullish: True for bullish pattern
            price_data: Full price history DataFrame with OHLC data
            x_price: Point X price
            a_price: Point A price
            b_price: Point B price
            c_price: Point C price
            d_price: Point D price (entry point)
            d_index: Index of point D in price_data
            max_allowed_stop_loss_pct: Maximum stop loss percentage from config
            min_allowed_stop_loss_pct: Minimum stop loss percentage from config

        Returns:
            Stop loss price, or None to use default Carney stop loss
        """
        return None  # Default: use Carney's pattern-specific stop loss
