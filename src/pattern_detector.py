"""
Hybrid Harmonic Pattern Detector
Uses Pyharmonics peak detection with Scott Carney's exact trading rules from Volumes 1, 2, and 3
"""

import pandas as pd
import numpy as np
from typing import List, Optional, Tuple, Dict
from dataclasses import dataclass
from pyharmonics import OHLCTechnicals as Technicals
from pyharmonics.search import HarmonicSearch
from carney_patterns import (
    CARNEY_PATTERNS, get_pattern_spec, PatternSpec,
    differentiate_gartley_vs_bat, differentiate_butterfly_vs_crab,
    calculate_ipo_target, calculate_382_trailer, calculate_stop_loss,
    calculate_prz_levels
)
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
import os

# Import config for SWING_WINDOW
try:
    import config
except ImportError:
    class config:
        SWING_WINDOW = 3  # Default for weekly data
        TP_STRATEGY = 'SCOTT'  # Default strategy

# Import TP strategies
from tp_strategies import ScottStrategy, MitchStrategy, PositionStrategy, TPStrategy


@dataclass
class Point:
    """Price point with index and value"""
    index: int
    price: float
    date: pd.Timestamp
    swing_type: str  # 'PEAK' or 'TROUGH'


@dataclass
class HarmonicPattern:
    """Harmonic pattern with Carney's exact trading specifications from Volumes 1-3"""
    x: Point
    a: Point
    b: Point
    c: Point
    d: Point
    pattern_type: str
    is_bullish: bool

    # Fibonacci ratios (actual measurements)
    ab_xa_ratio: float
    bc_ab_ratio: float
    bc_projection: float  # BC projection ratio
    cd_bc_ratio: float
    ad_xa_ratio: float

    # Carney's trading specs
    entry_price: float
    stop_loss: float
    ipo_target_1: float  # Initial Profit Objective (0.382 or 0.618 from pattern range)
    ipo_target_2: float  # Secondary target
    target_point_a: float  # Point A (pattern completion target)
    risk_reward: float

    # PRZ (Potential Reversal Zone) levels
    prz_levels: Dict[str, float]

    days_since_completion: int = 0
    # pattern_quality: str = "STANDARD"  # EXCELLENT, GOOD, STANDARD - REMOVED
    tolerance_level: str = "Standard"  # Textbook, Standard, or Relaxed
    grade: str = "B"  # A+, A, A-, B+, B, B-, C+, C, C-
    trade_quality: str = "Standard Trade"  # High-Probability Entry, Standard Trade, Standard / Reduced Size, Marginal / Scalp Only
    chart_path: str = ""  # Path to pattern visualization chart
    tp_strategy_used: str = ""  # Which TP strategy was used (e.g., "Scoring Engine", "Fixed", "Fibonacci")

    # Multi-swing BC leg metadata
    is_multi_swing_bc: bool = False  # True if BC leg contains multiple internal swings
    bc_internal_swing_count: int = 0  # Number of internal swings within BC leg (0 = simple BC)
    bc_volatility: float = 0.0  # Volatility within BC leg (std dev of internal swings)
    bc_duration_bars: int = 0  # Number of bars from B to C


