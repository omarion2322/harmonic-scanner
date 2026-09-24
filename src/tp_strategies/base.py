"""
Base Take Profit Strategy Interface

Defines the interface that all TP strategies must implement.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, List, Sequence, Tuple
import math
import pandas as pd


@dataclass
class TPTargets:
    """Take profit targets returned by strategy"""
    primary: Optional[float]  # First take profit level, if supported
    secondary: Optional[float]  # Second take profit level, if supported
    final: Optional[float] = None  # Final take profit level (if applicable)
    description: str = ""  # Description of the strategy targets
    tp_strategy_used: str = ""  # Which TP strategy was used (e.g., "Scoring Engine", "Fixed")
    target_details: Tuple[Optional[str], Optional[str], Optional[str]] = (
        None, None, None
    )


def format_target(price: Optional[float]) -> str:
    """Format an available target without inventing a price for missing levels."""
    return f"${price:.2f}" if price is not None else "N/A"


def target_allocations(
    targets: Sequence[Optional[float]], weights: Sequence[float]
) -> Tuple[float, float, float]:
    """Assign missing exits' allocations to the last available target."""
    if len(targets) != 3 or len(weights) != 3:
        raise ValueError("Exactly three target slots and exit weights are required")
    if any(not math.isfinite(w) or w < 0 for w in weights) or not math.isclose(
        sum(weights), 1.0, abs_tol=0.001
    ):
        raise ValueError("Exit weights must be finite, nonnegative and sum to one")
    count = 0
    missing = False
    for target in targets:
        if target is None:
            missing = True
        elif missing or not math.isfinite(target) or target <= 0:
            raise ValueError("Targets must be finite positive prices followed by missing slots")
        else:
            count += 1
    allocation = [0.0, 0.0, 0.0]
    if count:
        allocation[:count] = weights[:count]
        allocation[count - 1] += sum(weights[count:])
    return allocation[0], allocation[1], allocation[2]


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
                         d_index: int,
                         ticker: str = None) -> TPTargets:
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
            ticker: Stock ticker symbol (for debugging/logging)

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
