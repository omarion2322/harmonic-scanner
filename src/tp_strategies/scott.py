"""
SCOTT Take Profit Strategy

Scott Carney's Fibonacci-based approach using Initial Profit Objectives (I.P.O.)
Targets are based on Fibonacci retracements of the pattern range.

Strategy:
- Primary Target: 38.2% retracement of pattern range
- Secondary Target: 61.8% retracement of pattern range
- Final Target: 100% (Point A or pattern extreme)

This is the conservative, rule-based approach tied to pattern geometry.
"""

from tp_strategies.base import TPStrategy, TPTargets
from carney_patterns import calculate_ipo_target
import pandas as pd
from typing import Optional


class ScottStrategy(TPStrategy):
    """
    Scott Carney's Initial Profit Objective (I.P.O.) strategy.

    Targets are Fibonacci retracements from pattern extremes (high-low range),
    NOT from individual legs like AD.
    """

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
                         ticker: Optional[str] = None) -> TPTargets:
        """
        Calculate I.P.O. targets using Carney's Fibonacci method.

        Uses 38.2% and 61.8% retracements of the full pattern range,
        with final target at the pattern extreme (100%).
        """
        primary, secondary = calculate_ipo_target(
            pattern_high, pattern_low, is_bullish
        )
        final = pattern_high if is_bullish else pattern_low

        description = (
            f"Scott Carney I.P.O.: 38.2% @ {primary:.2f}, "
            f"61.8% @ {secondary:.2f}, 100% @ {final:.2f}"
        )

        return TPTargets(
            primary=primary,
            secondary=secondary,
            final=final,
            description=description,
            tp_strategy_used="Fibonacci",
            target_details=(
                "Fibonacci 38.2% (projection)",
                "Fibonacci 61.8% (projection)",
                "Fibonacci 100% (projection)",
            ),
        )

    def get_strategy_name(self) -> str:
        return "SCOTT"