class PatternDetector:
    """
    Uses Pyharmonics peak detection with Carney's exact pattern validation and trading rules.

    Benefits of hybrid approach:
    - Pyharmonics: Robust peak/trough detection with technical indicators
    - Carney: Exact pattern ratios and professional trading rules from Volumes 1, 2, and 3

    Implements:
    - Pattern-specific B point validation with exact tolerances
    - "Great Gartley Controversy" differentiation (BC > 1.618 = Bat)
    - I.P.O. (Initial Profit Objective) from pattern range, NOT AD leg
    - Pattern-specific stop losses
    - PRZ (Potential Reversal Zone) calculation
    - All 9 harmonic patterns: Gartley, Bat, Alternate Bat, Butterfly, Crab, Deep Crab, Cypher, Shark, 5-0
    """

    def __init__(self):
        """Initialize detector with Carney's exact specifications"""
        self.patterns = CARNEY_PATTERNS
        self.pattern_priority = [
            'gartley', 'bat', 'alternate_bat',
            'butterfly', 'crab', 'deep_crab',
            'cypher', 'shark', '5_0'
        ]
        self._tp_strategy_cache = None  # Cache the strategy instance

    def _get_tp_strategy(self) -> TPStrategy:
        """
        Get the appropriate take profit strategy based on config.TP_STRATEGY.

        Returns:
            TPStrategy instance (ScottStrategy, MitchStrategy, or PositionStrategy)
        """
        if self._tp_strategy_cache is not None:
            return self._tp_strategy_cache

        strategy_name = config.TP_STRATEGY if hasattr(config, 'TP_STRATEGY') else 'SCOTT'
        swing_window = config.SWING_WINDOW if hasattr(config, 'SWING_WINDOW') else 5

        if strategy_name == 'MITCH':
            self._tp_strategy_cache = MitchStrategy(swing_window=swing_window)
        elif strategy_name == 'POSITION':
            self._tp_strategy_cache = PositionStrategy(swing_window=swing_window)
        else:  # Default to SCOTT
            self._tp_strategy_cache = ScottStrategy()

        return self._tp_strategy_cache

    def detect_patterns(self, df: pd.DataFrame, symbol: str, interval: str = '1d') -> List[HarmonicPattern]:
        """
        Detect harmonic patterns using pyharmonics HarmonicSearch with Carney trading specs.

        Args:
            df: DataFrame with OHLC data (lowercase columns: open, high, low, close)
            symbol: Stock ticker symbol
            interval: Time interval ('1d', '1wk', '1mo', etc.)

        Returns:
            List of detected HarmonicPattern objects with Carney trading specs
        """
        return self._detect_patterns_pyharmonics(df, symbol, interval)

    def _detect_patterns_pyharmonics(self, df: pd.DataFrame, symbol: str, interval: str = '1d') -> List[HarmonicPattern]:
        """
        Detect patterns using pyharmonics HarmonicSearch, then apply Carney trading specs.

        Args:
            df: DataFrame with OHLC data (lowercase columns: open, high, low, close)
            symbol: Stock ticker symbol
            interval: Time interval ('1d', '1wk', '1mo', etc.)

        Returns:
            List of HarmonicPattern objects with Carney trading specs applied
        """
        # Create Technicals object for pyharmonics
        peak_spacing = config.SWING_WINDOW if hasattr(config, 'SWING_WINDOW') else 3
        tech = Technicals(df, symbol, interval, peak_spacing=peak_spacing)

        # Get Fibonacci tolerance from config
        fib_tolerance = config.PYHARMONICS_FIB_TOLERANCE

        # Create HarmonicSearch instance
        harmonic_search = HarmonicSearch(tech, fib_tolerance=fib_tolerance, check_anchor=True)

        # Search for formed patterns
        harmonic_search.search()
        # Get XABCD patterns (we focus on these for trading)
        pyharmonics_patterns = harmonic_search.get_patterns(family=harmonic_search.XABCD, formed=True)
        xabcd_patterns = pyharmonics_patterns.get(harmonic_search.XABCD, [])

        # Convert pyharmonics patterns to our format with Carney specs
        detected_patterns = []
        rejected_count = 0

        for py_pattern in xabcd_patterns:
            carney_pattern = self._convert_pyharmonics_pattern(py_pattern, df, tech, fib_tolerance, symbol)
            if carney_pattern:
                detected_patterns.append(carney_pattern)
            else:
                rejected_count += 1

        # Show summary if patterns were rejected
        verbose = config.VERBOSE_REPORTS if hasattr(config, 'VERBOSE_REPORTS') else False
        if rejected_count > 0 and verbose:
            print(f"  {symbol}: {rejected_count} pattern(s) rejected (invalid duration)")

        return detected_patterns

    def _convert_pyharmonics_pattern(self, py_pattern, df: pd.DataFrame, tech: Technicals, fib_tolerance: float, symbol: str) -> Optional[HarmonicPattern]:
        """
        Convert pyharmonics XABCDPattern to our HarmonicPattern format with trading specs.

        Args:
            py_pattern: pyharmonics XABCDPattern object
            df: Price dataframe for date lookups
            tech: Technicals object for peak data
            fib_tolerance: Fibonacci tolerance used for pattern detection (e.g., 0.03 = 3%)
            symbol: Stock ticker symbol

        Returns:
            HarmonicPattern with Carney trading specs, or None if conversion fails
        """
        try:
            # Extract X, A, B, C, D points from pyharmonics pattern
            # py_pattern.x contains timestamps/indices, py_pattern.y contains prices
            x_date, a_date, b_date, c_date, d_date = py_pattern.x
            x_price, a_price, b_price, c_price, d_price = py_pattern.y

            # Convert timestamps to pandas Timestamp objects
            x_ts = pd.Timestamp(x_date, unit='ms') if isinstance(x_date, (int, float)) else pd.Timestamp(x_date)
            a_ts = pd.Timestamp(a_date, unit='ms') if isinstance(a_date, (int, float)) else pd.Timestamp(a_date)
            b_ts = pd.Timestamp(b_date, unit='ms') if isinstance(b_date, (int, float)) else pd.Timestamp(b_date)
            c_ts = pd.Timestamp(c_date, unit='ms') if isinstance(c_date, (int, float)) else pd.Timestamp(c_date)
            d_ts = pd.Timestamp(d_date, unit='ms') if isinstance(d_date, (int, float)) else pd.Timestamp(d_date)

            # Create Point objects
            is_bullish = py_pattern.bullish
            x_point = Point(index=0, price=x_price, date=x_ts,
                          swing_type='TROUGH' if is_bullish else 'PEAK')
            a_point = Point(index=1, price=a_price, date=a_ts,
                          swing_type='PEAK' if is_bullish else 'TROUGH')
            b_point = Point(index=2, price=b_price, date=b_ts,
                          swing_type='TROUGH' if is_bullish else 'PEAK')
            c_point = Point(index=3, price=c_price, date=c_ts,
                          swing_type='PEAK' if is_bullish else 'TROUGH')
            d_point = Point(index=4, price=d_price, date=d_ts,
                          swing_type='TROUGH' if is_bullish else 'PEAK')

            # Validate temporal proportionality
            is_temporally_valid, temporal_reason = self._validate_temporal_proportionality(
                x_ts, a_ts, b_ts, c_ts, d_ts
            )

            if not is_temporally_valid:
                # Silently reject - will be summarized at ticker level
                return None  # Reject pattern with invalid duration

            # Use Fibonacci ratios from pyharmonics (trust their calculations)
            # py_pattern.retraces contains:
            #   'XAB'   = AB/XA ratio (B-point)
            #   'ABC'   = BC/AB ratio (C-point retracement)
            #   'BCD'   = CD/BC ratio (BC projection)
            #   'XABCD' = XD/XA ratio (D-point completion)
            from pyharmonics import constants

            ab_xa = py_pattern.retraces.get(constants.XAB, 0)
            bc_ab = py_pattern.retraces.get(constants.ABC, 0)
            bc_projection = py_pattern.retraces.get(constants.BCD, 0)
            cd_bc = bc_projection  # Same as BCD
            ad_xa = py_pattern.retraces.get(constants.XABCD, 0)

            # Calculate XA range for stop loss calculations
            xa_range = abs(a_price - x_price)

            # Map pyharmonics pattern names to our format
            pattern_name_map = {
                'bat': 'bat',
                'alt bat': 'alternate_bat',
                'gartley': 'gartley',
                'butterfly': 'butterfly',
                'crab': 'crab',
                'deep crab': 'deep_crab',
                'cypher': 'cypher',
                'shark': 'shark',
                'deep shark': '5_0',  # Map deep shark to 5-0 pattern
            }
            pattern_type = pattern_name_map.get(py_pattern.name.lower(), py_pattern.name.lower())

            # Get pattern spec for Carney trading rules
            pattern_spec = get_pattern_spec(pattern_type)
            if not pattern_spec:
                return None  # Unknown pattern type

            # Calculate Carney trading specifications
            # Entry price at point D
            entry_price = d_price

            # Calculate PRZ levels
            prz_levels = calculate_prz_levels(x_price, a_price, b_price, c_price, pattern_spec)

            # Stop loss using Carney's pattern-specific ratio
            stop_loss = calculate_stop_loss(pattern_spec, x_price, xa_range, is_bullish)

            # I.P.O. profit targets (from D to A reversal distance)
            if is_bullish:
                pattern_low = d_price
                pattern_high = a_price
            else:
                pattern_high = d_price
                pattern_low = a_price

            # Get TP targets using selected strategy
            tp_strategy = self._get_tp_strategy()

            # Find d_index in dataframe for strategy context
            try:
                d_index = df.index.get_loc(df.index[df.index >= d_ts][0])
            except (IndexError, KeyError):
                d_index = len(df) - 1  # Fallback to last index

            # Calculate targets using strategy
            tp_targets = tp_strategy.calculate_targets(
                pattern_high=pattern_high,
                pattern_low=pattern_low,
                is_bullish=is_bullish,
                price_data=df,
                x_price=x_price,
                a_price=a_price,
                b_price=b_price,
                c_price=c_price,
                d_price=d_price,
                d_index=d_index,
                ticker=symbol
            )

            ipo_target_1 = tp_targets.primary
            ipo_target_2 = tp_targets.secondary
            target_point_a = tp_targets.final if tp_targets.final else a_price
            tp_strategy_used = tp_targets.tp_strategy_used if hasattr(tp_targets, 'tp_strategy_used') else ""

            # Check if TP strategy has custom stop loss calculation
            max_allowed_stop_loss_pct = config.MAX_ALLOWED_STOP_LOSS_PCT if hasattr(config, 'MAX_ALLOWED_STOP_LOSS_PCT') else 10.0
            min_allowed_stop_loss_pct = config.MIN_ALLOWED_STOP_LOSS_PCT if hasattr(config, 'MIN_ALLOWED_STOP_LOSS_PCT') else 3.0
            strategy_stop_loss = tp_strategy.calculate_stop_loss(
                pattern_high=pattern_high,
                pattern_low=pattern_low,
                is_bullish=is_bullish,
                price_data=df,
                x_price=x_price,
                a_price=a_price,
                b_price=b_price,
                c_price=c_price,
                d_price=d_price,
                d_index=d_index,
                max_allowed_stop_loss_pct=max_allowed_stop_loss_pct,
                min_allowed_stop_loss_pct=min_allowed_stop_loss_pct
            )

            # Use strategy's stop loss if provided, otherwise keep Carney's
            if strategy_stop_loss is not None:
                stop_loss = strategy_stop_loss

            # Risk/Reward calculation using WEIGHTED average based on position sizing
            # Uses position sizing from config to ensure consistency with P&L calculations
            # This gives a more accurate R/R that reflects actual trade potential
            risk = abs(entry_price - stop_loss)
            reward_t1 = abs(ipo_target_1 - entry_price)
            reward_t2 = abs(ipo_target_2 - entry_price)
            reward_t3 = abs(target_point_a - entry_price)
            # Weighted average reward using config position sizing
            weighted_reward = (reward_t1 * config.POSITION_SIZE_T1) + \
                            (reward_t2 * config.POSITION_SIZE_T2) + \
                            (reward_t3 * config.POSITION_SIZE_T3)
            risk_reward = weighted_reward / risk if risk > 0 else 0

            # Pattern quality assessment - REMOVED
            # pattern_quality = self._assess_pattern_quality(
            #     ab_xa, pattern_spec.b_point_min, pattern_spec.b_point_max,
            #     bc_projection, pattern_spec.bc_projection_min, pattern_spec.bc_projection_max
            # )

            # For pyharmonics patterns, tolerance_level shows the fib_tolerance as percentage
            tolerance_level = f"{fib_tolerance*100:.1f}%"

            # Calculate refined grade based on Scott Carney's hierarchy
            # D-point accuracy (45%), PRZ convergence, and time symmetry
            grade = self._calculate_pyharmonics_grade(
                ab_xa, ad_xa, bc_projection, pattern_spec, fib_tolerance,
                x_price, a_price, b_price, c_price, d_price,
                x_ts, a_ts, b_ts, c_ts, d_ts
            )

            # Determine trade quality tier based on grade
            trade_quality = self._get_trade_quality(grade)

            # Create HarmonicPattern object
            return HarmonicPattern(
                x=x_point, a=a_point, b=b_point, c=c_point, d=d_point,
                pattern_type=pattern_spec.name,
                is_bullish=is_bullish,
                ab_xa_ratio=ab_xa,
                bc_ab_ratio=bc_ab,
                bc_projection=bc_projection,
                cd_bc_ratio=cd_bc,
                ad_xa_ratio=ad_xa,
                entry_price=entry_price,
                stop_loss=stop_loss,
                ipo_target_1=ipo_target_1,
                ipo_target_2=ipo_target_2,
                target_point_a=target_point_a,
                risk_reward=risk_reward,
                prz_levels=prz_levels,
                days_since_completion=0,
                # pattern_quality=pattern_quality,  # REMOVED
                tolerance_level=tolerance_level,
                grade=grade,
                trade_quality=trade_quality,
                tp_strategy_used=tp_strategy_used,
                # Multi-swing BC not detected from pyharmonics
                is_multi_swing_bc=False,
                bc_internal_swing_count=0,
                bc_volatility=0.0,
                bc_duration_bars=0
            )

        except Exception as e:
            # If conversion fails, skip this pattern
            print(f"Warning: [{symbol}] Failed to convert pyharmonics pattern {py_pattern.name}: {e}")
            return None

    def _validate_temporal_proportionality(self, x_ts, a_ts, b_ts, c_ts, d_ts) -> tuple:
        """
        Validate that pattern legs have proportional time relationships.
        Filters out patterns where CD leg is disproportionately extended compared to other legs.

        This catches patterns like RANI where XABC forms in 6-18 months but CD takes 4+ years,
        indicating different market phases rather than a cohesive harmonic structure.

        Args:
            x_ts, a_ts, b_ts, c_ts, d_ts: Timestamps for each point

        Returns:
            (is_valid, reason): Tuple of boolean and reason string
        """
        # Check if temporal validation is enabled
        if not (hasattr(config, 'ENABLE_TEMPORAL_VALIDATION') and config.ENABLE_TEMPORAL_VALIDATION):
            return True, ""

        # Calculate time durations in days
        xa_time = (a_ts - x_ts).days
        ab_time = (b_ts - a_ts).days
        bc_time = (c_ts - b_ts).days
        cd_time = (d_ts - c_ts).days
        xabc_time = xa_time + ab_time + bc_time
        total_time = (d_ts - x_ts).days

        # Avoid division by zero
        if xa_time <= 0 or ab_time <= 0 or bc_time <= 0:
            return False, f"Invalid time sequence: XA={xa_time}d, AB={ab_time}d, BC={bc_time}d"

        # Check maximum total pattern duration (prevents 24-year patterns like SHEN!)
        max_total_duration = config.MAX_TOTAL_PATTERN_DURATION_DAYS if hasattr(config, 'MAX_TOTAL_PATTERN_DURATION_DAYS') else 1825
        if total_time > max_total_duration:
            return False, f"Total pattern duration too long: {total_time} days ({total_time/365:.1f} years, max {max_total_duration/365:.1f} years)"

        # Check maximum individual leg duration (prevents 19-year XA legs!)
        max_leg_duration = config.MAX_INDIVIDUAL_LEG_DURATION_DAYS if hasattr(config, 'MAX_INDIVIDUAL_LEG_DURATION_DAYS') else 1095

        if xa_time > max_leg_duration:
            return False, f"XA leg too long: {xa_time} days ({xa_time/365:.1f} years, max {max_leg_duration/365:.1f} years)"
        if ab_time > max_leg_duration:
            return False, f"AB leg too long: {ab_time} days ({ab_time/365:.1f} years, max {max_leg_duration/365:.1f} years)"
        if bc_time > max_leg_duration:
            return False, f"BC leg too long: {bc_time} days ({bc_time/365:.1f} years, max {max_leg_duration/365:.1f} years)"
        if cd_time > max_leg_duration:
            return False, f"CD leg too long: {cd_time} days ({cd_time/365:.1f} years, max {max_leg_duration/365:.1f} years)"

        # Calculate time ratios
        cd_to_xa_ratio = cd_time / xa_time
        cd_to_ab_ratio = cd_time / ab_time
        cd_to_bc_ratio = cd_time / bc_time
        cd_to_xabc_ratio = cd_time / xabc_time if xabc_time > 0 else 0

        # Get thresholds from config (with defaults)
        max_cd_xa = config.MAX_CD_TO_XA_TIME_RATIO if hasattr(config, 'MAX_CD_TO_XA_TIME_RATIO') else 5.0
        max_cd_ab = config.MAX_CD_TO_AB_TIME_RATIO if hasattr(config, 'MAX_CD_TO_AB_TIME_RATIO') else 10.0
        max_cd_bc = config.MAX_CD_TO_BC_TIME_RATIO if hasattr(config, 'MAX_CD_TO_BC_TIME_RATIO') else 8.0
        max_cd_xabc = config.MAX_CD_TO_XABC_TIME_RATIO if hasattr(config, 'MAX_CD_TO_XABC_TIME_RATIO') else 3.0

        # Check if CD is disproportionately long
        if cd_to_xa_ratio > max_cd_xa:
            return False, f"CD leg too extended: {cd_to_xa_ratio:.1f}x longer than XA (max {max_cd_xa}x)"

        if cd_to_ab_ratio > max_cd_ab:
            return False, f"CD leg too extended: {cd_to_ab_ratio:.1f}x longer than AB (max {max_cd_ab}x)"

        if cd_to_bc_ratio > max_cd_bc:
            return False, f"CD leg too extended: {cd_to_bc_ratio:.1f}x longer than BC (max {max_cd_bc}x)"

        if cd_to_xabc_ratio > max_cd_xabc:
            return False, f"CD leg too extended: {cd_to_xabc_ratio:.1f}x longer than XABC combined (max {max_cd_xabc}x)"

        # Pattern passes temporal validation
        return True, ""

    # REMOVED: _assess_pattern_quality() method - quality classification no longer used
    # def _assess_pattern_quality(self, ab_xa: float, b_min: float, b_max: float,
    #                             bc_proj: float, bc_min: float, bc_max: float) -> str:
    #     """
    #     Assess pattern quality based on how precise the ratios are.
    #
    #     Returns: EXCELLENT, GOOD, or STANDARD
    #     """
    #     b_midpoint = (b_min + b_max) / 2
    #     bc_midpoint = (bc_min + bc_max) / 2
    #
    #     b_deviation = abs(ab_xa - b_midpoint) / ((b_max - b_min) / 2) if b_max != b_min else 0
    #     bc_deviation = abs(bc_proj - bc_midpoint) / ((bc_max - bc_min) / 2) if bc_max != bc_min else 0
    #
    #     avg_deviation = (b_deviation + bc_deviation) / 2
    #
    #     if avg_deviation < 0.3:
    #         return "EXCELLENT"
    #     elif avg_deviation < 0.6:
    #         return "GOOD"
    #     else:
    #         return "STANDARD"


    def _calculate_pyharmonics_grade(self, ab_xa: float, ad_xa: float, bc_projection: float,
                                     pattern_spec, fib_tolerance: float,
                                     x_price: float, a_price: float, b_price: float,
                                     c_price: float, d_price: float,
                                     x_ts, a_ts, b_ts, c_ts, d_ts) -> str:
        """
        Calculate refined harmonic grade emphasizing D-point accuracy, PRZ convergence, and time symmetry.

        Grading Hierarchy (Scott Carney Framework):
        - D-point (PRZ): 45% weight - MOST CRITICAL for reversal probability
        - B-point: 35% weight - Pattern structure definition
        - BC projection: 20% weight - Most flexible leg

        Quality Multipliers:
        - PRZ Convergence: ±5 points (cluster of AB=CD, BC proj, D-point)
        - Time Symmetry: ±1 tier (XB vs BD leg duration harmony)

        Args:
            ab_xa: Actual AB/XA ratio (B-point)
            ad_xa: Actual AD/XA ratio (D-point)
            bc_projection: Actual CD/BC ratio (BC projection)
            pattern_spec: PatternSpec with ideal ranges
            fib_tolerance: PYHARMONICS_FIB_TOLERANCE value
            x_price, a_price, b_price, c_price, d_price: XABCD prices
            x_ts, a_ts, b_ts, c_ts, d_ts: XABCD timestamps

        Returns:
            Grade from A+ to C- based on Fibonacci precision and structural quality
        """
        # Step 1: Calculate individual ratio scores (0-100 scale)
        # Using distance-to-band normalization (NOT fixed percentage)

        b_score = self._score_ratio_precision(
            actual=ab_xa,
            ideal_min=pattern_spec.b_point_min,
            ideal_max=pattern_spec.b_point_max
        )

        d_score = self._score_ratio_precision(
            actual=ad_xa,
            ideal_min=pattern_spec.d_point_min,
            ideal_max=pattern_spec.d_point_max
        )

        bc_score = self._score_ratio_precision(
            actual=bc_projection,
            ideal_min=pattern_spec.bc_projection_min,
            ideal_max=pattern_spec.bc_projection_max
        )

        # Step 2: Calculate weighted base score (D-point dominates)
        # D=45%, B=35%, BC=20%
        base_score = (d_score * 0.45) + (b_score * 0.35) + (bc_score * 0.20)

        # Step 3: PRZ Convergence Analysis
        # Check if AB=CD, BC projection, and D-point cluster at same price level
        prz_adjustment = self._calculate_prz_convergence(
            x_price, a_price, b_price, c_price, d_price,
            ad_xa, bc_projection, pattern_spec
        )

        # Step 4: Time Symmetry Analysis
        # Evaluate temporal harmony between XB and BD legs
        time_adjustment = self._calculate_time_symmetry(
            x_ts, a_ts, b_ts, c_ts, d_ts
        )

        # Step 5: Calculate final score with adjustments
        final_score = base_score + prz_adjustment + time_adjustment

        # Clamp to valid range
        final_score = max(0, min(100, final_score))

        # Step 6: Convert score to letter grade
        grade = self._score_to_grade(final_score)

        return grade

    def _score_ratio_precision(self, actual: float, ideal_min: float, ideal_max: float) -> float:
        """
        Score how precisely a Fibonacci ratio matches its ideal band using distance-to-band normalization.

        This ensures:
        - Tight ratios (e.g., Gartley D = 0.786) are scored strictly
        - Wide ratios (e.g., Crab BC = 2.618-3.618) are scored flexibly

        Args:
            actual: Actual measured ratio
            ideal_min: Minimum acceptable Fibonacci value
            ideal_max: Maximum acceptable Fibonacci value

        Returns:
            Score from 0-100 (100 = perfect, 0 = at/beyond tolerance edge)
        """
        # Calculate ideal midpoint
        ideal_midpoint = (ideal_min + ideal_max) / 2

        # Calculate band width (tolerance range)
        band_width = ideal_max - ideal_min

        # Handle exact values (zero band width)
        if band_width < 0.001:
            # For exact ratios (e.g., Gartley D = 0.786), use stricter scoring
            deviation = abs(actual - ideal_midpoint)
            # Use 3% as reference tolerance for exact ratios
            max_deviation = ideal_midpoint * 0.03
            normalized_deviation = min(deviation / max_deviation, 1.0) if max_deviation > 0 else 0
            score = 100 * (1 - normalized_deviation)
            return max(0, score)

        # Calculate distance from midpoint
        deviation_from_midpoint = abs(actual - ideal_midpoint)

        # Normalize by half-band width (distance to edge)
        half_band = band_width / 2
        normalized_deviation = deviation_from_midpoint / half_band if half_band > 0 else 0

        # Convert to score (0-100)
        # Perfect midpoint hit = 100
        # At band edge = 50
        # Beyond band edge = diminishing score
        if normalized_deviation <= 1.0:
            # Within band: linear scoring from 100 (midpoint) to 50 (edge)
            score = 100 - (normalized_deviation * 50)
        else:
            # Outside band: penalty scoring
            # Beyond edge by 1x band width = 0 score
            overshoot = normalized_deviation - 1.0
            score = max(0, 50 - (overshoot * 50))

        return score

    def _calculate_prz_convergence(self, x_price: float, a_price: float, b_price: float,
                                   c_price: float, d_price: float, ad_xa: float,
                                   bc_projection: float, pattern_spec) -> float:
        """
        Calculate PRZ (Potential Reversal Zone) convergence bonus/penalty.

        The D-point is strongest when multiple Fibonacci levels cluster at the same price:
        - Primary D ratio (e.g., 0.786 XA for Gartley, 1.618 XA for Crab)
        - AB=CD completion level
        - BC projection completion level

        Tight clustering = High reversal probability = Bonus
        Wide dispersion = Weak PRZ = Penalty

        Args:
            x_price, a_price, b_price, c_price, d_price: XABCD price levels
            ad_xa: Actual AD/XA ratio
            bc_projection: Actual BC projection ratio
            pattern_spec: Pattern specification

        Returns:
            Adjustment value: +5 to -5 points
        """
        # Calculate three key PRZ levels

        # Level 1: Primary D-point (actual D from pattern)
        primary_d = d_price

        # Level 2: AB=CD completion
        # AB=CD means: CD should equal AB in price distance
        ab_distance = abs(b_price - a_price)
        if primary_d < c_price:  # Bullish pattern (D below C)
            abcd_target = c_price - ab_distance
        else:  # Bearish pattern (D above C)
            abcd_target = c_price + ab_distance

        # Level 3: BC projection target
        bc_distance = abs(c_price - b_price)
        bc_proj_distance = bc_distance * pattern_spec.bc_projection_min  # Use min as reference
        if primary_d < c_price:  # Bullish
            bc_proj_target = c_price - bc_proj_distance
        else:  # Bearish
            bc_proj_target = c_price + bc_proj_distance

        # Calculate price deviations between the three levels
        d_to_abcd = abs(primary_d - abcd_target)
        d_to_bc_proj = abs(primary_d - bc_proj_target)
        abcd_to_bc_proj = abs(abcd_target - bc_proj_target)

        # Calculate percentage deviations relative to D price
        avg_d_price = (primary_d + abcd_target + bc_proj_target) / 3
        if avg_d_price == 0:
            return 0

        pct_d_to_abcd = (d_to_abcd / avg_d_price) * 100
        pct_d_to_bc_proj = (d_to_bc_proj / avg_d_price) * 100
        pct_abcd_to_bc_proj = (abcd_to_bc_proj / avg_d_price) * 100

        # Average percentage deviation across all three comparisons
        avg_deviation_pct = (pct_d_to_abcd + pct_d_to_bc_proj + pct_abcd_to_bc_proj) / 3

        # Scoring logic:
        # Excellent clustering: < 0.3% deviation → +5 points (strong reversal zone)
        # Good clustering: 0.3-0.6% → +3 points
        # Acceptable: 0.6-1.0% → +1 point
        # Neutral: 1.0-2.0% → 0 points
        # Poor: 2.0-3.0% → -2 points
        # Very poor: > 3.0% → -5 points (dispersed PRZ, weak signal)

        if avg_deviation_pct < 0.3:
            return 5.0  # Exceptional PRZ cluster
        elif avg_deviation_pct < 0.6:
            return 3.0  # Strong cluster
        elif avg_deviation_pct < 1.0:
            return 1.0  # Good cluster
        elif avg_deviation_pct < 2.0:
            return 0.0  # Neutral
        elif avg_deviation_pct < 3.0:
            return -2.0  # Weak PRZ
        else:
            return -5.0  # Dispersed PRZ

    def _calculate_time_symmetry(self, x_ts, a_ts, b_ts, c_ts, d_ts) -> float:
        """
        Calculate time symmetry adjustment based on XB vs BD leg duration.

        Harmonic patterns require price AND time harmony.
        Excellent time symmetry improves reversal probability.
        Broken rhythm suggests weaker structural integrity.

        Args:
            x_ts, a_ts, b_ts, c_ts, d_ts: XABCD timestamps

        Returns:
            Adjustment value: +3 to -3 points
        """
        # Calculate leg durations
        xb_duration = (b_ts - x_ts).days
        bd_duration = (d_ts - b_ts).days

        # Avoid division by zero
        if xb_duration <= 0 or bd_duration <= 0:
            return 0

        # Calculate time ratio
        time_ratio = bd_duration / xb_duration if xb_duration > 0 else 0

        # Scoring based on Fibonacci time ratios:
        # Perfect symmetry: 0.618-1.618 (golden ratio zone) → +3 points
        # Good symmetry: 0.5-2.0 → +1 point
        # Acceptable: 0.382-2.618 → 0 points
        # Poor: One leg > 2.618x the other → -3 points

        if 0.618 <= time_ratio <= 1.618:
            # Golden ratio time symmetry
            return 3.0
        elif 0.5 <= time_ratio <= 2.0:
            # Good symmetry
            return 1.0
        elif 0.382 <= time_ratio <= 2.618:
            # Acceptable range
            return 0.0
        else:
            # Broken rhythm - one leg disproportionately long
            return -3.0

    def _score_to_grade(self, score: float) -> str:
        """
        Convert numerical score (0-100) to letter grade.

        Args:
            score: Final score after all adjustments

        Returns:
            Letter grade from A+ to C-
        """
        if score >= 95:
            return 'A+'
        elif score >= 90:
            return 'A'
        elif score >= 85:
            return 'A-'
        elif score >= 80:
            return 'B+'
        elif score >= 75:
            return 'B'
        elif score >= 70:
            return 'B-'
        elif score >= 65:
            return 'C+'
        elif score >= 60:
            return 'C'
        else:
            return 'C-'

    def _get_trade_quality(self, grade: str) -> str:
        """
        Map letter grade to trade quality classification.

        Args:
            grade: Letter grade (A+ to C-)

        Returns:
            Trade quality tier
        """
        if grade in ['A+', 'A']:
            return 'High-Probability Entry'
        elif grade in ['A-', 'B+', 'B']:
            return 'Standard Trade'
        elif grade in ['B-', 'C+']:
            return 'Standard / Reduced Size'
        else:  # C, C-
            return 'Marginal / Scalp Only'

    def generate_pattern_chart(self, pattern: HarmonicPattern, ticker: str,
                               df: pd.DataFrame, chart_dir: str, interval: str = '1d',
                               reaction_data=None) -> str:
        """
        Generate a chart visualization of the harmonic pattern with Type 1/Type 2 reaction overlay.

        Args:
            pattern: The harmonic pattern to visualize
            ticker: Stock ticker symbol
            df: Price dataframe with OHLC data
            chart_dir: Directory to save the chart
            interval: Time interval ('1d', '1wk', '1mo', etc.)
            reaction_data: Optional ReactionData object with Type 1/Type 2 analysis

        Returns:
            Path to the saved chart image
        """
        # Create directory if it doesn't exist
        os.makedirs(chart_dir, exist_ok=True)

        # Create figure
        fig, ax = plt.subplots(figsize=(16, 9))

        # Calculate pattern timeframe (X to D) and show 2x that range
        # Get the date range of the pattern (from X to D)
        pattern_start = pattern.x.date
        pattern_end = pattern.d.date
        pattern_duration = pattern_end - pattern_start

        # Calculate 2x the pattern duration
        chart_start = pattern_end - (pattern_duration * 2)

        # Filter dataframe to show 2x the pattern timeframe
        # If chart_start is before the data, use all available data
        df_window = df[df.index >= chart_start]

        # Ensure we have the pattern completion point in the window
        if pattern_end not in df_window.index:
            df_window = df

        # Plot candlesticks
        dates = df_window.index
        opens = df_window['open'].values
        closes = df_window['close'].values
        highs = df_window['high'].values
        lows = df_window['low'].values

        # Convert dates to numeric for candlestick plotting
        from matplotlib.patches import Rectangle
        import matplotlib.patches as mpatches

        # Candlestick width (adjust based on interval)
        candle_width = 0.6
        if interval == '1wk':
            candle_width = 5  # 5 days for weekly
        elif interval == '1mo':
            candle_width = 20  # 20 days for monthly

        # Draw candlesticks
        for i, date in enumerate(dates):
            open_price = opens[i]
            close_price = closes[i]
            high_price = highs[i]
            low_price = lows[i]

            # Determine candle color
            if close_price >= open_price:
                # Bullish candle (green)
                body_color = '#26a69a'  # Teal green
                edge_color = '#1a7a6d'
            else:
                # Bearish candle (red)
                body_color = '#ef5350'  # Red
                edge_color = '#c62828'

            # Draw high-low line (wick)
            ax.plot([date, date], [low_price, high_price],
                   color=edge_color, linewidth=1, zorder=1)

            # Draw open-close rectangle (body)
            height = abs(close_price - open_price)
            bottom = min(open_price, close_price)

            rect = Rectangle((mdates.date2num(date) - candle_width/2, bottom),
                           candle_width, height,
                           facecolor=body_color, edgecolor=edge_color,
                           linewidth=1, zorder=2, alpha=0.8)
            ax.add_patch(rect)

        # Plot the harmonic pattern overlay
        pattern_points = [pattern.x, pattern.a, pattern.b, pattern.c, pattern.d]
        pattern_dates = [p.date for p in pattern_points]
        pattern_prices = [p.price for p in pattern_points]
        pattern_labels = ['X', 'A', 'B', 'C', 'D']

        # Pattern line color based on direction
        pattern_line_color = '#2962ff' if pattern.is_bullish else '#ff6d00'  # Blue for bullish, Orange for bearish

        # Draw pattern lines with higher zorder to overlay on candlesticks
        for i in range(len(pattern_points) - 1):
            ax.plot([pattern_dates[i], pattern_dates[i+1]],
                   [pattern_prices[i], pattern_prices[i+1]],
                   color=pattern_line_color, linewidth=3, alpha=0.9, zorder=10,
                   solid_capstyle='round')

        # Fill pattern area with transparent color
        pattern_x_coords = pattern_dates
        pattern_y_coords = pattern_prices
        ax.fill(pattern_x_coords, pattern_y_coords,
               color=pattern_line_color, alpha=0.1, zorder=3)

        # Plot pattern points with distinct colors
        point_colors = ['#d32f2f', '#388e3c', '#d32f2f', '#388e3c', '#d32f2f'] if pattern.is_bullish else ['#388e3c', '#d32f2f', '#388e3c', '#d32f2f', '#388e3c']
        for i, (date, price, label, color) in enumerate(zip(pattern_dates, pattern_prices, pattern_labels, point_colors)):
            # Draw larger outer circle
            ax.scatter(date, price, c='white', s=300, zorder=11, edgecolors='black', linewidth=3)
            # Draw inner colored circle
            ax.scatter(date, price, c=color, s=250, zorder=12, edgecolors='black', linewidth=2)

            # Add label with offset to avoid overlap
            y_offset = (max(pattern_prices) - min(pattern_prices)) * 0.03
            ax.text(date, price + y_offset, label,
                   fontsize=12, fontweight='bold', ha='center', va='bottom',
                   color='white', zorder=13,
                   bbox=dict(boxstyle='round,pad=0.4', facecolor='black', alpha=0.8, edgecolor=color, linewidth=2))

            # Add price label below
            ax.text(date, price - y_offset, f'${price:.2f}',
                   fontsize=9, ha='center', va='top',
                   color='black', zorder=13,
                   bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.9, edgecolor='gray', linewidth=1))

        # ========== ADD FIBONACCI RATIO VECTORS (LAYER II) ==========
        # Draw four critical Fibonacci relationship vectors with dashed lines and ratio labels
        # These help visualize the geometric relationships that define the harmonic pattern

        ratio_vector_color = '#1e88e5'  # Blue color for ratio vectors
        ratio_vector_style = '--'  # Dashed line style
        ratio_vector_width = 2.5
        ratio_vector_alpha = 0.6

        # Vector 1: X → B (R_XAB - AB/XA ratio)
        ax.plot([pattern.x.date, pattern.b.date],
               [pattern.x.price, pattern.b.price],
               color=ratio_vector_color, linewidth=ratio_vector_width,
               linestyle=ratio_vector_style, alpha=ratio_vector_alpha, zorder=8)

        # Midpoint for X→B label
        xb_mid_date = pattern.x.date + (pattern.b.date - pattern.x.date) / 2
        xb_mid_price = (pattern.x.price + pattern.b.price) / 2
        ax.text(xb_mid_date, xb_mid_price, f'{pattern.ab_xa_ratio:.3f}',
               fontsize=9, ha='center', va='center', fontweight='bold',
               color='white', zorder=14,
               bbox=dict(boxstyle='round,pad=0.4', facecolor=ratio_vector_color,
                        alpha=0.85, edgecolor='white', linewidth=1.5))

        # Vector 2: A → C (R_ABC - BC/AB ratio)
        ax.plot([pattern.a.date, pattern.c.date],
               [pattern.a.price, pattern.c.price],
               color=ratio_vector_color, linewidth=ratio_vector_width,
               linestyle=ratio_vector_style, alpha=ratio_vector_alpha, zorder=8)

        # Midpoint for A→C label
        ac_mid_date = pattern.a.date + (pattern.c.date - pattern.a.date) / 2
        ac_mid_price = (pattern.a.price + pattern.c.price) / 2
        ax.text(ac_mid_date, ac_mid_price, f'{pattern.bc_ab_ratio:.3f}',
               fontsize=9, ha='center', va='center', fontweight='bold',
               color='white', zorder=14,
               bbox=dict(boxstyle='round,pad=0.4', facecolor=ratio_vector_color,
                        alpha=0.85, edgecolor='white', linewidth=1.5))

        # Vector 3: B → D (R_BCD - CD/BC ratio, also known as BC projection)
        ax.plot([pattern.b.date, pattern.d.date],
               [pattern.b.price, pattern.d.price],
               color=ratio_vector_color, linewidth=ratio_vector_width,
               linestyle=ratio_vector_style, alpha=ratio_vector_alpha, zorder=8)

        # Midpoint for B→D label
        bd_mid_date = pattern.b.date + (pattern.d.date - pattern.b.date) / 2
        bd_mid_price = (pattern.b.price + pattern.d.price) / 2
        ax.text(bd_mid_date, bd_mid_price, f'{pattern.bc_projection:.3f}',
               fontsize=9, ha='center', va='center', fontweight='bold',
               color='white', zorder=14,
               bbox=dict(boxstyle='round,pad=0.4', facecolor=ratio_vector_color,
                        alpha=0.85, edgecolor='white', linewidth=1.5))

        # Vector 4: X → D (R_XABCD - AD/XA ratio, pattern completion ratio)
        ax.plot([pattern.x.date, pattern.d.date],
               [pattern.x.price, pattern.d.price],
               color=ratio_vector_color, linewidth=ratio_vector_width,
               linestyle=ratio_vector_style, alpha=ratio_vector_alpha, zorder=8)

        # Midpoint for X→D label
        xd_mid_date = pattern.x.date + (pattern.d.date - pattern.x.date) / 2
        xd_mid_price = (pattern.x.price + pattern.d.price) / 2
        ax.text(xd_mid_date, xd_mid_price, f'{pattern.ad_xa_ratio:.3f}',
               fontsize=9, ha='center', va='center', fontweight='bold',
               color='white', zorder=14,
               bbox=dict(boxstyle='round,pad=0.4', facecolor=ratio_vector_color,
                        alpha=0.85, edgecolor='white', linewidth=1.5))
        # ============================================================

        # Add Type 1 and Type 2 reaction visualization if available
        if reaction_data:
            # Mark Terminal Bar (T-Bar) at point D
            ax.axvline(x=pattern.d.date, color='purple', linestyle=':', linewidth=3, alpha=0.8,
                      zorder=15)

            # Type 1 Reaction visualization
            if reaction_data.type1_detected:
                # Mark the Type 1 reversal bar
                if reaction_data.type1_reversal_date:
                    ax.axvline(x=reaction_data.type1_reversal_date, color='#ff9800',
                              linestyle='-.', linewidth=2.5, alpha=0.8, zorder=15)

                    # Draw arrow showing Type 1 move
                    if pattern.is_bullish:
                        # Bullish: arrow pointing up from D to Type 1 peak
                        ax.annotate('', xy=(reaction_data.type1_reversal_date, reaction_data.type1_max_move),
                                   xytext=(pattern.d.date, pattern.d.price),
                                   arrowprops=dict(arrowstyle='->', color='#ff9800', lw=2.5, alpha=0.7),
                                   zorder=14)

                        # Mark if 38.2% target reached
                        if reaction_data.type1_reached_382:
                            ax.scatter(reaction_data.type1_reversal_date, reaction_data.target_382,
                                     marker='*', s=400, c='gold', edgecolors='black', linewidth=2,
                                     zorder=16)

                        # Mark if 61.8% target reached
                        if reaction_data.type1_reached_618:
                            ax.scatter(reaction_data.type1_reversal_date, reaction_data.target_618,
                                     marker='*', s=500, c='lime', edgecolors='black', linewidth=2,
                                     zorder=16)
                    else:
                        # Bearish: arrow pointing down from D to Type 1 low
                        ax.annotate('', xy=(reaction_data.type1_reversal_date, reaction_data.type1_max_move),
                                   xytext=(pattern.d.date, pattern.d.price),
                                   arrowprops=dict(arrowstyle='->', color='#ff9800', lw=2.5, alpha=0.7),
                                   zorder=14)

                        # Mark targets for bearish
                        if reaction_data.type1_reached_382:
                            ax.scatter(reaction_data.type1_reversal_date, reaction_data.target_382,
                                     marker='*', s=400, c='gold', edgecolors='black', linewidth=2,
                                     zorder=16)

                        if reaction_data.type1_reached_618:
                            ax.scatter(reaction_data.type1_reversal_date, reaction_data.target_618,
                                     marker='*', s=500, c='lime', edgecolors='black', linewidth=2,
                                     zorder=16)

            # Type 2 Reaction visualization
            if reaction_data.type2_detected:
                # Mark Type 2 retest area
                if reaction_data.type2_retest_date:
                    ax.axvline(x=reaction_data.type2_retest_date, color='magenta',
                              linestyle='--', linewidth=2.5, alpha=0.8, zorder=15)

                    # Mark Type 2 Terminal Bar
                    if reaction_data.type2_terminal_bar_date:
                        ax.axvline(x=reaction_data.type2_terminal_bar_date, color='cyan',
                                  linestyle=':', linewidth=2.5, alpha=0.8, zorder=15)

                        # Highlight the Type 2 retest zone
                        ax.axvspan(reaction_data.type2_retest_date, reaction_data.type2_terminal_bar_date,
                                  alpha=0.15, color='magenta', zorder=5)

        # Add title and labels
        direction = "BULLISH" if pattern.is_bullish else "BEARISH"
        interval_name = {'1d': 'Daily', '1wk': 'Weekly', '1mo': 'Monthly'}.get(interval, interval.upper())
        title = f"{ticker} - {direction} {pattern.pattern_type.upper()}"
        subtitle = f"{interval_name} Chart | Grade: {pattern.grade} | Detected: {pattern.d.date.date()} | R/R: {pattern.risk_reward:.2f}:1"
        ax.set_title(f"{title}\n{subtitle}", fontsize=14, fontweight='bold')
        ax.set_xlabel('Date', fontsize=12)
        ax.set_ylabel('Price ($)', fontsize=12)

        # Mark important dates on x-axis (pattern points and reactions)
        important_dates = [pattern.x.date, pattern.a.date, pattern.b.date,
                          pattern.c.date, pattern.d.date]
        important_labels = ['X', 'A', 'B', 'C', 'D']

        # Add reaction dates if available
        if reaction_data:
            if reaction_data.type1_detected and reaction_data.type1_reversal_date:
                important_dates.append(reaction_data.type1_reversal_date)
                important_labels.append('T1')
            if reaction_data.type2_detected and reaction_data.type2_terminal_bar_date:
                important_dates.append(reaction_data.type2_terminal_bar_date)
                important_labels.append('T2')

        # Set x-axis to show these important dates
        ax.set_xticks(important_dates)
        ax.set_xticklabels([f"{label}\n{date.strftime('%Y-%m-%d')}"
                           for label, date in zip(important_labels, important_dates)],
                          rotation=45, ha='right', fontsize=9, fontweight='bold')

        # Add minor ticks for other dates (less prominent)
        ax.xaxis.set_minor_locator(mdates.AutoDateLocator())
        ax.xaxis.set_minor_formatter(mdates.DateFormatter('%m/%d'))

        # Add grid with subtle styling
        ax.grid(True, alpha=0.2, linestyle='--', linewidth=0.5, zorder=0)
        ax.set_facecolor('#f8f9fa')

        # Calculate risk percentage
        risk_pct = abs((pattern.entry_price - pattern.stop_loss) / pattern.entry_price * 100)

        # Determine TP strategy display text
        tp_strategy_display = ""
        if hasattr(pattern, 'tp_strategy_used') and pattern.tp_strategy_used:
            tp_strategy_display = f"\nStrategy: {pattern.tp_strategy_used}"

        # Enhanced pattern info box (TOP LEFT)
        info_text = (
            f"TRADING LEVELS\n"
            f"{'─'*20}\n"
            f"Entry: ${pattern.entry_price:.2f}\n"
            f"Stop:  ${pattern.stop_loss:.2f}\n"
            f"Risk:  {risk_pct:.1f}%\n"
            f"\n"
            f"PROFIT TARGETS\n"
            f"{'─'*20}\n"
            f"T1: ${pattern.ipo_target_1:.2f}\n"
            f"T2: ${pattern.ipo_target_2:.2f}\n"
            f"T3: ${pattern.target_point_a:.2f}{tp_strategy_display}\n"
            f"\n"
            f"PATTERN METRICS\n"
            f"{'─'*20}\n"
            f"Tolerance: {pattern.tolerance_level}\n"
            f"Grade:     {pattern.grade}\n"
        )

        # Add reaction information if available
        if reaction_data:
            info_text += (
                f"\n"
                f"REACTION ANALYSIS\n"
                f"{'─'*20}\n"
            )

            if reaction_data.type1_detected:
                info_text += f"Type 1: YES\n"
                # Show Type 1 reversal price
                if reaction_data.type1_max_move:
                    info_text += f"  Price: ${reaction_data.type1_max_move:.2f}\n"
                # Show 38.2% target
                if reaction_data.target_382:
                    status_382 = "✓" if reaction_data.type1_reached_382 else "○"
                    info_text += f"  38.2% ({status_382}): ${reaction_data.target_382:.2f}\n"
                # Show 61.8% target
                if reaction_data.target_618:
                    status_618 = "✓" if reaction_data.type1_reached_618 else "○"
                    info_text += f"  61.8% ({status_618}): ${reaction_data.target_618:.2f}\n"
                if reaction_data.type1_trendline_broken:
                    info_text += f"  Trendline: BROKEN\n"
            else:
                info_text += f"Type 1: PENDING\n"

            if reaction_data.type2_detected:
                info_text += f"Type 2: YES\n"
                info_text += f"  PRZ Retested\n"
                # Show Type 2 retest price if available
                if hasattr(reaction_data, 'type2_retest_price') and reaction_data.type2_retest_price:
                    info_text += f"  Price: ${reaction_data.type2_retest_price:.2f}\n"
            elif reaction_data.type1_trendline_broken:
                info_text += f"Type 2: WATCHING\n"
        ax.text(0.02, 0.98, info_text, transform=ax.transAxes,
               fontsize=9, verticalalignment='top', horizontalalignment='left',
               family='monospace', zorder=20,
               bbox=dict(boxstyle='round,pad=0.8', facecolor='white',
                        edgecolor='gray', alpha=0.95, linewidth=2))

        # Add watermark/timestamp
        fig.text(0.99, 0.01, f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")}',
                ha='right', va='bottom', fontsize=8, color='gray', alpha=0.5)

        # Tight layout
        plt.tight_layout()

        # Save chart with higher DPI for better quality
        chart_filename = f"{ticker}_{pattern.pattern_type.replace(' ', '_')}_{pattern.d.date.date()}.png"
        chart_path = os.path.join(chart_dir, chart_filename)
        plt.savefig(chart_path, dpi=150, bbox_inches='tight', facecolor='white', edgecolor='none')
        plt.close()

        return chart_path

    def generate_signal(self, pattern: HarmonicPattern, current_price: float,
                       max_days_old: int = None, verbose: bool = False) -> Tuple[str, str]:
        """
        Generate trading signal based on Carney's exact framework from Volumes 1-3.

        Implements:
        - PRZ (Potential Reversal Zone) validation
        - Immediate reversal requirement
        - Pattern quality consideration
        - I.P.O. (Initial Profit Objective) profit targets

        Args:
            pattern: Detected harmonic pattern
            current_price: Current stock price
            max_days_old: Maximum age of pattern to consider (days). If None, uses MAX_DAYS_SINCE_PATTERN from config
            verbose: If True, generate detailed asset-specific explanation

        Returns:
            Tuple of (signal, explanation)
        """
        # Check pattern age - use config value if not specified
        if max_days_old is None:
            try:
                import config
                max_days_old = config.MAX_DAYS_SINCE_PATTERN if hasattr(config, 'MAX_DAYS_SINCE_PATTERN') else 730
            except ImportError:
                max_days_old = 730  # Default to 2 years if config not available

        if pattern.days_since_completion > max_days_old:
            return "HOLD", f"Pattern expired ({pattern.days_since_completion} days old, max {max_days_old}) - detected on {pattern.d.date.date()}"

        # Check risk/reward ratio from config - separate filters for LONG vs SHORT
        try:
            import config
            # Use different R/R filters based on pattern direction
            if pattern.is_bullish:
                # LONG (BUY) patterns - higher R/R potential
                min_rr = config.MIN_LONG_RISK_REWARD_RATIO if hasattr(config, 'MIN_LONG_RISK_REWARD_RATIO') else 1.5
                signal_type = "LONG"
            else:
                # SHORT (SELL) patterns - lower R/R due to limited downside
                min_rr = config.MIN_SHORT_RISK_REWARD_RATIO if hasattr(config, 'MIN_SHORT_RISK_REWARD_RATIO') else 1.5
                signal_type = "SHORT"
        except ImportError:
            min_rr = 1.5
            signal_type = "LONG" if pattern.is_bullish else "SHORT"

        if pattern.risk_reward < min_rr:
            return "HOLD", f"Risk/Reward too low for {signal_type} ({pattern.risk_reward:.2f}:1, minimum {min_rr}:1) - pattern detected on {pattern.d.date.date()}"

        # Check risk percentage from config
        try:
            import config
            max_risk_pct = config.MAX_ALLOWED_STOP_LOSS_PCT if hasattr(config, 'MAX_ALLOWED_STOP_LOSS_PCT') else 10.0
        except ImportError:
            max_risk_pct = 10.0

        risk_pct = abs((pattern.entry_price - pattern.stop_loss) / pattern.entry_price * 100)
        # Round to 1 decimal place to match display format and avoid floating-point precision issues
        # This ensures that a risk of 10.04% (displays as "10.0%") passes when max_risk_pct is 10.0%
        risk_pct_rounded = round(risk_pct, 1)
        if risk_pct_rounded > max_risk_pct:
            return "HOLD", f"Risk too high ({risk_pct:.1f}%, maximum {max_risk_pct:.1f}%) - pattern detected on {pattern.d.date.date()}"

        # PRZ tolerance based on pattern type
        # Extension patterns allow more volatility
        prz_tolerance = 0.03 if pattern.pattern_type in ['Butterfly', 'Crab', 'Deep Crab'] else 0.02

        # Check if current price is still within PRZ
        in_prz = False
        if pattern.is_bullish:
            # Bullish: price should be at or below entry (at D or lower)
            in_prz = current_price <= pattern.entry_price * (1 + prz_tolerance)
        else:
            # Bearish: price should be at or above entry (at D or higher)
            in_prz = current_price >= pattern.entry_price * (1 - prz_tolerance)

        # if not in_prz:
        #     return "HOLD", (
        #         f"{pattern.pattern_type} pattern detected on {pattern.d.date.date()} but price moved outside PRZ "
        #         f"(Current: ${current_price:.2f}, Entry: ${pattern.entry_price:.2f})"
        #     )

        # Check if stop loss hit
        # Get pattern spec for detailed stop loss information
        pattern_spec = get_pattern_spec(pattern.pattern_type.lower().replace(' ', '_'))

        if pattern.is_bullish:
            if current_price < pattern.stop_loss:
                if verbose:
                    return "HOLD", (
                        f"Stop loss hit for {pattern.pattern_type} pattern (detected {pattern.d.date.date()})\n"
                        f"  Current Price: ${current_price:.2f} < Stop Loss: ${pattern.stop_loss:.2f}\n"
                        f"  Stop Loss Level: {pattern_spec.stop_loss_ratio:.2f} x XA\n"
                        f"  X Point: ${pattern.x.price:.2f}\n"
                        f"  Pattern invalidated - price fell below {pattern_spec.stop_loss_ratio}:1 XA ratio"
                    )
                else:
                    return "HOLD", (
                        f"Stop loss hit: {pattern.pattern_type} pattern (detected {pattern.d.date.date()}) "
                        f"- Price ${current_price:.2f} < Stop ${pattern.stop_loss:.2f}, "
                        f"{pattern_spec.stop_loss_ratio}x XA from ${pattern.x.price:.2f}"
                    )
        else:
            if current_price > pattern.stop_loss:
                if verbose:
                    return "HOLD", (
                        f"Stop loss hit for {pattern.pattern_type} pattern (detected {pattern.d.date.date()})\n"
                        f"  Current Price: ${current_price:.2f} > Stop Loss: ${pattern.stop_loss:.2f}\n"
                        f"  Stop Loss Level: {pattern_spec.stop_loss_ratio:.2f} x XA\n"
                        f"  X Point: ${pattern.x.price:.2f}\n"
                        f"  Pattern invalidated - price rose above {pattern_spec.stop_loss_ratio}:1 XA ratio"
                    )
                else:
                    return "HOLD", (
                        f"Stop loss hit: {pattern.pattern_type} pattern (detected {pattern.d.date.date()}) "
                        f"- Price ${current_price:.2f} > Stop ${pattern.stop_loss:.2f}, "
                        f"{pattern_spec.stop_loss_ratio}x XA from ${pattern.x.price:.2f}"
                    )

        # Generate signal based on pattern direction
        if pattern.is_bullish:
            signal = "BUY"
            direction = "BULLISH"
        else:
            signal = "SELL"
            direction = "BEARISH"

        # Build explanation (detailed or standard based on verbose flag)
        if verbose:
            explanation = self._generate_verbose_explanation(pattern, current_price, signal, direction)
        else:
            # Standard concise explanation
            explanation = (
                f"{direction} {pattern.pattern_type.upper()} - Grade {pattern.grade} - Detected {pattern.d.date.date()}\n"
                f"  Entry: ${pattern.entry_price:.2f} | Stop: ${pattern.stop_loss:.2f}\n"
                f"  T1: ${pattern.ipo_target_1:.2f} | T2: ${pattern.ipo_target_2:.2f} | T3: ${pattern.target_point_a:.2f}\n"
                f"  Risk/Reward: {pattern.risk_reward:.2f}:1\n"
                f"  Tolerance: {pattern.tolerance_level}"
            )

        return signal, explanation

    def _generate_verbose_explanation(self, pattern: HarmonicPattern, current_price: float,
                                     signal: str, direction: str) -> str:
        """
        Generate detailed, asset-specific explanation for the trading signal.

        Args:
            pattern: Detected harmonic pattern
            current_price: Current stock price
            signal: BUY/SELL/HOLD
            direction: BULLISH/BEARISH

        Returns:
            Detailed multi-line explanation
        """
        lines = []

        # Header
        lines.append(f"{'='*70}")
        lines.append(f"{direction} {pattern.pattern_type.upper()} PATTERN - {signal} SIGNAL")
        lines.append(f"Grade: {pattern.grade} | Tolerance: {pattern.tolerance_level}")
        lines.append(f"{'='*70}")
        lines.append("")

        # Pattern completion details
        lines.append("PATTERN COMPLETION:")
        lines.append(f"  Completed at Point D: ${pattern.d.price:.2f} on {pattern.d.date.date()}")
        lines.append(f"  Current Price: ${current_price:.2f}")
        price_change = ((current_price - pattern.d.price) / pattern.d.price) * 100
        lines.append(f"  Price Change Since D: {price_change:+.2f}%")
        lines.append(f"  Days Since Completion: {pattern.days_since_completion}")
        lines.append("")

        # Pattern structure
        lines.append("PATTERN STRUCTURE:")
        lines.append(f"  X: ${pattern.x.price:.2f} ({pattern.x.date.date()})")
        lines.append(f"  A: ${pattern.a.price:.2f} ({pattern.a.date.date()})")
        lines.append(f"  B: ${pattern.b.price:.2f} ({pattern.b.date.date()})")
        lines.append(f"  C: ${pattern.c.price:.2f} ({pattern.c.date.date()})")
        lines.append(f"  D: ${pattern.d.price:.2f} ({pattern.d.date.date()})")

        # Multi-swing BC information
        if pattern.is_multi_swing_bc:
            lines.append("")
            lines.append(f"  ⚡ MULTI-SWING BC LEG DETECTED:")
            lines.append(f"    Internal swings: {pattern.bc_internal_swing_count} (filtered ≥0.236 BC)")
            lines.append(f"    BC volatility: {pattern.bc_volatility:.2f}")
            lines.append(f"    BC duration: {pattern.bc_duration_bars} bars")
            lines.append(f"    BC macro ratio: {pattern.bc_ab_ratio:.3f} (measured B→C)")

        lines.append("")

        # Fibonacci validation
        lines.append("FIBONACCI VALIDATION (Carney's Exact Ratios):")
        pattern_spec = get_pattern_spec(pattern.pattern_type.lower().replace(' ', '_'))

        # B point validation
        b_target = (pattern_spec.b_point_min + pattern_spec.b_point_max) / 2
        b_match = "✓" if pattern_spec.b_point_min <= pattern.ab_xa_ratio <= pattern_spec.b_point_max else "✗"
        lines.append(f"  {b_match} B Point: {pattern.ab_xa_ratio:.3f} (Target: {b_target:.3f}, "
                    f"Range: {pattern_spec.b_point_min:.3f}-{pattern_spec.b_point_max:.3f})")

        # BC projection validation
        bc_target = (pattern_spec.bc_projection_min + pattern_spec.bc_projection_max) / 2
        bc_match = "✓" if pattern_spec.bc_projection_min <= pattern.bc_projection <= pattern_spec.bc_projection_max else "✗"
        lines.append(f"  {bc_match} BC Projection: {pattern.bc_projection:.3f} (Target: {bc_target:.3f}, "
                    f"Range: {pattern_spec.bc_projection_min:.3f}-{pattern_spec.bc_projection_max:.3f})")

        # D point validation
        d_target = (pattern_spec.d_point_min + pattern_spec.d_point_max) / 2
        d_match = "✓" if pattern_spec.d_point_min <= pattern.ad_xa_ratio <= pattern_spec.d_point_max else "✗"
        lines.append(f"  {d_match} D Point: {pattern.ad_xa_ratio:.3f} (Target: {d_target:.3f}, "
                    f"Range: {pattern_spec.d_point_min:.3f}-{pattern_spec.d_point_max:.3f})")
        lines.append("")

        # PRZ Analysis
        lines.append("PRZ (POTENTIAL REVERSAL ZONE) ANALYSIS:")
        if pattern.is_bullish:
            prz_status = "In PRZ" if current_price <= pattern.entry_price * 1.03 else "Outside PRZ"
        else:
            prz_status = "In PRZ" if current_price >= pattern.entry_price * 0.97 else "Outside PRZ"
        lines.append(f"  Status: {prz_status}")
        lines.append(f"  Entry Price (Point D): ${pattern.entry_price:.2f}")
        lines.append(f"  Current Distance from Entry: {abs(current_price - pattern.entry_price):.2f} "
                    f"({abs((current_price - pattern.entry_price) / pattern.entry_price * 100):.2f}%)")
        lines.append("")

        # Trading specifications
        lines.append("TRADING SPECIFICATIONS (Per Scott Carney):")
        lines.append(f"  Entry: ${pattern.entry_price:.2f}")
        lines.append(f"  Stop Loss: ${pattern.stop_loss:.2f}")
        stop_distance = abs(pattern.entry_price - pattern.stop_loss)
        lines.append(f"  Stop Distance: ${stop_distance:.2f} ({(stop_distance/pattern.entry_price*100):.2f}%)")
        lines.append("")

        # Profit targets (I.P.O. method)
        lines.append("PROFIT TARGETS (I.P.O. Method - Pattern Range):")
        lines.append(f"  Target 1 (0.382 I.P.O.): ${pattern.ipo_target_1:.2f}")
        t1_gain = abs(pattern.ipo_target_1 - pattern.entry_price)
        t1_pct = (t1_gain / pattern.entry_price) * 100
        lines.append(f"    Potential Gain: ${t1_gain:.2f} ({t1_pct:.2f}%)")

        lines.append(f"  Target 2 (0.618 I.P.O.): ${pattern.ipo_target_2:.2f}")
        t2_gain = abs(pattern.ipo_target_2 - pattern.entry_price)
        t2_pct = (t2_gain / pattern.entry_price) * 100
        lines.append(f"    Potential Gain: ${t2_gain:.2f} ({t2_pct:.2f}%)")

        lines.append(f"  Target 3 (Point A): ${pattern.target_point_a:.2f}")
        t3_gain = abs(pattern.target_point_a - pattern.entry_price)
        t3_pct = (t3_gain / pattern.entry_price) * 100
        lines.append(f"    Potential Gain: ${t3_gain:.2f} ({t3_pct:.2f}%)")
        lines.append("")

        # Risk/Reward
        lines.append("RISK/REWARD ANALYSIS:")
        lines.append(f"  Risk: ${stop_distance:.2f} ({(stop_distance/pattern.entry_price*100):.2f}%)")
        lines.append(f"  Reward (to T1): ${t1_gain:.2f} ({t1_pct:.2f}%)")
        lines.append(f"  Risk/Reward Ratio: {pattern.risk_reward:.2f}:1")
        if pattern.risk_reward >= 3.0:
            lines.append(f"  Assessment: EXCELLENT - Exceeds 3:1 ratio")
        elif pattern.risk_reward >= 2.0:
            lines.append(f"  Assessment: GOOD - Meets 2:1 minimum")
        elif pattern.risk_reward >= 1.5:
            lines.append(f"  Assessment: ACCEPTABLE - Above 1.5:1")
        else:
            lines.append(f"  Assessment: POOR - Below recommended minimum")
        lines.append("")

        # Pattern-specific notes
        lines.append("PATTERN-SPECIFIC NOTES:")
        if pattern.pattern_type == "Gartley":
            lines.append("  • Gartley: Most common harmonic pattern")
            lines.append("  • B point must be precise 0.618 (±3%)")
            lines.append("  • BC projection MUST NOT exceed 1.618 (else it's a Bat)")
            lines.append("  • Price should NOT extend beyond PRZ")
            lines.append("  • Stop loss just beyond 1.0 XA")
        elif pattern.pattern_type == "Bat":
            lines.append("  • Bat: 0.886 is THE MOST IMPORTANT number")
            lines.append("  • Incredibly accurate pattern with smaller stop loss")
            lines.append("  • B point must be <0.618 (preferably 0.50 or 0.382)")
            lines.append("  • BC projection must be ≥1.618")
            lines.append("  • Price must reverse immediately after testing 0.886")
        elif pattern.pattern_type == "Butterfly":
            lines.append("  • Butterfly: Extension pattern (goes beyond X)")
            lines.append("  • 1.27 XA is THE MOST CRITICAL number")
            lines.append("  • NO 1.618 XA projection (that would be Crab)")
            lines.append("  • B point must be 0.786 (±3% max)")
            lines.append("  • Works extremely well in new high/low territory")
        elif pattern.pattern_type == "Crab":
            lines.append("  • Crab: Extreme extension pattern")
            lines.append("  • 1.618 XA is defining limit")
            lines.append("  • Extreme BC projection (2.618, 3.14, or 3.618)")
            lines.append("  • Price may exceed 1.618 with volatile action")
            lines.append("  • Larger stop loss required (>2.0 XA)")
        elif pattern.pattern_type == "Deep Crab":
            lines.append("  • Deep Crab: Variation of Crab with deeper B")
            lines.append("  • B point @ 0.886 is minimum and must be tested")
            lines.append("  • Has +5% tolerance on B point")
            lines.append("  • Less prevalent than regular Crab")
        elif pattern.pattern_type == "Alternate Bat":
            lines.append("  • Alternate Bat: Extension beyond standard Bat")
            lines.append("  • B point must be ≤0.382")
            lines.append("  • Extends to 0.886-1.13 XA")
            lines.append("  • Valid reversals often occur at 1.13 precisely")
        lines.append("")

        # Signal justification
        lines.append("SIGNAL JUSTIFICATION:")
        if signal == "BUY":
            lines.append(f"  ✓ Bullish {pattern.pattern_type} pattern completed at ${pattern.entry_price:.2f}")
            lines.append(f"  ✓ Current price ${current_price:.2f} is within PRZ tolerance")
            lines.append(f"  ✓ Risk/Reward ratio of {pattern.risk_reward:.2f}:1 meets minimum")
            lines.append(f"  ✓ All Fibonacci ratios validated per Carney's specifications")
            lines.append("")
            lines.append(f"  RECOMMENDATION: Consider buying at current price ${current_price:.2f}")
            lines.append(f"  Place stop loss at ${pattern.stop_loss:.2f}")
            lines.append(f"  Take partial profits at T1: ${pattern.ipo_target_1:.2f}")
        elif signal == "SELL":
            lines.append(f"  ✓ Bearish {pattern.pattern_type} pattern completed at ${pattern.entry_price:.2f}")
            lines.append(f"  ✓ Current price ${current_price:.2f} is within PRZ tolerance")
            lines.append(f"  ✓ Risk/Reward ratio of {pattern.risk_reward:.2f}:1 meets minimum")
            lines.append(f"  ✓ All Fibonacci ratios validated per Carney's specifications")
            lines.append("")
            lines.append(f"  RECOMMENDATION: Consider selling/shorting at current price ${current_price:.2f}")
            lines.append(f"  Place stop loss at ${pattern.stop_loss:.2f}")
            lines.append(f"  Take partial profits at T1: ${pattern.ipo_target_1:.2f}")

        lines.append(f"{'='*70}")

        return "\n".join(lines)


