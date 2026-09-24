"""
POSITION Take Profit Strategy

Long-term combined strategy blending Scott Carney's Fibonacci approach
with Mitch Ray's external market structure analysis.

Strategy:
- Targets much larger timeframes (months to years)
- Aims for x2-x5 gains (100% to 400% profit)
- Combines Fibonacci extensions with external structure
- Uses extended projections: 1.618, 2.0, 2.618, 3.618 of pattern range
- Identifies major support/resistance zones for macro targets
- Holds through intermediate levels for maximum profit potential

This is a position trading strategy for patient traders seeking
substantial returns over longer holding periods.
"""

from tp_strategies.base import TPStrategy, TPTargets
from tp_strategies.scott import ScottStrategy
from tp_strategies.mitch import MitchStrategy
import pandas as pd
import numpy as np
from typing import List, Tuple


class PositionStrategy(TPStrategy):
    """
    Long-term position trading strategy combining Fibonacci extensions
    with external market structure for x2-x5 profit targets.

    This strategy looks beyond the pattern itself to identify
    major market levels that could support 100%-400% gains.
    """

    def __init__(self, swing_window: int = 5):
        """
        Initialize Position strategy.

        Args:
            swing_window: Window size for swing point detection (from config SWING_WINDOW)
                         Uses the entire stock history available for analysis
        """
        self.swing_window = swing_window
        self.scott_strategy = ScottStrategy()
        self.mitch_strategy = MitchStrategy(swing_window=swing_window)

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
        Calculate long-term position targets using Fibonacci extensions
        and major external market structure levels.

        Targets x2 (100%), x3 (200%), and x5 (400%) profit levels.
        """
        # Calculate pattern range for Fibonacci extensions
        pattern_range = pattern_high - pattern_low

        # Get Mitch's external structure targets for context
        mitch_targets = self.mitch_strategy.calculate_targets(
            pattern_high, pattern_low, is_bullish, price_data,
            x_price, a_price, b_price, c_price, d_price, d_index, ticker
        )

        # Get ALL historical data for major structure analysis (entire stock history)
        historical_data = price_data.iloc[:d_index + 1].copy()

        if is_bullish:
            targets = self._calculate_bullish_position_targets(
                d_price, pattern_range, pattern_high, pattern_low,
                historical_data, mitch_targets
            )
        else:
            targets = self._calculate_bearish_position_targets(
                d_price, pattern_range, pattern_high, pattern_low,
                historical_data, mitch_targets
            )

        return targets

    def _calculate_bullish_position_targets(self,
                                            d_price: float,
                                            pattern_range: float,
                                            pattern_high: float,
                                            pattern_low: float,
                                            historical_data: pd.DataFrame,
                                            mitch_targets: TPTargets) -> TPTargets:
        """
        Calculate long-term bullish targets for x2-x5 gains.

        Combines:
        1. Fibonacci extensions (1.618, 2.0, 2.618, 3.618 of pattern range)
        2. Major historical resistance levels
        3. Psychological levels (round numbers, ATHs)
        """
        candidate_targets = []

        # 1. Fibonacci Extensions from D
        # x2 profit = d_price + (d_price - entry) * 2 ≈ 100% gain
        # But we'll use pattern-based extensions which are more conservative
        fib_1618 = pattern_low + (pattern_range * 1.618)  # ~60% extension
        fib_2000 = pattern_low + (pattern_range * 2.0)    # ~100% extension
        fib_2618 = pattern_low + (pattern_range * 2.618)  # ~160% extension
        fib_3618 = pattern_low + (pattern_range * 3.618)  # ~260% extension

        candidate_targets.append(("Fib 1.618", fib_1618))
        candidate_targets.append(("Fib 2.0", fib_2000))
        candidate_targets.append(("Fib 2.618", fib_2618))
        candidate_targets.append(("Fib 3.618", fib_3618))

        # 2. Profit-based targets (x2, x3, x5 from entry)
        # Entry is at D price, so calculate absolute profit targets
        profit_x2 = d_price + (d_price - pattern_low) * 2  # 2x gain from entry
        profit_x3 = d_price + (d_price - pattern_low) * 3  # 3x gain from entry
        profit_x5 = d_price + (d_price - pattern_low) * 5  # 5x gain from entry

        candidate_targets.append(("2x Gain", profit_x2))
        candidate_targets.append(("3x Gain", profit_x3))
        candidate_targets.append(("5x Gain", profit_x5))

        # 3. Major historical resistance (all-time highs in lookback period)
        if len(historical_data) > 0:
            ath = historical_data['high'].max()
            if ath > d_price:
                candidate_targets.append(("Historical ATH", ath))

            # Major resistance levels (top 3 swing highs in history)
            major_highs = self._find_major_levels(historical_data, is_high=True, count=3)
            for i, level in enumerate(major_highs):
                if level > d_price:
                    candidate_targets.append((f"Major Resistance {i+1}", level))

        # 4. Incorporate Mitch's external structure if above our extensions
        if mitch_targets.final and mitch_targets.final > fib_2000:
            candidate_targets.append(("Mitch Final", mitch_targets.final))

        # Filter targets above entry and sort by price
        valid_targets = [(name, price) for name, price in candidate_targets if price > d_price]
        valid_targets.sort(key=lambda x: x[1])

        # Select primary (first major level), secondary (mid-range), final (aggressive)
        if len(valid_targets) >= 3:
            # Primary: First significant level (conservative)
            primary_idx = min(2, len(valid_targets) - 1)  # 3rd target or less
            primary = valid_targets[primary_idx][1]
            primary_name = valid_targets[primary_idx][0]

            # Secondary: Mid-range target (~x2-x3 zone)
            secondary_idx = min(4, len(valid_targets) - 1)  # 5th target or less
            secondary = valid_targets[secondary_idx][1]
            secondary_name = valid_targets[secondary_idx][0]

            # Final: Aggressive target (x5 zone or highest valid level)
            final_idx = min(6, len(valid_targets) - 1)  # 7th target or less
            final = valid_targets[final_idx][1]
            final_name = valid_targets[final_idx][0]

            desc = (f"Position Strategy: {primary_name} @ {primary:.2f} "
                   f"→ {secondary_name} @ {secondary:.2f} "
                   f"→ {final_name} @ {final:.2f}")
        else:
            # Fallback to basic Fibonacci extensions
            primary = fib_1618
            secondary = fib_2618
            final = fib_3618
            primary_name = "Fib 1.618"
            secondary_name = "Fib 2.618"
            final_name = "Fib 3.618"
            desc = f"Position Strategy: Fib 1.618 @ {primary:.2f} → Fib 2.618 @ {secondary:.2f} → Fib 3.618 @ {final:.2f}"

        return TPTargets(
            primary=primary,
            secondary=secondary,
            final=final,
            description=desc,
            tp_strategy_used=mitch_targets.tp_strategy_used if hasattr(mitch_targets, 'tp_strategy_used') and mitch_targets.tp_strategy_used else "Combined",
            target_details=(primary_name, secondary_name, final_name),
        )

    def _calculate_bearish_position_targets(self,
                                            d_price: float,
                                            pattern_range: float,
                                            pattern_high: float,
                                            pattern_low: float,
                                            historical_data: pd.DataFrame,
                                            mitch_targets: TPTargets) -> TPTargets:
        """
        Calculate long-term bearish targets for x2-x5 gains.
        """
        candidate_targets = []

        # 1. Fibonacci Extensions from D (downward)
        fib_1618 = pattern_high - (pattern_range * 1.618)
        fib_2000 = pattern_high - (pattern_range * 2.0)
        fib_2618 = pattern_high - (pattern_range * 2.618)
        fib_3618 = pattern_high - (pattern_range * 3.618)

        candidate_targets.append(("Fib 1.618", fib_1618))
        candidate_targets.append(("Fib 2.0", fib_2000))
        candidate_targets.append(("Fib 2.618", fib_2618))
        candidate_targets.append(("Fib 3.618", fib_3618))

        # 2. Profit-based targets (x2, x3, x5 from entry)
        profit_x2 = d_price - (pattern_high - d_price) * 2
        profit_x3 = d_price - (pattern_high - d_price) * 3
        profit_x5 = d_price - (pattern_high - d_price) * 5

        candidate_targets.append(("2x Gain", profit_x2))
        candidate_targets.append(("3x Gain", profit_x3))
        candidate_targets.append(("5x Gain", profit_x5))

        # 3. Major historical support (all-time lows in lookback period)
        if len(historical_data) > 0:
            atl = historical_data['low'].min()
            if atl < d_price:
                candidate_targets.append(("Historical ATL", atl))

            # Major support levels (bottom 3 swing lows in history)
            major_lows = self._find_major_levels(historical_data, is_high=False, count=3)
            for i, level in enumerate(major_lows):
                if level < d_price:
                    candidate_targets.append((f"Major Support {i+1}", level))

        # 4. Incorporate Mitch's external structure if below our extensions
        if mitch_targets.final and mitch_targets.final < fib_2000:
            candidate_targets.append(("Mitch Final", mitch_targets.final))

        # Filter targets below entry and sort by price (descending)
        valid_targets = [(name, price) for name, price in candidate_targets if price < d_price]
        valid_targets.sort(key=lambda x: x[1], reverse=True)

        # Select targets
        if len(valid_targets) >= 3:
            primary_idx = min(2, len(valid_targets) - 1)
            primary = valid_targets[primary_idx][1]
            primary_name = valid_targets[primary_idx][0]

            secondary_idx = min(4, len(valid_targets) - 1)
            secondary = valid_targets[secondary_idx][1]
            secondary_name = valid_targets[secondary_idx][0]

            final_idx = min(6, len(valid_targets) - 1)
            final = valid_targets[final_idx][1]
            final_name = valid_targets[final_idx][0]

            desc = (f"Position Strategy: {primary_name} @ {primary:.2f} "
                   f"→ {secondary_name} @ {secondary:.2f} "
                   f"→ {final_name} @ {final:.2f}")
        else:
            # Fallback to basic Fibonacci extensions
            primary = fib_1618
            secondary = fib_2618
            final = fib_3618
            primary_name = "Fib 1.618"
            secondary_name = "Fib 2.618"
            final_name = "Fib 3.618"
            desc = f"Position Strategy: Fib 1.618 @ {primary:.2f} → Fib 2.618 @ {secondary:.2f} → Fib 3.618 @ {final:.2f}"

        return TPTargets(
            primary=primary,
            secondary=secondary,
            final=final,
            description=desc,
            tp_strategy_used=mitch_targets.tp_strategy_used if hasattr(mitch_targets, 'tp_strategy_used') and mitch_targets.tp_strategy_used else "Combined",
            target_details=(primary_name, secondary_name, final_name),
        )

    def _find_major_levels(self, data: pd.DataFrame, is_high: bool, count: int = 3) -> List[float]:
        """
        Find major support/resistance levels using volume-weighted approach.

        Args:
            data: Historical price data
            is_high: True for resistance levels, False for support levels
            count: Number of levels to return

        Returns:
            List of major price levels sorted by significance
        """
        if len(data) < 20:
            return []

        # Use a larger window for major levels
        window = max(10, len(data) // 20)
        levels = []

        if is_high:
            prices = data['high'].values
        else:
            prices = data['low'].values

        # Find swing points with larger window
        for i in range(window, len(data) - window):
            if is_high:
                if prices[i] == max(prices[i - window:i + window + 1]):
                    levels.append(prices[i])
            else:
                if prices[i] == min(prices[i - window:i + window + 1]):
                    levels.append(prices[i])

        # Return top N levels
        if is_high:
            levels.sort(reverse=True)
        else:
            levels.sort()

        return levels[:count]

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
                           min_allowed_stop_loss_pct: float = None) -> float:
        """
        Calculate stop loss using Mitch Ray's external market structure approach.
        Position strategy delegates to MitchStrategy for stop loss calculation.

        Args:
            See base class for parameter descriptions

        Returns:
            Stop loss price
        """
        # Delegate to Mitch's stop loss calculation
        return self.mitch_strategy.calculate_stop_loss(
            pattern_high=pattern_high,
            pattern_low=pattern_low,
            is_bullish=is_bullish,
            price_data=price_data,
            x_price=x_price,
            a_price=a_price,
            b_price=b_price,
            c_price=c_price,
            d_price=d_price,
            d_index=d_index,
            max_allowed_stop_loss_pct=max_allowed_stop_loss_pct,
            min_allowed_stop_loss_pct=min_allowed_stop_loss_pct
        )

    def get_strategy_name(self) -> str:
        return "POSITION"
