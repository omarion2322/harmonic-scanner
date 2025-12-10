"""
MITCH Take Profit Strategy

Mitch Ray's External Market Structure approach.
Focuses on measured moves, previous support/resistance levels,
and broader market context (moving averages, trendlines).

ENHANCED Strategy (v2.0):
- Uses FULL stock/ETF history (up to 20 years) for comprehensive S/R analysis
- Identifies CLUSTERED support/resistance levels (multiple touches = stronger levels)
- Calculates measured moves from COHERENT swing pairs (actual price movements)
- Adds pattern-based Fibonacci extensions (127.2%, 161.8%)
- Enforces minimum target distance (2% from entry) to filter noise
- Ensures proper spacing between targets (1.5% minimum gap)
- Strength-weighted target selection (prioritizes most significant levels)

Key Improvements Over v1.0:
1. Fixed measured move calculation - now uses actual swing pairs instead of cherry-picked extremes
2. Added clustering algorithm for S/R - identifies levels tested multiple times
3. Minimum distance filtering - rejects targets too close to entry
4. Target spacing requirements - ensures meaningful profit gradations
5. Full historical analysis - uses entire stock history, not just DATA_PERIOD

Targets are adaptive, strength-weighted, and based on comprehensive market structure.
"""

from tp_strategies.base import TPStrategy, TPTargets
import pandas as pd
import numpy as np
from typing import List, Tuple