if __name__ == "__main__":
    # Test improved Carney-based detector
    import yfinance as yf

    print("="*80)
    print("IMPROVED HARMONIC PATTERN DETECTOR TEST")
    print("Pyharmonics Peak Detection + Carney's Exact Rules (Volumes 1-3)")
    print("="*80)
    print()

    # Download test data
    ticker = yf.Ticker("AAPL")
    df = ticker.history(period="6mo")
    df.columns = [c.lower() for c in df.columns]

    print(f"Testing on AAPL - {len(df)} days of data")
    print()

    # Create detector with Carney's specifications
    detector = PatternDetector()

    # Detect patterns
    patterns = detector.detect_patterns(df, "AAPL")

    print(f"Found {len(patterns)} harmonic patterns using Carney's exact specifications")
    print()

    # Display patterns
    for i, pattern in enumerate(patterns[:5], 1):  # Show first 5
        current_price = df['close'].iloc[-1]
        signal, explanation = detector.generate_signal(pattern, current_price)

        print(f"Pattern {i}: {pattern.pattern_type.upper()} ({'BULLISH' if pattern.is_bullish else 'BEARISH'}) [Grade {pattern.grade}]")
        print(f"  Points: X=${pattern.x.price:.2f} -> A=${pattern.a.price:.2f} -> B=${pattern.b.price:.2f} -> C=${pattern.c.price:.2f} -> D=${pattern.d.price:.2f}")
        print(f"  Date Range: {pattern.x.date.date()} to {pattern.d.date.date()}")
        print(f"  Ratios: AB/XA={pattern.ab_xa_ratio:.3f}, BC_proj={pattern.bc_projection:.3f}, AD/XA={pattern.ad_xa_ratio:.3f}")
        print(f"  Signal: {signal}")
        print(f"  {explanation}")
        print()
