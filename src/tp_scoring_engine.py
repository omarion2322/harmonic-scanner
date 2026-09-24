"""
Take-Profit (TP) Scoring Engine

Identifies and ranks optimal exit zones based on historical price action and market structure.
Uses trendln for swing detection and implements a 5-component scoring system.

Core Principles:
- TP zones are areas of prior participation, not theoretical projections
- Exits prioritize liquidity, memory, and reaction probability
- Precision entries ≠ precision exits → use zones, not single prices
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime
from tp_strategies.base import TPTargets


@dataclass
class TPZone:
    """Represents a Take-Profit zone with scoring."""
    price_center: float
    price_min: float
    price_max: float
    score: float
    tier: str  # TP1, TP2, TP3, or IGNORE
    direction: str  # LONG or SHORT

    # Scoring components
    touch_score: float
    volume_score: float
    reaction_score: float
    recency_score: float
    alignment_score: float

    # Metadata
    touch_count: int
    last_touch_bars_ago: int
    zone_type: str  # e.g., "Swing High", "Support", "Resistance", "HVN"

    def __repr__(self):
        return (f"TPZone(price={self.price_center:.2f}, score={self.score:.1f}, "
                f"tier={self.tier}, type={self.zone_type})")


class TPScoringEngine:
    """
    Take-Profit Scoring Engine

    Identifies optimal exit zones using market structure and historical price action.
    """

    def __init__(self, df: pd.DataFrame, atr_period: int = 14):
        """
        Initialize TP Scoring Engine.

        Args:
            df: Price dataframe with OHLCV data (lowercase columns)
            atr_period: Period for ATR calculation
        """
        self.df = df.copy()
        self.atr_period = atr_period

        # Handle MultiIndex columns from yfinance
        if isinstance(self.df.columns, pd.MultiIndex):
            self.df.columns = self.df.columns.get_level_values(0)

        # Ensure lowercase column names
        self.df.columns = [col.lower() for col in self.df.columns]

        # Calculate ATR
        self._calculate_atr()

        # Detect swings using trendln
        self.swing_highs, self.swing_lows = self._detect_swings()

        # Identify support/resistance zones
        self.resistance_zones = []
        self.support_zones = []
        self._identify_sr_zones()

    def _calculate_atr(self):
        """Calculate Average True Range."""
        high = self.df['high']
        low = self.df['low']
        close = self.df['close']

        # True Range
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        self.df['atr'] = tr.rolling(window=self.atr_period, min_periods=1).mean()

    def _detect_swings(self) -> Tuple[pd.Series, pd.Series]:
        """
        Detect swing highs and swing lows using scipy.

        IMPROVED: Uses order=2 instead of order=5 to catch more swing points,
        especially in consolidation zones. This helps identify support/resistance
        areas where price oscillates rather than forming sharp V-shaped pivots.

        Returns:
            Tuple of (swing_highs, swing_lows) as boolean Series
        """
        try:
            from scipy.signal import argrelextrema

            # FIXED: Reduced from order=5 to order=2
            # order=5 was too strict and missed consolidation zones
            # order=2 catches more swing points while still filtering noise
            swing_order = 2

            # Find local maxima (swing highs)
            high_indices = argrelextrema(
                self.df['high'].values,
                np.greater,
                order=swing_order
            )[0]

            # Find local minima (swing lows)
            low_indices = argrelextrema(
                self.df['low'].values,
                np.less,
                order=swing_order
            )[0]

            # Convert to boolean Series
            swing_highs = pd.Series(False, index=self.df.index)
            swing_lows = pd.Series(False, index=self.df.index)

            swing_highs.iloc[high_indices] = True
            swing_lows.iloc[low_indices] = True

            return swing_highs, swing_lows

        except Exception as e:
            print(f"Warning: Swing detection failed: {e}")
            # Fallback: return empty Series
            return pd.Series(False, index=self.df.index), pd.Series(False, index=self.df.index)

    def _identify_sr_zones(self):
        """Identify support and resistance zones from swing points."""
        # Get swing high prices
        swing_high_prices = self.df.loc[self.swing_highs, 'high'].values
        swing_high_indices = self.df.loc[self.swing_highs].index

        # Get swing low prices
        swing_low_prices = self.df.loc[self.swing_lows, 'low'].values
        swing_low_indices = self.df.loc[self.swing_lows].index

        # Cluster nearby swing highs into resistance zones
        self.resistance_zones = self._cluster_levels(
            swing_high_prices,
            swing_high_indices,
            zone_type='Resistance'
        )

        # Cluster nearby swing lows into support zones
        self.support_zones = self._cluster_levels(
            swing_low_prices,
            swing_low_indices,
            zone_type='Support'
        )

    def _cluster_levels(self, prices: np.ndarray, indices, zone_type: str,
                       cluster_tolerance: float = 0.05) -> List[Dict]:
        """
        Cluster nearby price levels into zones.

        IMPROVED: Increased tolerance from 2% to 5% to better capture
        consolidation zones and support/resistance areas.

        Args:
            prices: Array of price levels
            indices: Corresponding dataframe indices
            zone_type: 'Support' or 'Resistance'
            cluster_tolerance: Percentage tolerance for clustering (default 5%)

        Returns:
            List of zone dictionaries
        """
        if len(prices) == 0:
            return []

        zones = []
        sorted_indices = np.argsort(prices)
        sorted_prices = prices[sorted_indices]
        sorted_df_indices = [indices[i] for i in sorted_indices]

        current_cluster = [sorted_prices[0]]
        current_indices = [sorted_df_indices[0]]

        for i in range(1, len(sorted_prices)):
            # Check if price is within cluster tolerance
            cluster_mean = np.mean(current_cluster)
            if abs(sorted_prices[i] - cluster_mean) / cluster_mean <= cluster_tolerance:
                current_cluster.append(sorted_prices[i])
                current_indices.append(sorted_df_indices[i])
            else:
                # Save current cluster and start new one
                # IMPROVED: Allow single swing points (was >= 2)
                # With stricter swing detection (order=2), individual pivots are significant
                if len(current_cluster) >= 1:
                    zones.append({
                        'prices': current_cluster,
                        'indices': current_indices,
                        'type': zone_type
                    })
                current_cluster = [sorted_prices[i]]
                current_indices = [sorted_df_indices[i]]

        # Add last cluster
        # IMPROVED: Allow single swing points (was >= 2)
        if len(current_cluster) >= 1:
            zones.append({
                'prices': current_cluster,
                'indices': current_indices,
                'type': zone_type
            })

        return zones

    def calculate_tolerance(self, price: float) -> float:
        """
        Calculate zone tolerance.

        Tolerance = max(0.4%, ATR × 0.5)

        Args:
            price: Center price of zone

        Returns:
            Tolerance value
        """
        current_atr = self.df['atr'].iloc[-1]

        # 0.4% of price
        pct_tolerance = price * 0.004

        # 50% of ATR
        atr_tolerance = current_atr * 0.5

        return max(pct_tolerance, atr_tolerance)

    def calculate_touch_score(self, zone_indices: List, min_bar_separation: int = 10) -> Tuple[float, int]:
        """
        Calculate TouchScore (0-100).

        Measures how many independent reactions occurred at the zone.
        TouchScore = min(100, TouchCount × 20)

        Args:
            zone_indices: List of bar indices where zone was touched
            min_bar_separation: Minimum bars between touches to count as independent

        Returns:
            Tuple of (touch_score, valid_touch_count)
        """
        if len(zone_indices) < 2:
            return 0.0, 0

        # Sort indices
        sorted_indices = sorted([self.df.index.get_loc(idx) for idx in zone_indices])

        # Count independent touches (separated by min_bar_separation)
        valid_touches = 1  # First touch always counts
        last_touch = sorted_indices[0]

        for idx in sorted_indices[1:]:
            if idx - last_touch >= min_bar_separation:
                valid_touches += 1
                last_touch = idx

        # Score: 20 points per touch, capped at 100
        touch_score = min(100.0, valid_touches * 20)

        return touch_score, valid_touches

    def calculate_volume_score(self, price_min: float, price_max: float) -> float:
        """
        Calculate VolumeScore (0-100).

        Measures how much trading activity occurred inside the zone.
        VolumeScore = min(100, (ZoneVolume / AvgVolume) × 50)

        Args:
            price_min: Bottom of zone
            price_max: Top of zone

        Returns:
            Volume score
        """
        # Find bars where price overlapped with zone
        zone_bars = self.df[
            ((self.df['high'] >= price_min) & (self.df['low'] <= price_max))
        ]

        if len(zone_bars) == 0:
            return 0.0

        # Sum volume in zone
        zone_volume = zone_bars['volume'].sum()

        # Average volume across entire dataset
        avg_volume = self.df['volume'].mean()

        if avg_volume == 0:
            return 0.0

        # Score: normalized to 50x multiplier, capped at 100
        volume_score = min(100.0, (zone_volume / (avg_volume * len(zone_bars))) * 50)

        return volume_score

    def calculate_reaction_score(self, zone_indices: List, price_center: float) -> float:
        """
        Calculate ReactionScore (0-100).

        Measures how strongly price moved away from the zone after interaction.
        ReactionScore = min(100, (AvgReactionMove / ATR) × 40)

        Args:
            zone_indices: List of indices where zone was touched
            price_center: Center price of zone

        Returns:
            Reaction score
        """
        if len(zone_indices) == 0:
            return 0.0

        reactions = []

        for idx in zone_indices:
            idx_loc = self.df.index.get_loc(idx)

            # Look ahead 5-20 bars to measure reaction
            if idx_loc + 20 >= len(self.df):
                continue

            # Get price movement in next 5-20 bars
            future_slice = self.df.iloc[idx_loc+1:idx_loc+21]

            # Measure max move away from zone
            max_high = future_slice['high'].max()
            min_low = future_slice['low'].min()

            # Reaction is the larger move away
            reaction_up = max_high - price_center
            reaction_down = price_center - min_low
            reaction = max(reaction_up, reaction_down)

            reactions.append(reaction)

        if len(reactions) == 0:
            return 0.0

        avg_reaction = np.mean(reactions)
        current_atr = self.df['atr'].iloc[-1]

        if current_atr == 0:
            return 0.0

        # Score: reaction relative to ATR, 40x multiplier, capped at 100
        reaction_score = min(100.0, (avg_reaction / current_atr) * 40)

        return reaction_score

    def calculate_recency_score(self, zone_indices: List, decay_rate: float = 0.4) -> Tuple[float, int]:
        """
        Calculate RecencyScore (0-100).

        Measures freshness of market memory.
        RecencyScore = max(0, 100 - BarsSinceLastTouch × DecayRate)

        Args:
            zone_indices: List of indices where zone was touched
            decay_rate: Decay per bar (0.3-0.5 recommended)

        Returns:
            Tuple of (recency_score, bars_since_last_touch)
        """
        if len(zone_indices) == 0:
            return 0.0, 999

        # Get most recent touch
        last_touch_idx = max([self.df.index.get_loc(idx) for idx in zone_indices])
        current_idx = len(self.df) - 1

        bars_since = current_idx - last_touch_idx

        # Score: decays over time
        recency_score = max(0.0, 100.0 - (bars_since * decay_rate))

        return recency_score, bars_since

    def calculate_alignment_score(self, price_center: float,
                                  harmonic_targets: Optional[List[float]] = None) -> float:
        """
        Calculate AlignmentScore (0-100).

        Measures confluence with institutional reference points.
        Additive bonuses:
        - +30: Anchored VWAP
        - +25: Major swing high/low
        - +20: Harmonic target (T1/T2/T3)
        - +15: Psychological round number

        Args:
            price_center: Center price of zone
            harmonic_targets: Optional list of harmonic pattern targets

        Returns:
            Alignment score (capped at 100)
        """
        score = 0.0

        # 1. Check for psychological round number
        # Round numbers ending in 00, 50, or at major decimal points
        if self._is_psychological_level(price_center):
            score += 15

        # 2. Check for major swing high/low
        if self._is_major_swing(price_center):
            score += 25

        # 3. Check for harmonic target alignment
        if harmonic_targets:
            for target in harmonic_targets:
                tolerance = self.calculate_tolerance(target)
                if abs(price_center - target) <= tolerance:
                    score += 20
                    break  # Only count once

        # 4. Check for VWAP alignment (if available)
        if 'vwap' in self.df.columns:
            current_vwap = self.df['vwap'].iloc[-1]
            tolerance = self.calculate_tolerance(current_vwap)
            if abs(price_center - current_vwap) <= tolerance:
                score += 30

        return min(100.0, score)

    def _is_psychological_level(self, price: float) -> bool:
        """Check if price is a psychological round number."""
        # Check for round numbers
        if price >= 100:
            # For prices >= 100, check for multiples of 50 or 100
            return (price % 100 == 0) or (price % 50 == 0)
        elif price >= 10:
            # For prices 10-100, check for multiples of 10 or 5
            return (price % 10 == 0) or (price % 5 == 0)
        else:
            # For prices < 10, check for whole numbers
            return (price % 1 == 0)

    def _is_major_swing(self, price: float, lookback: int = 100) -> bool:
        """Check if price aligns with a major swing high/low."""
        recent_data = self.df.tail(lookback)

        # Get major swing highs/lows (top 10%)
        all_highs = recent_data['high'].values
        all_lows = recent_data['low'].values

        major_high_threshold = np.percentile(all_highs, 90)
        major_low_threshold = np.percentile(all_lows, 10)

        # Check if any major swing is near this price
        major_swings = np.concatenate([
            all_highs[all_highs >= major_high_threshold],
            all_lows[all_lows <= major_low_threshold]
        ])

        tolerance = self.calculate_tolerance(price)

        for swing in major_swings:
            if abs(price - swing) <= tolerance:
                return True

        return False

    def score_zone(self, zone_data: Dict, harmonic_targets: Optional[List[float]] = None) -> TPZone:
        """
        Calculate comprehensive score for a TP zone.

        IMPROVED: Increased recency weight from 15% to 35% to prioritize recent
        support/resistance over old levels. Recent price action is more relevant
        for take profit targets than old support from years ago.

        TP_SCORE = 0.20 × TouchScore
                 + 0.20 × VolumeScore
                 + 0.15 × ReactionScore
                 + 0.35 × RecencyScore (INCREASED from 0.15)
                 + 0.10 × AlignmentScore

        Args:
            zone_data: Dictionary with 'prices', 'indices', 'type'
            harmonic_targets: Optional harmonic pattern targets for alignment

        Returns:
            TPZone object with complete scoring
        """
        prices = zone_data['prices']
        indices = zone_data['indices']
        zone_type = zone_data['type']

        # Calculate zone boundaries
        price_min = min(prices)
        price_max = max(prices)
        price_center = np.mean(prices)

        # Expand zone by tolerance
        tolerance = self.calculate_tolerance(price_center)
        price_min = price_center - tolerance
        price_max = price_center + tolerance

        # Calculate scoring components
        touch_score, touch_count = self.calculate_touch_score(indices)
        volume_score = self.calculate_volume_score(price_min, price_max)
        reaction_score = self.calculate_reaction_score(indices, price_center)
        recency_score, bars_since = self.calculate_recency_score(indices)
        alignment_score = self.calculate_alignment_score(price_center, harmonic_targets)

        # Weighted final score - IMPROVED: Recency now 35% (was 15%)
        final_score = (
            0.20 * touch_score +
            0.20 * volume_score +
            0.15 * reaction_score +
            0.35 * recency_score +
            0.10 * alignment_score
        )

        # Classify tier
        if final_score >= 80:
            tier = "TP3"
        elif final_score >= 65:
            tier = "TP2"
        elif final_score >= 50:
            tier = "TP1"
        else:
            tier = "IGNORE"

        # Determine direction
        current_price = self.df['close'].iloc[-1]
        if price_center > current_price:
            direction = "LONG"
        else:
            direction = "SHORT"

        return TPZone(
            price_center=price_center,
            price_min=price_min,
            price_max=price_max,
            score=final_score,
            tier=tier,
            direction=direction,
            touch_score=touch_score,
            volume_score=volume_score,
            reaction_score=reaction_score,
            recency_score=recency_score,
            alignment_score=alignment_score,
            touch_count=touch_count,
            last_touch_bars_ago=bars_since,
            zone_type=zone_type
        )

    def get_tp_zones(self, entry_price: float, direction: str,
                     harmonic_targets: Optional[List[float]] = None) -> List[TPZone]:
        """
        Get ranked TP zones for a trade.

        Args:
            entry_price: Trade entry price
            direction: 'LONG' or 'SHORT'
            harmonic_targets: Optional harmonic pattern targets for alignment

        Returns:
            List of TPZone objects, sorted by score (highest first)
        """
        all_zones = []

        # Choose appropriate zones based on direction
        if direction == "LONG":
            # For LONG trades, only consider resistance zones ABOVE entry
            candidate_zones = [z for z in self.resistance_zones
                             if np.mean(z['prices']) > entry_price]
        else:  # SHORT
            # For SHORT trades, only consider support zones BELOW entry
            candidate_zones = [z for z in self.support_zones
                             if np.mean(z['prices']) < entry_price]

        # Score all candidate zones
        for zone_data in candidate_zones:
            tp_zone = self.score_zone(zone_data, harmonic_targets)

            # IMPROVED: Lowered threshold from 50 to 40
            # 50 was too restrictive and filtered out valid support/resistance zones
            # 40 allows more zones while still maintaining quality
            if tp_zone.score >= 40:
                all_zones.append(tp_zone)

        # Sort by score (highest first)
        all_zones.sort(key=lambda z: z.score, reverse=True)

        return all_zones

    def get_target_plan(
        self, entry_price: float, direction: str,
        harmonic_targets: Optional[List[float]] = None,
        min_spacing_pct: float = 30.0,
        min_entry_distance_pct: float = 20.0,
        atr_multiplier: float = 1.0,
        include_structure: bool = True,
    ) -> TPTargets:
        """Choose the nearest T1, then the strongest sufficiently distant zones.

        Both percentage distances use entry as their denominator, symmetrically
        for longs and shorts. A missing level remains missing, never extrapolated.
        """
        if direction not in ("LONG", "SHORT"):
            raise ValueError("TP direction must be LONG or SHORT")
        if not np.isfinite(entry_price) or entry_price <= 0:
            raise ValueError("TP entry must be a finite positive price")
        for value in (min_spacing_pct, min_entry_distance_pct, atr_multiplier):
            if not np.isfinite(value) or value <= 0:
                raise ValueError("TP spacing and ATR settings must be finite and positive")
        atr = float(self.df['atr'].iloc[-1]) if not self.df.empty else 0.0
        if not np.isfinite(atr) or atr < 0:
            raise ValueError("Cannot calculate TP spacing from invalid ATR")
        entry_gap = max(entry_price * min_entry_distance_pct / 100, atr * atr_multiplier)
        target_gap = max(entry_price * min_spacing_pct / 100, atr * atr_multiplier)
        sign = 1 if direction == "LONG" else -1
        # price, lower/upper zone edges, source label
        selected: List[Tuple[float, float, float, str]] = []

        def qualifies(price: float, low: float, high: float) -> bool:
            if not all(np.isfinite(v) for v in (price, low, high)) or price <= 0:
                raise ValueError("TP candidates must have finite bounds and positive prices")
            required_distance = entry_gap
            if selected:
                required_distance = sign * (selected[-1][0] - entry_price) + target_gap
            distance = sign * (price - entry_price)
            if distance < required_distance and not np.isclose(
                distance, required_distance, rtol=1e-12, atol=1e-12
            ):
                return False
            for _, other_low, other_high, _ in selected:
                if low < other_high and high > other_low:
                    return False
            return True

        zones = (
            self.get_tp_zones(entry_price, direction, harmonic_targets)
            if include_structure else []
        )
        projections = sorted(
            enumerate(harmonic_targets or []), key=lambda item: sign * item[1]
        )
        for slot in range(3):
            eligible = [
                zone for zone in zones
                if qualifies(zone.price_center, zone.price_min, zone.price_max)
            ]
            if eligible:
                if slot == 0:
                    zone = min(eligible, key=lambda z: sign * z.price_center)
                else:
                    zone = min(eligible, key=lambda z: (-z.score, sign * z.price_center))
                selected.append((
                    float(zone.price_center), zone.price_min, zone.price_max,
                    f"Structure ({zone.zone_type}, score {zone.score:.0f})",
                ))
                continue
            # Projections must meet the same rung and spacing requirements.
            # Never insert one before an already selected structural target.
            fallback = next(
                ((index, price) for index, price in projections if qualifies(price, price, price)),
                None,
            )
            if fallback is None:
                break
            index, price = fallback
            label = ("38.2%", "61.8%", "100%")[index] if index < 3 else str(index + 1)
            selected.append((float(price), price, price, f"Fibonacci {label} (projection)"))

        prices: List[Optional[float]] = [candidate[0] for candidate in selected]
        prices.extend([None] * (3 - len(selected)))
        provenance = "; ".join(
            f"T{i}: {candidate[3]}" for i, candidate in enumerate(selected, 1)
        )
        description = "; ".join(
            f"T{i} @ {candidate[0]:.2f}: {candidate[3]}"
            for i, candidate in enumerate(selected, 1)
        )
        target_details: List[Optional[str]] = []
        for candidate in selected:
            detail = candidate[3]
            if detail.startswith("Structure (") and detail.endswith(")"):
                detail = detail[len("Structure ("):-1]
            target_details.append(detail)
        target_details.extend([None] * (3 - len(target_details)))
        return TPTargets(
            primary=prices[0], secondary=prices[1], final=prices[2],
            description=description or "No targets meet the distance and spacing requirements",
            tp_strategy_used=provenance or "No qualifying targets",
            target_details=tuple(target_details),
        )

    def get_optimal_targets(
        self, entry_price: float, direction: str,
        harmonic_targets: Optional[List[float]] = None,
        min_spacing_pct: float = 30.0,
        min_entry_distance_pct: float = 20.0,
        atr_multiplier: float = 1.0,
    ) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """Return available targets in order, with absent suffixes left as None."""
        plan = self.get_target_plan(
            entry_price, direction, harmonic_targets, min_spacing_pct,
            min_entry_distance_pct, atr_multiplier,
        )
        return plan.primary, plan.secondary, plan.final


def test_tp_scoring():
    """Test the TP scoring engine with sample data."""
    from data_downloader import download_stock_data

    print("Testing TP Scoring Engine...")
    print("="*80)

    # Download sample data
    ticker = "AAPL"
    df = download_stock_data(ticker, period="1y", interval="1d")

    # Ensure columns are lowercase
    df.columns = [col.lower() for col in df.columns]

    # Initialize engine
    engine = TPScoringEngine(df)

    print(f"\nAnalyzing {ticker}...")
    print(f"Data period: {df.index[0]} to {df.index[-1]}")
    print(f"Swing highs detected: {engine.swing_highs.sum()}")
    print(f"Swing lows detected: {engine.swing_lows.sum()}")
    print(f"Resistance zones: {len(engine.resistance_zones)}")
    print(f"Support zones: {len(engine.support_zones)}")

    # Test LONG trade
    entry_price = df['close'].iloc[-1]
    print(f"\n{'='*80}")
    print(f"LONG TRADE EXAMPLE (Entry: ${entry_price:.2f})")
    print(f"{'='*80}")

    long_zones = engine.get_tp_zones(entry_price, "LONG")

    if long_zones:
        print(f"\nFound {len(long_zones)} valid TP zones:")
        for i, zone in enumerate(long_zones[:5], 1):
            print(f"\n{i}. {zone}")
            print(f"   Price Range: ${zone.price_min:.2f} - ${zone.price_max:.2f}")
            print(f"   Component Scores:")
            print(f"     Touch:     {zone.touch_score:5.1f} ({zone.touch_count} touches)")
            print(f"     Volume:    {zone.volume_score:5.1f}")
            print(f"     Reaction:  {zone.reaction_score:5.1f}")
            print(f"     Recency:   {zone.recency_score:5.1f} ({zone.last_touch_bars_ago} bars ago)")
            print(f"     Alignment: {zone.alignment_score:5.1f}")

        # Get optimal targets
        tp1, tp2, tp3 = engine.get_optimal_targets(entry_price, "LONG")
        print(f"\n{'='*80}")
        print("OPTIMAL TARGETS:")
        print(f"  TP1: ${tp1:.2f}" if tp1 else "  TP1: Not available")
        print(f"  TP2: ${tp2:.2f}" if tp2 else "  TP2: Not available")
        print(f"  TP3: ${tp3:.2f}" if tp3 else "  TP3: Not available")
    else:
        print("\nNo valid TP zones found above entry price.")

    print(f"\n{'='*80}\n")


if __name__ == "__main__":
    test_tp_scoring()
