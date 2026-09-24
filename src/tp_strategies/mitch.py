"""Structural take-profit zones with Scott-style harmonic fallback projections.

Targets use history available at D. Unsupported target slots remain absent.
Stop placement retains the existing Mitch strategy's selection rules.
"""

from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

from logging_config import get_logger
from tp_strategies.base import TPStrategy, TPTargets
from tp_strategies.scott import ScottStrategy
from utils import ConfigHelper
import config

logger = get_logger(__name__)
config_helper = ConfigHelper(config)


class MitchStrategy(TPStrategy):
    """Select separated structural exits before using harmonic projections."""

    def __init__(
        self,
        swing_window: int = 5,
        use_tp_scoring_engine: bool = True,
        tp_min_spacing_pct: Optional[float] = None,
        tp_min_entry_distance_pct: Optional[float] = None,
        tp_atr_multiplier: Optional[float] = None,
    ) -> None:
        from tp_scoring_engine import TPScoringEngine

        self.swing_window = swing_window
        self.use_tp_scoring_engine = use_tp_scoring_engine
        self.TPScoringEngine = TPScoringEngine
        self.tp_min_spacing_pct = (
            config_helper.get_float('TP_MIN_SPACING_PCT', 30.0)
            if tp_min_spacing_pct is None else tp_min_spacing_pct
        )
        self.tp_min_entry_distance_pct = (
            config_helper.get_float('TP_MIN_ENTRY_DISTANCE_PCT', 20.0)
            if tp_min_entry_distance_pct is None else tp_min_entry_distance_pct
        )
        self.tp_atr_multiplier = (
            config_helper.get_float('TP_ATR_MULTIPLIER', 1.0)
            if tp_atr_multiplier is None else tp_atr_multiplier
        )

    def calculate_targets(
        self,
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
        ticker: Optional[str] = None,
    ) -> TPTargets:
        """Use structural zones first, then 38.2/61.8/100% pattern retracements."""
        if not all(
            np.isfinite(price) and price > 0
            for price in (x_price, a_price, b_price, c_price, d_price)
        ):
            raise ValueError("Harmonic points must be finite positive prices")
        if not 0 <= d_index < len(price_data):
            raise ValueError("D index must refer to an available price bar")

        historical_data = price_data.iloc[:d_index + 1].copy()
        if self.use_tp_scoring_engine and ticker:
            from data_downloader import download_stock_data

            try:
                full_history = download_stock_data(
                    ticker, period='max',
                    interval=config_helper.get('DATA_INTERVAL', '1d'),
                    auto_adjust=False,
                )
                if not full_history.empty:
                    full_history = full_history.copy()
                    if full_history.index.tz is not None:
                        full_history.index = full_history.index.tz_localize(None)
                    d_date = pd.Timestamp(price_data.index[d_index])
                    if d_date.tz is not None:
                        d_date = d_date.tz_localize(None)
                    # Never use the next available bar when D's date is absent.
                    full_history = full_history.loc[full_history.index <= d_date]
                    if len(full_history) > len(historical_data):
                        historical_data = full_history
            except (ValueError, KeyError, OSError) as exc:
                logger.warning(
                    "[%s] Full TP history unavailable; using supplied history: %s",
                    ticker, exc,
                )

        pattern_high = max(x_price, a_price, b_price, c_price, d_price)
        pattern_low = min(x_price, a_price, b_price, c_price, d_price)
        if pattern_high <= pattern_low:
            raise ValueError("Harmonic target projections require a positive pattern range")
        fallback = ScottStrategy().calculate_targets(
            pattern_high, pattern_low, is_bullish, price_data,
            x_price, a_price, b_price, c_price, d_price, d_index, ticker,
        )
        harmonic_targets = [
            target for target in (fallback.primary, fallback.secondary, fallback.final)
            if target is not None
        ]
        engine = self.TPScoringEngine(historical_data, atr_period=14)
        targets = engine.get_target_plan(
            entry_price=d_price,
            direction="LONG" if is_bullish else "SHORT",
            harmonic_targets=harmonic_targets,
            min_spacing_pct=self.tp_min_spacing_pct,
            min_entry_distance_pct=self.tp_min_entry_distance_pct,
            atr_multiplier=self.tp_atr_multiplier,
            include_structure=self.use_tp_scoring_engine and len(historical_data) >= 20,
        )
        if targets.primary is None:
            logger.info("[%s] No qualifying take-profit levels: %s", ticker, targets.description)
        return targets

    def _find_swing_points(
        self, data: pd.DataFrame, window: int
    ) -> Tuple[List[float], List[float]]:
        """Return historical swing prices in chronological order."""
        swing_highs: List[float] = []
        swing_lows: List[float] = []
        highs = data['high'].values
        lows = data['low'].values
        for i in range(window, len(data) - window):
            if highs[i] == max(highs[i - window:i + window + 1]):
                swing_highs.append(highs[i])
            if lows[i] == min(lows[i - window:i + window + 1]):
                swing_lows.append(lows[i])
        return swing_highs, swing_lows

    def _find_strongest_support_resistance(
        self,
        swing_highs: List[float],
        swing_lows: List[float],
        d_price: float,
        is_bullish: bool,
    ) -> Optional[float]:
        """Find the strongest cluster using the existing stop-selection policy."""
        if is_bullish:
            candidates = [low for low in swing_lows if low < d_price]
        else:
            candidates = [high for high in swing_highs if high > d_price]
        if len(candidates) == 0:
            return None

        cluster_tolerance = 0.03
        clusters: List[Tuple[float, int]] = []
        for price in candidates:
            cluster = [p for p in candidates if abs(p - price) / price <= cluster_tolerance]
            if len(cluster) >= 2:
                avg_price = sum(cluster) / len(cluster)
                clusters.append((avg_price, len(cluster)))
        if not clusters:
            return None
        clusters.sort(
            key=lambda x: (
                -x[1],
                -abs(x[0] - d_price) if is_bullish else abs(x[0] - d_price),
            )
        )
        return clusters[0][0]

    def calculate_stop_loss(
        self,
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
        min_allowed_stop_loss_pct: Optional[float] = None,
    ) -> float:
        """Retain the closest-level, strongest-cluster, then maximum-stop policy."""
        historical_data = price_data.iloc[:d_index + 1].copy()
        if min_allowed_stop_loss_pct is None:
            min_allowed_stop_loss_pct = config_helper.get_float(
                'MIN_ALLOWED_STOP_LOSS_PCT', 3.0
            )

        if is_bullish:
            min_allowed_stop = d_price * (1 - min_allowed_stop_loss_pct / 100)
            max_allowed_stop = d_price * (1 - max_allowed_stop_loss_pct / 100)
        else:
            min_allowed_stop = d_price * (1 + min_allowed_stop_loss_pct / 100)
            max_allowed_stop = d_price * (1 + max_allowed_stop_loss_pct / 100)

        swing_highs, swing_lows = self._find_swing_points(
            historical_data, window=self.swing_window
        )
        if is_bullish and len(swing_lows) > 0:
            candidate_lows = [low for low in swing_lows if low < d_price]
            if candidate_lows:
                option_a_stop = max(candidate_lows)
                if max_allowed_stop <= option_a_stop <= min_allowed_stop:
                    return option_a_stop
        elif not is_bullish and len(swing_highs) > 0:
            candidate_highs = [high for high in swing_highs if high > d_price]
            if candidate_highs:
                option_a_stop = min(candidate_highs)
                if min_allowed_stop <= option_a_stop <= max_allowed_stop:
                    return option_a_stop

        strongest_level = self._find_strongest_support_resistance(
            swing_highs, swing_lows, d_price, is_bullish
        )
        if strongest_level is not None:
            if is_bullish and max_allowed_stop <= strongest_level <= min_allowed_stop:
                return strongest_level
            elif not is_bullish and min_allowed_stop <= strongest_level <= max_allowed_stop:
                return strongest_level
        if is_bullish:
            return d_price * (1 - max_allowed_stop_loss_pct / 100)
        else:
            return d_price * (1 + max_allowed_stop_loss_pct / 100)

    def get_strategy_name(self) -> str:
        return "MITCH"
