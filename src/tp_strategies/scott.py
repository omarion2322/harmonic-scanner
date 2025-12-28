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
import pandas as pd


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
                         ticker: str = None) -> TPTargets:
        """
        Calculate I.P.O. targets using Carney's Fibonacci method.

        Uses 38.2% and 61.8% retracements of the full pattern range,
        with final target at the pattern extreme (100%).
        """
        pattern_range = pattern_high - pattern_low

        if is_bullish:
            # Bullish: measure retracements from pattern low
            primary = pattern_low + (pattern_range * 0.382)
            secondary = pattern_low + (pattern_range * 0.618)
            final = pattern_high  # 100% = point A or pattern high
        else:
            # Bearish: measure retracements from pattern high
            primary = pattern_high - (pattern_range * 0.382)
            secondary = pattern_high - (pattern_range * 0.618)
            final = pattern_low  # 100% = point A or pattern low

        description = (
            f"Scott Carney I.P.O.: 38.2% @ {primary:.2f}, "
            f"61.8% @ {secondary:.2f}, 100% @ {final:.2f}"
        )

        return TPTargets(
            primary=primary,
            secondary=secondary,
            final=final,
            description=description,
            tp_strategy_used="Fibonacci"
        )

    def get_strategy_name(self) -> str:
        return "SCOTT"