class MitchStrategy(TPStrategy):
    """
    Mitch Ray's External Market Structure strategy.

    Analyzes price action outside the harmonic pattern to identify
    realistic profit targets based on historical support/resistance,
    measured moves, and moving averages.
    """

    def __init__(self, swing_window: int = 5):
        """
        Initialize Mitch strategy.

        Args:
            swing_window: Window size for swing point detection (from config SWING_WINDOW)
                         This uses the entire stock history available in price_data
        """
        self.swing_window = swing_window

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
        Calculate targets based on external market structure.

        Analyzes historical data to find:
        1. Previous swing highs/lows as support/resistance
        2. Measured moves from recent price swings
        3. Key moving average levels (20, 50, 200 SMA)

        Uses ALL available historical data up to point D to find the most
        meaningful support/resistance levels across the entire stock history.
        """
        # Use ALL historical data up to point D for maximum context
        historical_data = price_data.iloc[:d_index + 1].copy()

        if len(historical_data) < 20:
            # Not enough data, fallback to simple pattern-based targets
            return self._fallback_targets(pattern_high, pattern_low, is_bullish)

        # Calculate moving averages for dynamic support/resistance
        ma_20 = historical_data['close'].rolling(20).mean().iloc[-1] if len(historical_data) >= 20 else None
        ma_50 = historical_data['close'].rolling(50).mean().iloc[-1] if len(historical_data) >= 50 else None

        # Find significant swing highs and lows outside the pattern
        swing_highs, swing_lows = self._find_swing_points(historical_data, window=self.swing_window)

        if is_bullish:
            targets = self._calculate_bullish_targets(
                d_price, pattern_high, pattern_low,
                swing_highs, swing_lows, ma_20, ma_50
            )
        else:
            targets = self._calculate_bearish_targets(
                d_price, pattern_high, pattern_low,
                swing_highs, swing_lows, ma_20, ma_50
            )

        return targets

    def _find_swing_points(self, data: pd.DataFrame, window: int) -> Tuple[List[float], List[float]]:
        """
        Identify significant swing highs and lows in the historical data.

        Args:
            data: Price DataFrame with high/low columns (lowercase)
            window: Window size for swing detection (from config SWING_WINDOW)

        Returns:
            Tuple of (swing_highs, swing_lows) lists
        """
        swing_highs = []
        swing_lows = []

        highs = data['high'].values
        lows = data['low'].values

        for i in range(window, len(data) - window):
            # Check for swing high
            if highs[i] == max(highs[i - window:i + window + 1]):
                swing_highs.append(highs[i])

            # Check for swing low
            if lows[i] == min(lows[i - window:i + window + 1]):
                swing_lows.append(lows[i])

        return swing_highs, swing_lows

    def _calculate_bullish_targets(self,
                                   d_price: float,
                                   pattern_high: float,
                                   pattern_low: float,
                                   swing_highs: List[float],
                                   swing_lows: List[float],
                                   ma_20: float,
                                   ma_50: float) -> TPTargets:
        """Calculate targets for bullish patterns using external structure."""
        # FIXED: Increased from 2% to 10% to match harmonic pattern completion behavior
        # Harmonic patterns typically complete with 30-100%+ gains, not 2-5%
        MIN_TARGET_DISTANCE_PCT = 10.0  # T1 must be at least 10% above entry
        # FIXED: Reduced from 33% to 29% for proper absolute percentage spacing
        # If T1 @ 15%, then T2 @ ~48% (15% * 1.29 ≈ 48%), T3 @ ~91% (48% * 1.29 ≈ 91%)
        MIN_TARGET_SPACING_PCT = 29.0  # Minimum gap between targets (29% for meaningful gradation)

        min_target_price = d_price * (1 + MIN_TARGET_DISTANCE_PCT / 100)

        # Collect all potential targets with strength scores
        target_candidates = []  # List of (name, price, strength_score)

        # 1. Find CLUSTERED resistance levels (stronger levels with multiple touches)
        resistance_clusters = self._find_resistance_clusters(swing_highs, d_price, is_above=True)
        for i, (price, strength) in enumerate(resistance_clusters[:5]):  # Top 5 strongest
            if price > min_target_price:
                target_candidates.append((f"Resistance Cluster {i+1}", price, strength))

        # 2. Calculate measured move using COHERENT swing pairs
        measured_moves = self._calculate_measured_moves(swing_highs, swing_lows, d_price, is_bullish=True)
        for i, (price, swing_size) in enumerate(measured_moves[:3]):  # Top 3 largest swings
            if price > min_target_price:
                # Strength score based on swing magnitude
                strength = swing_size / d_price  # Relative swing size
                target_candidates.append((f"Measured Move {i+1}", price, strength))

        # 3. Add moving averages with moderate strength (only if meaningful distance)
        if ma_20 and ma_20 > min_target_price:
            # 20 SMA gets lower priority (strength 0.5)
            target_candidates.append(("20 SMA", ma_20, 0.5))
        if ma_50 and ma_50 > min_target_price:
            # 50 SMA gets moderate priority (strength 1.0)
            target_candidates.append(("50 SMA", ma_50, 1.0))

        # 4. Add pattern projection targets (fibonacci extensions from pattern range)
        pattern_range = pattern_high - pattern_low
        fib_127 = d_price + (pattern_range * 1.272)  # 127.2% extension
        fib_161 = d_price + (pattern_range * 1.618)  # 161.8% extension
        if fib_127 > min_target_price:
            target_candidates.append(("127% Pattern Extension", fib_127, 1.5))
        if fib_161 > min_target_price:
            target_candidates.append(("161% Pattern Extension", fib_161, 2.0))

        # 5. Sort by strength score (descending), then filter for spacing
        target_candidates.sort(key=lambda x: x[2], reverse=True)

        # 6. Select top 3 targets ensuring proper spacing
        selected_targets = self._select_spaced_targets(
            target_candidates,
            d_price,
            MIN_TARGET_SPACING_PCT,
            max_targets=3
        )

        if len(selected_targets) >= 3:
            primary = selected_targets[0][1]
            secondary = selected_targets[1][1]
            final = selected_targets[2][1]
            desc = f"Mitch Ray: {selected_targets[0][0]} @ {primary:.2f}, {selected_targets[1][0]} @ {secondary:.2f}, {selected_targets[2][0]} @ {final:.2f}"
        elif len(selected_targets) == 2:
            primary = selected_targets[0][1]
            secondary = selected_targets[1][1]
            # Use highest reasonable target for final
            final = max(pattern_high, fib_127) if fib_127 > secondary else pattern_high
            desc = f"Mitch Ray: {selected_targets[0][0]} @ {primary:.2f}, {selected_targets[1][0]} @ {secondary:.2f}, Extension @ {final:.2f}"
        elif len(selected_targets) == 1:
            primary = selected_targets[0][1]
            # Calculate reasonable secondary and final based on pattern
            secondary = d_price + (pattern_range * 0.75)
            final = max(pattern_high, fib_127)
            desc = f"Mitch Ray: {selected_targets[0][0]} @ {primary:.2f}, 75% Pattern @ {secondary:.2f}, Extension @ {final:.2f}"
        else:
            # No external structure found, use pattern-based fallback
            return self._fallback_targets(pattern_high, pattern_low, is_bullish=True)

        return TPTargets(
            primary=primary,
            secondary=secondary,
            final=final,
            description=desc
        )

    def _calculate_bearish_targets(self,
                                   d_price: float,
                                   pattern_high: float,
                                   pattern_low: float,
                                   swing_highs: List[float],
                                   swing_lows: List[float],
                                   ma_20: float,
                                   ma_50: float) -> TPTargets:
        """Calculate targets for bearish patterns using external structure."""
        # For bearish: minimum distance from entry (15% minimum, not 33% - targets go toward zero)
        MIN_TARGET_DISTANCE_PCT = 15.0  # T1 must be at least 15% below entry
        MIN_TARGET_SPACING_PCT = 10.0  # 10% gap between targets (not 33% - would reach zero too fast)
        MAX_DOWNSIDE_PCT = 70.0  # Maximum realistic downside - filters out extreme/old support levels

        max_target_price = d_price * (1 - MIN_TARGET_DISTANCE_PCT / 100)
        min_realistic_target = d_price * (1 - MAX_DOWNSIDE_PCT / 100)  # Floor at 30% of entry price

        # Collect all potential targets with strength scores
        target_candidates = []  # List of (name, price, strength_score)

        # 1. Find CLUSTERED support levels (stronger levels with multiple touches)
        # Filter out extreme/penny-stock support levels using min_realistic_target
        support_clusters = self._find_resistance_clusters(swing_lows, d_price, is_above=False)
        for i, (price, strength) in enumerate(support_clusters[:10]):  # Check top 10
            # Must be below max_target_price AND above min_realistic_target (within 70% downside)
            if price < max_target_price and price >= min_realistic_target:
                target_candidates.append((f"Support Cluster {i+1}", price, strength))

        # 2. Calculate measured move using COHERENT swing pairs
        measured_moves = self._calculate_measured_moves(swing_highs, swing_lows, d_price, is_bullish=False)
        for i, (price, swing_size) in enumerate(measured_moves[:3]):  # Top 3 largest swings
            # Apply same realistic bounds
            if price < max_target_price and price >= min_realistic_target:
                # Strength score based on swing magnitude
                strength = swing_size / d_price  # Relative swing size
                target_candidates.append((f"Measured Move {i+1}", price, strength))

        # 3. Add moving averages with moderate strength (only if meaningful distance)
        if ma_20 and ma_20 < max_target_price and ma_20 >= min_realistic_target:
            # 20 SMA gets lower priority (strength 0.5)
            target_candidates.append(("20 SMA", ma_20, 0.5))
        if ma_50 and ma_50 < max_target_price and ma_50 >= min_realistic_target:
            # 50 SMA gets moderate priority (strength 1.0)
            target_candidates.append(("50 SMA", ma_50, 1.0))

        # 4. Add pattern projection targets (fibonacci extensions from D to pattern low)
        # For bearish, use the expected move from D to pattern_low, not full pattern range
        pattern_range = pattern_high - pattern_low
        expected_move = d_price - pattern_low  # Distance from entry to pattern low

        # Extensions should project the expected move, with realistic minimum boundary
        fib_127 = max(d_price - (expected_move * 1.272), min_realistic_target)  # 127.2% of expected move
        fib_161 = max(d_price - (expected_move * 1.618), min_realistic_target)  # 161.8% of expected move

        # Only add if within realistic range (not too extreme)
        if fib_127 < max_target_price and fib_127 >= min_realistic_target:
            target_candidates.append(("127% Pattern Extension", fib_127, 1.5))
        if fib_161 < max_target_price and fib_161 >= min_realistic_target:
            target_candidates.append(("161% Pattern Extension", fib_161, 2.0))

        # 5. Sort by strength score (descending), then filter for spacing
        target_candidates.sort(key=lambda x: x[2], reverse=True)

        # 6. Select top 3 targets ensuring proper spacing (for bearish, use negative for sorting)
        selected_targets = self._select_spaced_targets(
            target_candidates,
            d_price,
            MIN_TARGET_SPACING_PCT,
            max_targets=3,
            is_bullish=False
        )

        if len(selected_targets) >= 3:
            primary = selected_targets[0][1]
            secondary = selected_targets[1][1]
            final = selected_targets[2][1]
            desc = f"Mitch Ray: {selected_targets[0][0]} @ {primary:.2f}, {selected_targets[1][0]} @ {secondary:.2f}, {selected_targets[2][0]} @ {final:.2f}"
        elif len(selected_targets) == 2:
            primary = selected_targets[0][1]
            secondary = selected_targets[1][1]
            # Use lowest reasonable target for final (ensure above min_realistic_target)
            final = max(min(pattern_low, fib_127), min_realistic_target) if fib_127 < secondary and fib_127 >= min_realistic_target else max(pattern_low, min_realistic_target)
            desc = f"Mitch Ray: {selected_targets[0][0]} @ {primary:.2f}, {selected_targets[1][0]} @ {secondary:.2f}, Extension @ {final:.2f}"
        elif len(selected_targets) == 1:
            primary = selected_targets[0][1]
            # Calculate reasonable secondary and final based on pattern (ensure above min_realistic_target)
            secondary = max(d_price - (expected_move * 0.75), min_realistic_target)
            final = max(min(pattern_low, fib_127), min_realistic_target) if fib_127 >= min_realistic_target else max(pattern_low, min_realistic_target)
            desc = f"Mitch Ray: {selected_targets[0][0]} @ {primary:.2f}, 75% Pattern @ {secondary:.2f}, Extension @ {final:.2f}"
        else:
            # No external structure found, use pattern-based fallback
            return self._fallback_targets(pattern_high, pattern_low, is_bullish=False)

        return TPTargets(
            primary=primary,
            secondary=secondary,
            final=final,
            description=desc
        )

    def _fallback_targets(self, pattern_high: float, pattern_low: float, is_bullish: bool) -> TPTargets:
        """
        Fallback to simple pattern-based targets when insufficient external structure.

        Uses 50% and 75% of pattern range as conservative approximations.
        """
        pattern_range = pattern_high - pattern_low

        if is_bullish:
            primary = pattern_low + (pattern_range * 0.5)
            secondary = pattern_low + (pattern_range * 0.75)
            final = pattern_high
        else:
            primary = pattern_high - (pattern_range * 0.5)
            secondary = pattern_high - (pattern_range * 0.75)
            final = pattern_low

        description = f"Mitch Ray (Fallback): 50% @ {primary:.2f}, 75% @ {secondary:.2f}, 100% @ {final:.2f}"

        return TPTargets(
            primary=primary,
            secondary=secondary,
            final=final,
            description=description
        )

    def _find_resistance_clusters(self,
                                  swing_points: List[float],
                                  d_price: float,
                                  is_above: bool) -> List[Tuple[float, int]]:
        """
        Find clustered support/resistance levels with strength scores.

        Args:
            swing_points: List of swing high or low prices
            d_price: Entry price (point D)
            is_above: True to find levels above D, False for below D

        Returns:
            List of (price, strength) tuples sorted by strength (descending)
            Strength = number of times the level was touched
        """
        if is_above:
            candidates = [p for p in swing_points if p > d_price]
        else:
            candidates = [p for p in swing_points if p < d_price]

        if len(candidates) == 0:
            return []

        # Find clusters using 2% tolerance
        cluster_tolerance = 0.02
        clusters = []
        used = set()

        for i, price in enumerate(candidates):
            if i in used:
                continue

            # Find all prices within 2% of this price
            cluster = []
            for j, other_price in enumerate(candidates):
                if j not in used and abs(other_price - price) / price <= cluster_tolerance:
                    cluster.append(other_price)
                    used.add(j)

            if cluster:
                avg_price = sum(cluster) / len(cluster)
                strength = len(cluster)  # Number of touches
                clusters.append((avg_price, strength))

        # Sort by strength (descending), then by distance from D (prefer closer)
        clusters.sort(key=lambda x: (-x[1], abs(x[0] - d_price)))

        return clusters

    def _calculate_measured_moves(self,
                                  swing_highs: List[float],
                                  swing_lows: List[float],
                                  d_price: float,
                                  is_bullish: bool) -> List[Tuple[float, float]]:
        """
        Calculate measured moves using COHERENT swing pairs (actual swing movements).

        Args:
            swing_highs: List of swing high prices
            swing_lows: List of swing low prices
            d_price: Entry price (point D)
            is_bullish: True for bullish patterns, False for bearish

        Returns:
            List of (projected_price, swing_size) tuples sorted by swing_size (descending)
        """
        if len(swing_highs) < 1 or len(swing_lows) < 1:
            return []

        # Find recent coherent swing pairs (up-down or down-up movements)
        # Look at last 10 swings of each type
        recent_highs = swing_highs[-10:] if len(swing_highs) >= 10 else swing_highs
        recent_lows = swing_lows[-10:] if len(swing_lows) >= 10 else swing_lows

        swing_ranges = []

        # For each recent high, find the nearest low before and after it
        for high in recent_highs:
            # Find lows below this high
            lower_lows = [low for low in recent_lows if low < high]
            if lower_lows:
                # Get the closest low (largest low below this high)
                nearest_low = max(lower_lows)
                swing_range = high - nearest_low
                swing_ranges.append(swing_range)

        if not swing_ranges:
            return []

        # Sort swing ranges by size (largest first)
        swing_ranges.sort(reverse=True)

        # Project the top 3 swing ranges from D
        measured_moves = []
        for swing_range in swing_ranges[:3]:
            if is_bullish:
                projected_price = d_price + swing_range
            else:
                # For bearish, ensure we don't project below zero
                # Cap swing_range at 90% of entry price (realistic maximum downside)
                safe_swing_range = min(swing_range, d_price * 0.90)
                projected_price = d_price - safe_swing_range

                # Additional safety: ensure positive price
                if projected_price <= 0:
                    continue  # Skip this measured move

            measured_moves.append((projected_price, swing_range if is_bullish else safe_swing_range))

        return measured_moves

    def _select_spaced_targets(self,
                               target_candidates: List[Tuple[str, float, float]],
                               d_price: float,
                               min_spacing_pct: float,
                               max_targets: int = 3,
                               is_bullish: bool = True) -> List[Tuple[str, float]]:
        """
        Select targets ensuring proper spacing between them.

        Args:
            target_candidates: List of (name, price, strength) tuples sorted by strength
            d_price: Entry price
            min_spacing_pct: Minimum percentage spacing between targets
            max_targets: Maximum number of targets to select
            is_bullish: True for bullish patterns

        Returns:
            List of (name, price) tuples with proper spacing
        """
        if not target_candidates:
            return []

        selected = []
        last_price = d_price

        for name, price, strength in target_candidates:
            if len(selected) >= max_targets:
                break

            # Calculate spacing from last selected target (or entry)
            spacing_pct = abs(price - last_price) / last_price * 100

            # For the first target, just check minimum distance from entry
            if len(selected) == 0:
                if spacing_pct >= min_spacing_pct:
                    selected.append((name, price))
                    last_price = price
            else:
                # For subsequent targets, ensure minimum spacing from last target
                if spacing_pct >= min_spacing_pct:
                    selected.append((name, price))
                    last_price = price

        # Sort selected targets by price (ascending for bullish, descending for bearish)
        if is_bullish:
            selected.sort(key=lambda x: x[1])
        else:
            selected.sort(key=lambda x: x[1], reverse=True)

        return selected

    def _find_strongest_support_resistance(self,
                                           swing_highs: List[float],
                                           swing_lows: List[float],
                                           d_price: float,
                                           is_bullish: bool) -> float:
        """
        Find the strongest support/resistance level based on clustering.

        A strong level is one where multiple swing points cluster together,
        indicating the price has tested this level multiple times.

        Args:
            swing_highs: List of swing high prices
            swing_lows: List of swing low prices
            d_price: Entry price (point D)
            is_bullish: True for bullish pattern

        Returns:
            Strongest support/resistance price, or None if not found
        """
        # For bullish, we need support levels (swing lows below D)
        # For bearish, we need resistance levels (swing highs above D)
        if is_bullish:
            candidates = [low for low in swing_lows if low < d_price]
        else:
            candidates = [high for high in swing_highs if high > d_price]

        if len(candidates) == 0:
            return None

        # Find clusters of swing points (levels that have been tested multiple times)
        # Use 2% tolerance for clustering
        cluster_tolerance = 0.02
        clusters = []

        for price in candidates:
            # Find all prices within 2% of this price
            cluster = [p for p in candidates if abs(p - price) / price <= cluster_tolerance]
            if len(cluster) >= 2:  # At least 2 touches to be considered strong
                avg_price = sum(cluster) / len(cluster)
                clusters.append((avg_price, len(cluster)))

        if not clusters:
            return None

        # Sort clusters by strength (number of touches)
        # If tied, prefer the one closer to D (most recent)
        clusters.sort(key=lambda x: (-x[1], -abs(x[0] - d_price) if is_bullish else abs(x[0] - d_price)))

        # Return the strongest cluster's average price
        return clusters[0][0]

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

        Hierarchical approach:
        1. Option A: Use most recent swing low/high (closest support/resistance)
                    - Must be within [MIN_ALLOWED_STOP_LOSS_PCT, MAX_ALLOWED_STOP_LOSS_PCT]
        2. Option A2: Use strongest support/resistance (most confirmed level)
                     - Must be within [MIN_ALLOWED_STOP_LOSS_PCT, MAX_ALLOWED_STOP_LOSS_PCT]
        3. Option B: Use MAX_ALLOWED_STOP_LOSS_PCT as fallback

        Args:
            d_price: Point D price (entry point)
            is_bullish: True for bullish pattern
            price_data: Full price history
            d_index: Index of point D
            max_allowed_stop_loss_pct: Maximum stop loss percentage from config
            min_allowed_stop_loss_pct: Minimum stop loss percentage from config

        Returns:
            Stop loss price
        """
        # Use ALL historical data up to point D
        historical_data = price_data.iloc[:d_index + 1].copy()

        # Get min_allowed from config if not provided
        if min_allowed_stop_loss_pct is None:
            import src.config as config
            min_allowed_stop_loss_pct = config.MIN_ALLOWED_STOP_LOSS_PCT if hasattr(config, 'MIN_ALLOWED_STOP_LOSS_PCT') else 3.0

        # Calculate acceptable stop loss range
        if is_bullish:
            # For bullish: stop is BELOW entry
            # min_allowed_stop is HIGHER price (tighter stop)
            # max_allowed_stop is LOWER price (wider stop)
            min_allowed_stop = d_price * (1 - min_allowed_stop_loss_pct / 100)
            max_allowed_stop = d_price * (1 - max_allowed_stop_loss_pct / 100)
        else:
            # For bearish: stop is ABOVE entry
            # min_allowed_stop is LOWER price (tighter stop)
            # max_allowed_stop is HIGHER price (wider stop)
            min_allowed_stop = d_price * (1 + min_allowed_stop_loss_pct / 100)
            max_allowed_stop = d_price * (1 + max_allowed_stop_loss_pct / 100)

        # Find swing points for analysis
        swing_highs, swing_lows = self._find_swing_points(historical_data, window=self.swing_window)

        # OPTION A: Most recent swing low/high
        if is_bullish and len(swing_lows) > 0:
            # Find swing lows below D
            candidate_lows = [low for low in swing_lows if low < d_price]
            if candidate_lows:
                # Use the highest (most recent) swing low below D
                option_a_stop = max(candidate_lows)

                # Check if within acceptable range [max_allowed_stop, min_allowed_stop]
                if max_allowed_stop <= option_a_stop <= min_allowed_stop:
                    return option_a_stop

        elif not is_bullish and len(swing_highs) > 0:
            # Find swing highs above D
            candidate_highs = [high for high in swing_highs if high > d_price]
            if candidate_highs:
                # Use the lowest (most recent) swing high above D
                option_a_stop = min(candidate_highs)

                # Check if within acceptable range [min_allowed_stop, max_allowed_stop]
                if min_allowed_stop <= option_a_stop <= max_allowed_stop:
                    return option_a_stop

        # OPTION A2: Strongest support/resistance (most confirmed level)
        strongest_level = self._find_strongest_support_resistance(
            swing_highs, swing_lows, d_price, is_bullish
        )

        if strongest_level is not None:
            # Check if within acceptable range
            if is_bullish and max_allowed_stop <= strongest_level <= min_allowed_stop:
                return strongest_level
            elif not is_bullish and min_allowed_stop <= strongest_level <= max_allowed_stop:
                return strongest_level

        # OPTION B: Fallback to MAX_ALLOWED_STOP_LOSS_PCT
        if is_bullish:
            return d_price * (1 - max_allowed_stop_loss_pct / 100)
        else:
            return d_price * (1 + max_allowed_stop_loss_pct / 100)

    def get_strategy_name(self) -> str:
        return "MITCH"
