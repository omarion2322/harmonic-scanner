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
        self.df['atr'] = tr.rolling(window=self.atr_period).mean()

    def _detect_swings(self) -> Tuple[pd.Series, pd.Series]:
        """
        Detect swing highs and swing lows using trendln.

        Returns:
            Tuple of (swing_highs, swing_lows) as boolean Series
        """
        try:
            # Use trendln to find swing points
            # minimaIdxs and maximaIdxs return indices of swing points
            from scipy.signal import argrelextrema

            # Find local maxima (swing highs)
            high_indices = argrelextrema(
                self.df['high'].values,
                np.greater,
                order=5  # Look 5 bars on each side
            )[0]

            # Find local minima (swing lows)
            low_indices = argrelextrema(
                self.df['low'].values,
                np.less,
                order=5
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
                       cluster_tolerance: float = 0.02) -> List[Dict]:
        """
        Cluster nearby price levels into zones.

        Args:
            prices: Array of price levels
            indices: Corresponding dataframe indices
            zone_type: 'Support' or 'Resistance'
            cluster_tolerance: Percentage tolerance for clustering (default 2%)

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
                if len(current_cluster) >= 2:  # Require at least 2 touches
                    zones.append({
                        'prices': current_cluster,
                        'indices': current_indices,
                        'type': zone_type
                    })
                current_cluster = [sorted_prices[i]]
                current_indices = [sorted_df_indices[i]]

        # Add last cluster
        if len(current_cluster) >= 2:
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

        TP_SCORE = 0.30 × TouchScore
                 + 0.25 × VolumeScore
                 + 0.20 × ReactionScore
                 + 0.15 × RecencyScore
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

        # Weighted final score
        final_score = (
            0.30 * touch_score +
            0.25 * volume_score +
            0.20 * reaction_score +
            0.15 * recency_score +
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

            # Only include zones with score >= 50
            if tp_zone.score >= 50:
                all_zones.append(tp_zone)

        # Sort by score (highest first)
        all_zones.sort(key=lambda z: z.score, reverse=True)

        return all_zones

    def get_optimal_targets(self, entry_price: float, direction: str,
                           harmonic_targets: Optional[List[float]] = None,
                           min_spacing_pct: float = 20.0) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """
        Get optimal TP1, TP2, TP3 targets based on scored zones.

        CRITICAL: Targets must be ordered by distance from entry:
        - LONG: TP1 < TP2 < TP3 (all above entry)
        - SHORT: TP1 > TP2 > TP3 (all below entry)

        NEW: Enforces minimum 20% spacing between targets to ensure meaningful differentiation
        NEW: Enforces minimum distance from entry for TP1:
            - LONG: 40% minimum (stocks have unlimited upside)
            - SHORT: 10% minimum (stocks can't go below $0, more conservative)

        Args:
            entry_price: Trade entry price
            direction: 'LONG' or 'SHORT'
            harmonic_targets: Optional harmonic pattern targets for alignment
            min_spacing_pct: Minimum percentage spacing between targets (default 20%)

        Returns:
            Tuple of (TP1, TP2, TP3) prices, properly ordered and spaced
        """
        # Direction-specific minimum TP1 distance from entry
        min_tp1_distance_pct = 40.0 if direction == "LONG" else 10.0

        zones = self.get_tp_zones(entry_price, direction, harmonic_targets)

        if len(zones) == 0:
            return None, None, None

        # Sort zones by DISTANCE from entry (closest to farthest)
        if direction == "LONG":
            # For LONG: sort ascending (closest resistance first)
            zones_by_distance = sorted(zones, key=lambda z: z.price_center)
        else:  # SHORT
            # For SHORT: sort descending (closest support first)
            zones_by_distance = sorted(zones, key=lambda z: z.price_center, reverse=True)

        # NEW ALGORITHM: Select targets with minimum spacing and maximum scores
        # Strategy:
        # 1. Select TP1 from zones at least min_tp1_distance_pct from entry (highest score)
        # 2. Select TP2 from zones at least min_spacing_pct away from TP1 (highest score)
        # 3. Select TP3 from zones at least min_spacing_pct away from TP2 (highest score)

        tp1 = None
        tp2 = None
        tp3 = None

        # Helper function to check if zone meets minimum spacing
        def meets_spacing(zone_price: float, reference_price: float, min_pct: float) -> bool:
            pct_diff = abs((zone_price - reference_price) / reference_price) * 100
            return pct_diff >= min_pct

        # Step 1: Select TP1 - Pick highest-scored zone that meets minimum distance from entry
        num_zones = len(zones_by_distance)
        if num_zones == 0:
            return None, None, None

        # FILTER: Only consider zones at least min_tp1_distance_pct away from entry
        # For LONG: zone must be at least 40% above entry
        # For SHORT: zone must be at least 10% below entry
        tp1_candidates = [z for z in zones_by_distance
                          if meets_spacing(z.price_center, entry_price, min_tp1_distance_pct)]

        if not tp1_candidates:
            # No zones meet minimum distance - return None to trigger fallback to fixed method
            return None, None, None

        # Pick highest-scored candidate that meets minimum distance
        tp1_zone = max(tp1_candidates, key=lambda z: z.score)
        tp1 = tp1_zone.price_center

        # Step 2: Select TP2 - Must be at least min_spacing_pct away from TP1 in the correct direction
        if direction == "LONG":
            # For LONG: TP2 must be ABOVE TP1 and at least min_spacing_pct away
            tp2_candidates = [z for z in zones_by_distance
                             if z.price_center > tp1 and meets_spacing(z.price_center, tp1, min_spacing_pct)]
        else:  # SHORT
            # For SHORT: TP2 must be BELOW TP1 and at least min_spacing_pct away
            tp2_candidates = [z for z in zones_by_distance
                             if z.price_center < tp1 and meets_spacing(z.price_center, tp1, min_spacing_pct)]

        if tp2_candidates:
            # Pick highest-scored candidate that meets spacing
            tp2_zone = max(tp2_candidates, key=lambda z: z.score)
            tp2 = tp2_zone.price_center
        else:
            # No zones meet spacing - calculate TP2 based on min_spacing_pct from TP1
            if direction == "LONG":
                tp2 = tp1 * (1 + min_spacing_pct / 100)
            else:  # SHORT
                tp2 = tp1 * (1 - min_spacing_pct / 100)

        # Step 3: Select TP3 - Must be at least min_spacing_pct away from TP2 in the correct direction
        if direction == "LONG":
            # For LONG: TP3 must be ABOVE TP2 and at least min_spacing_pct away
            tp3_candidates = [z for z in zones_by_distance
                             if z.price_center > tp2 and meets_spacing(z.price_center, tp2, min_spacing_pct)]
        else:  # SHORT
            # For SHORT: TP3 must be BELOW TP2 and at least min_spacing_pct away
            tp3_candidates = [z for z in zones_by_distance
                             if z.price_center < tp2 and meets_spacing(z.price_center, tp2, min_spacing_pct)]

        if tp3_candidates:
            # Pick highest-scored candidate that meets spacing from TP2
            tp3_zone = max(tp3_candidates, key=lambda z: z.score)
            tp3 = tp3_zone.price_center
        else:
            # No zones meet spacing - calculate TP3 based on min_spacing_pct from TP2
            if direction == "LONG":
                tp3 = tp2 * (1 + min_spacing_pct / 100)
            else:  # SHORT
                tp3 = tp2 * (1 - min_spacing_pct / 100)

        # Final validation: ensure proper ordering
        if direction == "LONG":
            # Ensure entry < T1 < T2 < T3
            if not (entry_price < tp1 < tp2 < tp3):
                # Fix ordering if broken
                all_targets = sorted([t for t in [tp1, tp2, tp3] if t is not None])
                if len(all_targets) >= 3:
                    tp1, tp2, tp3 = all_targets[0], all_targets[1], all_targets[2]
                elif len(all_targets) == 2:
                    tp1 = all_targets[0]
                    tp2 = (all_targets[0] + all_targets[1]) / 2
                    tp3 = all_targets[1]
                else:
                    # Only one target - create spacing manually
                    tp1 = entry_price * (1 + min_spacing_pct / 100)
                    tp2 = tp1 * (1 + min_spacing_pct / 100)
                    tp3 = tp2 * (1 + min_spacing_pct / 100)

        else:  # SHORT
            # Ensure entry > T1 > T2 > T3
            if not (entry_price > tp1 > tp2 > tp3):
                # Fix ordering if broken
                all_targets = sorted([t for t in [tp1, tp2, tp3] if t is not None], reverse=True)
                if len(all_targets) >= 3:
                    tp1, tp2, tp3 = all_targets[0], all_targets[1], all_targets[2]
                elif len(all_targets) == 2:
                    tp1 = all_targets[0]
                    tp2 = (all_targets[0] + all_targets[1]) / 2
                    tp3 = all_targets[1]
                else:
                    # Only one target - create spacing manually
                    tp1 = entry_price * (1 - min_spacing_pct / 100)
                    tp2 = tp1 * (1 - min_spacing_pct / 100)
                    tp3 = tp2 * (1 - min_spacing_pct / 100)

        return tp1, tp2, tp3


def test_tp_scoring():
    """Test the TP scoring engine with sample data."""
    import yfinance as yf

    print("Testing TP Scoring Engine...")
    print("="*80)

    # Download sample data
    ticker = "AAPL"
    df = yf.download(ticker, period="1y", interval="1d", progress=False)

    # Handle MultiIndex columns from yfinance
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

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
