"""
Hybrid Harmonic Pattern Detector
Uses Pyharmonics peak detection with Scott Carney's exact trading rules from Volumes 1, 2, and 3
"""

import pandas as pd
import numpy as np
from typing import List, Optional, Tuple, Dict, Any
from dataclasses import dataclass
from pyharmonics import OHLCTechnicals as Technicals
from pyharmonics.search import HarmonicSearch
from carney_patterns import (
    CARNEY_PATTERNS, get_pattern_spec, PatternSpec,
    differentiate_gartley_vs_bat, differentiate_butterfly_vs_crab,
    calculate_ipo_target, calculate_382_trailer, calculate_stop_loss,
    calculate_prz_levels
)
# Configure matplotlib for thread-safety before importing pyplot
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend, thread-safe
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
import os

# Import config for SWING_WINDOW
try:
    import config  # type: ignore
except ImportError:
    class config:  # type: ignore
        SWING_WINDOW = 3  # Default for weekly data
        TP_STRATEGY = 'SCOTT'  # Default strategy

# Import TP strategies
from tp_strategies import ScottStrategy, MitchStrategy, PositionStrategy, TPStrategy
from tp_strategies.base import format_target, target_allocations
from utils import ConfigHelper
from logging_config import get_logger
from chart_generator import ChartGenerator
from exceptions import (
    PatternConversionError,
    PatternValidationError,
    TemporalValidationError
)

logger = get_logger(__name__)


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
    ipo_target_1: Optional[float]  # First supported target, if available
    ipo_target_2: Optional[float]  # Secondary target
    target_point_a: Optional[float]  # Final supported target, not necessarily point A
    risk_reward: float

    # PRZ (Potential Reversal Zone) levels
    prz_levels: Dict[str, float]

    # D-Point Range (PRZ boundaries)
    d_point_range_min: float = 0.0  # Minimum valid D-point price (lower bound of PRZ)
    d_point_range_max: float = 0.0  # Maximum valid D-point price (upper bound of PRZ)

    days_since_completion: int = 0
    # pattern_quality: str = "STANDARD"  # EXCELLENT, GOOD, STANDARD - REMOVED
    tolerance_level: str = "Standard"  # Textbook, Standard, or Relaxed
    grade: str = "B"  # A+, A, A-, B+, B, B-, C+, C, C-
    trade_quality: str = "Standard Trade"  # High-Probability Entry, Standard Trade, Standard / Reduced Size, Marginal / Scalp Only
    chart_path: str = ""  # Path to pattern visualization chart
    tp_strategy_used: str = ""  # Detailed target provenance for reports
    tp_strategy_name: str = ""  # Configured TP strategy name
    tp_target_details: Tuple[Optional[str], Optional[str], Optional[str]] = (
        None, None, None
    )
    origin: Optional[Point] = None  # Unmeasured 0 point that precedes a 5-0 structure

    # Multi-swing BC leg metadata
    is_multi_swing_bc: bool = False  # True if BC leg contains multiple internal swings
    bc_internal_swing_count: int = 0  # Number of internal swings within BC leg (0 = simple BC)
    bc_volatility: float = 0.0  # Volatility within BC leg (std dev of internal swings)
    bc_duration_bars: int = 0  # Number of bars from B to C
    divergence: Optional[Dict[str, Any]] = None  # Descriptive, context-specific momentum evidence


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

    def __init__(self) -> None:
        """Initialize detector with Carney's exact specifications"""
        self.patterns = CARNEY_PATTERNS
        self.pattern_priority = [
            'gartley', 'bat', 'alternate_bat',
            'butterfly', 'crab', 'deep_crab',
            'cypher', 'shark', '5_0'
        ]
        self._tp_strategy_cache = None  # Cache the strategy instance
        self.config_helper = ConfigHelper(config)  # Configuration helper
        self.chart_generator = ChartGenerator(dpi=150)  # Chart generator

    def _get_tp_strategy(self) -> TPStrategy:
        """
        Get the appropriate take profit strategy based on config.TP_STRATEGY.

        Returns:
            TPStrategy instance (ScottStrategy, MitchStrategy, or PositionStrategy)
        """
        if self._tp_strategy_cache is not None:
            return self._tp_strategy_cache

        strategy_name = self.config_helper.get('TP_STRATEGY', 'SCOTT')
        swing_window = self.config_helper.get_int('SWING_WINDOW', 5)

        if strategy_name == 'MITCH':
            self._tp_strategy_cache = MitchStrategy(
                swing_window=swing_window,
                tp_min_spacing_pct=self.config_helper.get_float('TP_MIN_SPACING_PCT', 30.0),
                tp_min_entry_distance_pct=self.config_helper.get_float('TP_MIN_ENTRY_DISTANCE_PCT', 20.0),
                tp_atr_multiplier=self.config_helper.get_float('TP_ATR_MULTIPLIER', 1.0),
            )
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
        peak_spacing = self.config_helper.get_int('SWING_WINDOW', 3)
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

        detected_patterns.extend(
            self._detect_five_zero_patterns(tech, df, fib_tolerance, symbol)
        )

        # Show summary if patterns were rejected
        verbose = self.config_helper.get_bool('VERBOSE_REPORTS', False)
        if rejected_count > 0:
            # Always log rejections at DEBUG level for troubleshooting
            logger.debug("%s: %d pattern(s) rejected (invalid duration)", symbol, rejected_count)
            if verbose:
                logger.info("%s: %d pattern(s) rejected (invalid duration)", symbol, rejected_count)

        return detected_patterns

    def _convert_pyharmonics_pattern(self, py_pattern: Any, df: pd.DataFrame, tech: Technicals, fib_tolerance: float, symbol: str) -> Optional[HarmonicPattern]:
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
            # Step 1: Extract XABCD points
            points = self._extract_pattern_points(py_pattern, df)
            if not points:
                return None

            # Step 2: Validate temporal proportionality
            is_valid, reason = self._validate_temporal_proportionality(
                points['x'].date, points['a'].date, points['b'].date,
                points['c'].date, points['d'].date
            )
            if not is_valid:
                return None

            # Step 3: Calculate Fibonacci ratios
            ratios = self._calculate_fibonacci_ratios(py_pattern)

            # Step 4: Get pattern specification and calculate trading specs
            pattern_spec = self._get_pattern_specification(py_pattern)
            if not pattern_spec:
                return None

            trading_specs = self._calculate_trading_specifications(
                points, ratios, pattern_spec, df, symbol
            )

            # Step 5: Calculate pattern grade
            grade = self._calculate_pyharmonics_grade(
                ratios['ab_xa'], ratios['bc_ab'], ratios['ad_xa'],
                ratios['bc_projection'],
                pattern_spec, fib_tolerance,
                points['x'].price, points['a'].price, points['b'].price,
                points['c'].price, points['d'].price,
                points['x'].date, points['a'].date, points['b'].date,
                points['c'].date, points['d'].date
            )

            # Step 6: Create HarmonicPattern object
            return self._create_harmonic_pattern(
                points, ratios, pattern_spec, trading_specs, grade, fib_tolerance
            )

        except PatternConversionError as e:
            logger.debug("[%s] Pattern conversion failed for %s: %s", symbol, py_pattern.name, e)
            return None
        except (PatternValidationError, TemporalValidationError) as e:
            logger.debug("[%s] Pattern validation failed for %s: %s", symbol, py_pattern.name, e)
            return None
        except (ValueError, KeyError, AttributeError) as e:
            # Expected errors from pyharmonics data access
            logger.debug("[%s] Invalid pattern data for %s: %s", symbol, py_pattern.name, e)
            return None
        except Exception as e:
            # Truly unexpected errors - convert to PatternConversionError with chaining
            logger.warning("[%s] Unexpected error converting pyharmonics pattern %s: %s", symbol, py_pattern.name, e)
            raise PatternConversionError(
                f"Unexpected error converting {py_pattern.name}", ticker=symbol
            ) from e

    def _detect_five_zero_patterns(
        self,
        tech: Technicals,
        df: pd.DataFrame,
        fib_tolerance: float,
        symbol: str
    ) -> List[HarmonicPattern]:
        """Detect completed 0-X-A-B-C-D structures from alternating swings."""
        pattern_spec = self.patterns['5_0']
        detected: List[HarmonicPattern] = []

        for points in self._find_five_zero_candidates(tech, fib_tolerance):
            is_valid, _ = self._validate_temporal_proportionality(
                points['x'].date, points['a'].date, points['b'].date,
                points['c'].date, points['d'].date
            )
            if not is_valid:
                continue

            ratios = self._calculate_five_zero_ratios(points)
            trading_specs = self._calculate_trading_specifications(
                points, ratios, pattern_spec, df, symbol
            )
            grade = self._calculate_pyharmonics_grade(
                ratios['ab_xa'], ratios['bc_ab'], ratios['ad_xa'],
                ratios['bc_projection'], pattern_spec, fib_tolerance,
                points['x'].price, points['a'].price, points['b'].price,
                points['c'].price, points['d'].price,
                points['x'].date, points['a'].date, points['b'].date,
                points['c'].date, points['d'].date
            )
            detected.append(
                self._create_harmonic_pattern(
                    points, ratios, pattern_spec, trading_specs, grade,
                    fib_tolerance
                )
            )

        return detected

    def _find_five_zero_candidates(
        self,
        tech: Technicals,
        fib_tolerance: float
    ) -> List[Dict[str, Any]]:
        """Return valid 5-0 candidates from six consecutive swing points."""
        candidates: List[Dict[str, Any]] = []
        swings = self._collapse_same_type_swings(tech.peak_data)
        pattern_spec = self.patterns['5_0']

        for start in range(len(swings) - 5):
            window = swings[start:start + 6]
            if any(window[i][2] == window[i + 1][2] for i in range(5)):
                continue

            point_names = ('origin', 'x', 'a', 'b', 'c', 'd')
            points: Dict[str, Any] = {}
            for point_index, (name, swing) in enumerate(zip(point_names, window)):
                data_index, price, swing_type = swing
                points[name] = Point(
                    index=point_index - 1,
                    price=float(price),
                    date=pd.Timestamp(tech.df.index[data_index]),
                    swing_type='PEAK' if swing_type == 1 else 'TROUGH'
                )

            points['is_bullish'] = window[0][2] == 0
            try:
                ratios = self._calculate_five_zero_ratios(points)
            except PatternValidationError:
                continue
            if self._validate_five_zero_structure(
                ratios, pattern_spec, fib_tolerance
            ):
                candidates.append(points)

        return candidates

    @staticmethod
    def _collapse_same_type_swings(
        swings: List[Tuple[int, float, int]]
    ) -> List[Tuple[int, float, int]]:
        """Keep the most extreme swing when adjacent points have the same type."""
        collapsed: List[Tuple[int, float, int]] = []
        for swing in swings:
            if not collapsed or collapsed[-1][2] != swing[2]:
                collapsed.append(swing)
                continue

            previous = collapsed[-1]
            is_more_extreme = (
                swing[1] > previous[1] if swing[2] == 1
                else swing[1] < previous[1]
            )
            if is_more_extreme:
                collapsed[-1] = swing

        return collapsed

    def _extract_pattern_points(self, py_pattern: Any, df: pd.DataFrame) -> Optional[Dict[str, Point]]:
        """
        Extract XABCD points from pyharmonics pattern.

        Args:
            py_pattern: pyharmonics XABCDPattern object
            df: Price dataframe

        Returns:
            Dictionary of points {'x': Point, 'a': Point, ...}, or None if extraction fails
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

            return {
                'x': x_point,
                'a': a_point,
                'b': b_point,
                'c': c_point,
                'd': d_point,
                'is_bullish': is_bullish
            }

        except (ValueError, KeyError, IndexError, AttributeError) as e:
            raise PatternConversionError(
                f"Failed to extract points from pyharmonics pattern: {e}",
                source_format="pyharmonics",
                target_format="Point"
            ) from e
        except Exception as e:
            # Unexpected errors
            raise PatternConversionError(
                f"Unexpected error extracting points: {e}",
                source_format="pyharmonics",
                target_format="Point"
            ) from e

    def _calculate_fibonacci_ratios(self, py_pattern: Any) -> Dict[str, float]:
        """
        Calculate Fibonacci ratios from pyharmonics pattern.

        Args:
            py_pattern: pyharmonics XABCDPattern object

        Returns:
            Dictionary containing all Fibonacci ratios
        """
        from pyharmonics import constants

        # Use Fibonacci ratios from pyharmonics (trust their calculations)
        # py_pattern.retraces contains:
        #   'XAB'   = AB/XA ratio (B-point)
        #   'ABC'   = BC/AB ratio (C-point retracement)
        #   'BCD'   = CD/BC ratio (BC projection)
        #   'XABCD' = XD/XA ratio (D-point completion)
        ab_xa = py_pattern.retraces.get(constants.XAB, 0)
        bc_ab = py_pattern.retraces.get(constants.ABC, 0)
        bc_projection = py_pattern.retraces.get(constants.BCD, 0)
        cd_bc = bc_projection  # Same as BCD
        ad_xa = py_pattern.retraces.get(constants.XABCD, 0)

        return {
            'ab_xa': ab_xa,
            'bc_ab': bc_ab,
            'bc_projection': bc_projection,
            'cd_bc': cd_bc,
            'ad_xa': ad_xa
        }

    def _calculate_five_zero_ratios(
        self,
        points: Dict[str, Point]
    ) -> Dict[str, float]:
        """Calculate the 5-0 ratios from the legs defined by Carney."""
        xa = abs(points['a'].price - points['x'].price)
        ab = abs(points['b'].price - points['a'].price)
        bc = abs(points['c'].price - points['b'].price)
        cd = abs(points['d'].price - points['c'].price)

        if min(xa, ab, bc) == 0:
            raise PatternValidationError("5-0 pattern contains a zero-length leg")

        return {
            'ab_xa': ab / xa,
            'bc_ab': bc / ab,
            'bc_projection': cd / bc,
            'cd_bc': cd / bc,
            'ad_xa': abs(points['d'].price - points['x'].price) / xa,
            'cd_ab': cd / ab,
        }

    @staticmethod
    def _get_pattern_validation_tolerance(_fib_tolerance: float) -> float:
        """Return tolerance used for Carney pattern validation.

        pyharmonics' fib_tolerance is only for library-side candidate discovery.
        Carney's pattern definitions are authoritative, so validation must not be
        widened by the pyharmonics setting.
        """
        return 0.0

    def _validate_five_zero_structure(
        self,
        ratios: Dict[str, float],
        pattern_spec: PatternSpec,
        fib_tolerance: float
    ) -> bool:
        """Validate the four defining measurements of a 5-0 pattern."""
        validation_tolerance = self._get_pattern_validation_tolerance(fib_tolerance)
        return (
            pattern_spec.b_point_min - validation_tolerance
            <= ratios['ab_xa']
            <= pattern_spec.b_point_max + validation_tolerance
            and pattern_spec.c_point_min - validation_tolerance
            <= ratios['bc_ab']
            <= pattern_spec.c_point_max + validation_tolerance
            and abs(ratios['cd_bc'] - 0.50) <= validation_tolerance
            and abs(ratios['cd_ab'] - 1.0) <= validation_tolerance
        )

    def _get_pattern_specification(self, py_pattern: Any) -> Optional[PatternSpec]:
        """
        Get pattern specification from pyharmonics pattern name.

        Args:
            py_pattern: pyharmonics XABCDPattern object

        Returns:
            PatternSpec object, or None if pattern type is unknown
        """
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
        }
        pattern_type = pattern_name_map.get(py_pattern.name.lower(), py_pattern.name.lower())

        # Get pattern spec for Carney trading rules
        pattern_spec = get_pattern_spec(pattern_type)
        return pattern_spec

    def _calculate_trading_specifications(
        self,
        points: Dict[str, Any],
        ratios: Dict[str, float],
        pattern_spec: PatternSpec,
        df: pd.DataFrame,
        symbol: str
    ) -> Dict[str, Any]:
        """
        Calculate trading specifications (entry, stop, targets).

        Args:
            points: Dictionary containing XABCD points and is_bullish flag
            ratios: Dictionary containing Fibonacci ratios
            pattern_spec: Pattern specification
            df: Price dataframe
            symbol: Stock ticker symbol

        Returns:
            Dictionary containing all trading specifications
        """
        # Extract prices and metadata
        x_price = points['x'].price
        a_price = points['a'].price
        b_price = points['b'].price
        c_price = points['c'].price
        d_price = points['d'].price
        is_bullish = points['is_bullish']

        # Calculate basic trading parameters
        entry_price = d_price
        xa_range = abs(a_price - x_price)
        prz_levels = calculate_prz_levels(x_price, a_price, b_price, c_price, pattern_spec)

        # Calculate D-point range (PRZ boundaries)
        prz_tolerance_pct = self.config_helper.get_float('PRZ_TOLERANCE_PCT', 0.02)
        d_point_range_min = d_price * (1 - prz_tolerance_pct)
        d_point_range_max = d_price * (1 + prz_tolerance_pct)

        # Calculate stop loss
        stop_loss = self._calculate_stop_loss(
            pattern_spec, x_price, a_price, b_price, c_price, d_price,
            xa_range, is_bullish, df, points['d'].date, symbol
        )

        # Calculate profit targets
        tp_result = self._calculate_profit_targets(
            x_price, a_price, b_price, c_price, d_price,
            is_bullish, df, points['d'].date, symbol
        )

        # Calculate risk/reward ratio
        risk_reward = self._calculate_risk_reward(
            entry_price, stop_loss, tp_result['ipo_target_1'],
            tp_result['ipo_target_2'], tp_result['target_point_a']
        )

        return {
            'entry_price': entry_price,
            'stop_loss': stop_loss,
            'ipo_target_1': tp_result['ipo_target_1'],
            'ipo_target_2': tp_result['ipo_target_2'],
            'target_point_a': tp_result['target_point_a'],
            'risk_reward': risk_reward,
            'prz_levels': prz_levels,
            'd_point_range_min': d_point_range_min,
            'd_point_range_max': d_point_range_max,
            'tp_strategy_used': tp_result['tp_strategy_used'],
            'tp_strategy_name': tp_result['tp_strategy_name'],
            'tp_target_details': tp_result['tp_target_details'],
        }

    def _calculate_stop_loss(
        self,
        pattern_spec: PatternSpec,
        x_price: float,
        a_price: float,
        b_price: float,
        c_price: float,
        d_price: float,
        xa_range: float,
        is_bullish: bool,
        df: pd.DataFrame,
        d_ts: pd.Timestamp,
        symbol: str
    ) -> float:
        """Calculate stop loss with optional strategy override."""
        # Base stop loss using Carney's pattern-specific ratio
        stop_loss = calculate_stop_loss(pattern_spec, x_price, xa_range, is_bullish)

        # Get TP strategy for potential stop loss override
        tp_strategy = self._get_tp_strategy()

        # Determine pattern high/low for strategy calculations
        pattern_high = a_price if is_bullish else d_price
        pattern_low = d_price if is_bullish else a_price

        # Find d_index in dataframe
        try:
            d_index = df.index.get_loc(df.index[df.index >= d_ts][0])
        except (IndexError, KeyError):
            d_index = len(df) - 1

        # Check if TP strategy has custom stop loss calculation
        max_allowed_stop_loss_pct = self.config_helper.get_float('MAX_ALLOWED_STOP_LOSS_PCT', 10.0)
        min_allowed_stop_loss_pct = self.config_helper.get_float('MIN_ALLOWED_STOP_LOSS_PCT', 3.0)

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

        # Use strategy's stop loss if provided
        return strategy_stop_loss if strategy_stop_loss is not None else stop_loss

    def _calculate_profit_targets(
        self,
        x_price: float,
        a_price: float,
        b_price: float,
        c_price: float,
        d_price: float,
        is_bullish: bool,
        df: pd.DataFrame,
        d_ts: pd.Timestamp,
        symbol: str
    ) -> Dict[str, Any]:
        """Calculate profit targets using TP strategy."""
        # Determine pattern high/low
        pattern_high = a_price if is_bullish else d_price
        pattern_low = d_price if is_bullish else a_price

        # Find d_index in dataframe
        try:
            d_index = df.index.get_loc(df.index[df.index >= d_ts][0])
        except (IndexError, KeyError):
            d_index = len(df) - 1

        # Get TP strategy and calculate targets
        tp_strategy = self._get_tp_strategy()
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

        return {
            'ipo_target_1': tp_targets.primary,
            'ipo_target_2': tp_targets.secondary,
            'target_point_a': tp_targets.final,
            'tp_strategy_used': tp_targets.tp_strategy_used if hasattr(tp_targets, 'tp_strategy_used') else "",
            'tp_strategy_name': tp_strategy.get_strategy_name(),
            'tp_target_details': tp_targets.target_details,
        }

    def _calculate_risk_reward(
        self,
        entry_price: float,
        stop_loss: float,
        target_1: Optional[float],
        target_2: Optional[float],
        target_3: Optional[float]
    ) -> float:
        """Calculate weighted reward, closing the remainder at the last target."""
        risk = abs(entry_price - stop_loss)
        targets = (target_1, target_2, target_3)
        weights = target_allocations(
            targets,
            (config.POSITION_SIZE_T1, config.POSITION_SIZE_T2, config.POSITION_SIZE_T3),
        )
        if risk == 0:
            return 0.0
        direction = 1 if stop_loss < entry_price else -1
        previous = entry_price
        weighted_reward = 0.0
        for target, weight in zip(targets, weights):
            if target is not None:
                # Legacy POSITION plans can allocate two exits to the same price.
                # MITCH enforces distinct, spaced prices during target selection.
                if (
                    direction * (target - entry_price) <= 0
                    or direction * (target - previous) < 0
                ):
                    raise ValueError("Profit targets must be ordered on the profitable side of entry")
                weighted_reward += direction * (target - entry_price) * weight
                previous = target
        return weighted_reward / risk

    def _validate_temporal_proportionality(self, x_ts: pd.Timestamp, a_ts: pd.Timestamp, b_ts: pd.Timestamp, c_ts: pd.Timestamp, d_ts: pd.Timestamp) -> Tuple[bool, str]:
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
        if not self.config_helper.get_bool('ENABLE_TEMPORAL_VALIDATION', True):
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
        max_total_duration = self.config_helper.get_int('MAX_TOTAL_PATTERN_DURATION_DAYS', 1825)
        if total_time > max_total_duration:
            return False, f"Total pattern duration too long: {total_time} days ({total_time/365:.1f} years, max {max_total_duration/365:.1f} years)"

        # Check maximum individual leg duration (prevents 19-year XA legs!)
        max_leg_duration = self.config_helper.get_int('MAX_INDIVIDUAL_LEG_DURATION_DAYS', 1095)

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
        max_cd_xa = self.config_helper.get_float('MAX_CD_TO_XA_TIME_RATIO', 5.0)
        max_cd_ab = self.config_helper.get_float('MAX_CD_TO_AB_TIME_RATIO', 10.0)
        max_cd_bc = self.config_helper.get_float('MAX_CD_TO_BC_TIME_RATIO', 8.0)
        max_cd_xabc = self.config_helper.get_float('MAX_CD_TO_XABC_TIME_RATIO', 3.0)

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

    def _create_harmonic_pattern(
        self,
        points: Dict[str, Any],
        ratios: Dict[str, float],
        pattern_spec: PatternSpec,
        trading_specs: Dict[str, Any],
        grade: str,
        fib_tolerance: float
    ) -> HarmonicPattern:
        """
        Create HarmonicPattern object from all components.

        Args:
            points: Dictionary containing XABCD points and is_bullish flag
            ratios: Dictionary containing Fibonacci ratios
            pattern_spec: Pattern specification
            trading_specs: Dictionary containing trading specifications
            grade: Pattern grade (A+ to C-)
            fib_tolerance: Fibonacci tolerance used

        Returns:
            HarmonicPattern object
        """
        # For pyharmonics patterns, tolerance_level shows the fib_tolerance as percentage
        tolerance_level = f"{fib_tolerance*100:.1f}%"

        # Determine trade quality tier based on grade
        trade_quality = self._get_trade_quality(grade)

        # Create HarmonicPattern object
        return HarmonicPattern(
            x=points['x'],
            a=points['a'],
            b=points['b'],
            c=points['c'],
            d=points['d'],
            pattern_type=pattern_spec.name,
            is_bullish=points['is_bullish'],
            ab_xa_ratio=ratios['ab_xa'],
            bc_ab_ratio=ratios['bc_ab'],
            bc_projection=ratios['bc_projection'],
            cd_bc_ratio=ratios['cd_bc'],
            ad_xa_ratio=ratios['ad_xa'],
            entry_price=trading_specs['entry_price'],
            stop_loss=trading_specs['stop_loss'],
            ipo_target_1=trading_specs['ipo_target_1'],
            ipo_target_2=trading_specs['ipo_target_2'],
            target_point_a=trading_specs['target_point_a'],
            risk_reward=trading_specs['risk_reward'],
            prz_levels=trading_specs['prz_levels'],
            d_point_range_min=trading_specs['d_point_range_min'],
            d_point_range_max=trading_specs['d_point_range_max'],
            days_since_completion=0,
            tolerance_level=tolerance_level,
            grade=grade,
            trade_quality=trade_quality,
            tp_strategy_used=trading_specs['tp_strategy_used'],
            tp_strategy_name=trading_specs['tp_strategy_name'],
            tp_target_details=trading_specs['tp_target_details'],
            origin=points.get('origin'),
            # Multi-swing BC not detected from pyharmonics
            is_multi_swing_bc=False,
            bc_internal_swing_count=0,
            bc_volatility=0.0,
            bc_duration_bars=0
        )

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


    def _calculate_pyharmonics_grade(self, ab_xa: float, bc_ab: float,
                                     ad_xa: float, bc_projection: float,
                                     pattern_spec: PatternSpec, fib_tolerance: float,
                                     x_price: float, a_price: float, b_price: float,
                                     c_price: float, d_price: float,
                                     x_ts: pd.Timestamp, a_ts: pd.Timestamp, b_ts: pd.Timestamp, c_ts: pd.Timestamp, d_ts: pd.Timestamp) -> str:
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
            bc_ab: Actual BC/AB ratio
            ad_xa: Actual AD/XA ratio (D-point for standard XABCD patterns)
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

        bc_score = self._score_ratio_precision(
            actual=bc_projection,
            ideal_min=pattern_spec.bc_projection_min,
            ideal_max=pattern_spec.bc_projection_max
        )

        if pattern_spec.name == '5-0':
            c_score = self._score_ratio_precision(
                actual=bc_ab,
                ideal_min=pattern_spec.c_point_min,
                ideal_max=pattern_spec.c_point_max
            )
            ab = abs(b_price - a_price)
            reciprocal_ratio = abs(d_price - c_price) / ab if ab else 0
            reciprocal_score = self._score_ratio_precision(
                actual=reciprocal_ratio,
                ideal_min=1.0,
                ideal_max=1.0
            )
            # Completion is defined jointly by the 50% BC retracement and
            # reciprocal AB=CD; the setup ratios establish the structure.
            base_score = (
                (bc_score * 0.35)
                + (reciprocal_score * 0.35)
                + (b_score * 0.15)
                + (c_score * 0.15)
            )
        else:
            d_score = self._score_ratio_precision(
                actual=ad_xa,
                ideal_min=pattern_spec.d_point_min,
                ideal_max=pattern_spec.d_point_max
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
                                   bc_projection: float, pattern_spec: PatternSpec) -> float:
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

    def _calculate_time_symmetry(self, x_ts: pd.Timestamp, a_ts: pd.Timestamp, b_ts: pd.Timestamp, c_ts: pd.Timestamp, d_ts: pd.Timestamp) -> float:
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
                               reaction_data: Optional[Any] = None,
                               sector_etf_analysis: Optional[Any] = None) -> str:
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
        # Delegate to ChartGenerator
        return self.chart_generator.generate_pattern_chart(
            pattern=pattern,
            ticker=ticker,
            df=df,
            chart_dir=chart_dir,
            interval=interval,
            reaction_data=reaction_data,
            sector_etf_analysis=sector_etf_analysis
        )

    def generate_signal(self, pattern: HarmonicPattern, current_price: float,
                       max_days_old: Optional[int] = None, verbose: bool = False) -> Tuple[str, str]:
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
            max_days_old: Maximum age for the initial entry. If None, uses
                MAX_DAYS_TO_INITIAL_ENTRY from config.
            verbose: If True, generate detailed asset-specific explanation

        Returns:
            Tuple of (signal, explanation)
        """
        # Check pattern age - use config value if not specified
        if max_days_old is None:
            try:
                import config
                max_days_old = self.config_helper.get_int(
                    'MAX_DAYS_TO_INITIAL_ENTRY',
                    self.config_helper.get_int('MAX_DAYS_SINCE_PATTERN', 730),
                )
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
                min_rr = self.config_helper.get_float('MIN_LONG_RISK_REWARD_RATIO', 1.5)
                signal_type = "LONG"
            else:
                # SHORT (SELL) patterns - lower R/R due to limited downside
                min_rr = self.config_helper.get_float('MIN_SHORT_RISK_REWARD_RATIO', 1.5)
                signal_type = "SHORT"
        except ImportError:
            min_rr = 1.5
            signal_type = "LONG" if pattern.is_bullish else "SHORT"

        # Missing TP targets describe an incomplete exit plan; they do not
        # invalidate the harmonic pattern or prevent a signal.
        has_tp_targets = pattern.ipo_target_1 is not None
        if has_tp_targets and pattern.risk_reward < min_rr:
            return "HOLD", f"Risk/Reward too low for {signal_type} ({pattern.risk_reward:.2f}:1, minimum {min_rr}:1) - pattern detected on {pattern.d.date.date()}"

        # Check risk percentage from config
        try:
            import config
            max_risk_pct = self.config_helper.get_float('MAX_ALLOWED_STOP_LOSS_PCT', 10.0)
        except ImportError:
            max_risk_pct = 10.0

        risk_pct = abs((pattern.entry_price - pattern.stop_loss) / pattern.entry_price * 100)
        # Round to 1 decimal place to match display format and avoid floating-point precision issues
        # This ensures that a risk of 10.04% (displays as "10.0%") passes when max_risk_pct is 10.0%
        risk_pct_rounded = round(risk_pct, 1)
        if risk_pct_rounded > max_risk_pct:
            return "HOLD", f"Risk too high ({risk_pct:.1f}%, maximum {max_risk_pct:.1f}%) - pattern detected on {pattern.d.date.date()}"

        # PRZ tolerance: 5% matches live execution (wick or pay up to 5%).
        # Wider than Carney's tight PRZ; audit showed exact-D wick fills underperformed
        # opens still inside 5%. Extension patterns keep the same band.
        prz_tolerance = self.config_helper.get_float('PRZ_ENTRY_TOLERANCE_PCT', 5.0) / 100.0

        # Check if current price is still within PRZ
        in_prz = False
        if pattern.is_bullish:
            # Bullish: price should be at or below entry (at D or lower)
            in_prz = current_price <= pattern.entry_price * (1 + prz_tolerance)
        else:
            # Bearish: price should be at or above entry (at D or higher)
            in_prz = current_price >= pattern.entry_price * (1 - prz_tolerance)

        require_prz = self.config_helper.get_bool('REQUIRE_PRICE_IN_PRZ', True)
        if require_prz and not in_prz:
            return "HOLD", (
                f"{pattern.pattern_type} pattern detected on {pattern.d.date.date()} but price moved outside PRZ "
                f"(Current: ${current_price:.2f}, Entry: ${pattern.entry_price:.2f})"
            )

        # Check if stop loss hit
        # Get pattern spec for detailed stop loss information
        pattern_spec = get_pattern_spec(pattern.pattern_type.lower().replace(' ', '_'))

        if pattern.is_bullish:
            if current_price < pattern.stop_loss:
                if verbose and pattern_spec:
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
                        f"- Price ${current_price:.2f} < Stop ${pattern.stop_loss:.2f}"
                        + (f", {pattern_spec.stop_loss_ratio}x XA from ${pattern.x.price:.2f}" if pattern_spec else "")
                    )
        else:
            if current_price > pattern.stop_loss:
                if verbose and pattern_spec:
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
                        f"- Price ${current_price:.2f} > Stop ${pattern.stop_loss:.2f}"
                        + (f", {pattern_spec.stop_loss_ratio}x XA from ${pattern.x.price:.2f}" if pattern_spec else "")
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
            target_summary = (
                f"  T1: {format_target(pattern.ipo_target_1)} | "
                f"T2: {format_target(pattern.ipo_target_2)} | "
                f"T3: {format_target(pattern.target_point_a)}"
            )
            risk_reward_summary = (
                f"  Risk/Reward: {pattern.risk_reward:.2f}:1"
                if has_tp_targets
                else "  Risk/Reward: Undefined (TP targets not defined)"
            )
            explanation = (
                f"{direction} {pattern.pattern_type.upper()} - Grade {pattern.grade} - Detected {pattern.d.date.date()}\n"
                f"  Entry: ${pattern.entry_price:.2f} | Stop: ${pattern.stop_loss:.2f}\n"
                f"{target_summary}\n"
                f"{risk_reward_summary}\n"
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

        if pattern.pattern_type == '5-0':
            c_match = (
                "✓"
                if pattern_spec.c_point_min <= pattern.bc_ab_ratio <= pattern_spec.c_point_max
                else "✗"
            )
            lines.append(
                f"  {c_match} BC/AB Extension: {pattern.bc_ab_ratio:.3f} "
                f"(Range: {pattern_spec.c_point_min:.3f}-{pattern_spec.c_point_max:.3f})"
            )
            d_match = "✓" if abs(pattern.cd_bc_ratio - 0.50) <= 0.03 else "✗"
            lines.append(
                f"  {d_match} D Retracement of BC: {pattern.cd_bc_ratio:.3f} "
                "(Target: 0.500)"
            )
            ab = abs(pattern.b.price - pattern.a.price)
            reciprocal_ratio = abs(pattern.d.price - pattern.c.price) / ab if ab else 0
            reciprocal_match = "✓" if abs(reciprocal_ratio - 1.0) <= 0.03 else "✗"
            lines.append(
                f"  {reciprocal_match} Reciprocal AB=CD: {reciprocal_ratio:.3f} "
                "(Target: 1.000)"
            )
        else:
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

        lines.append(f"PROFIT TARGETS ({pattern.tp_strategy_used}):")
        t1_gain = (
            abs(pattern.ipo_target_1 - pattern.entry_price)
            if pattern.ipo_target_1 is not None else 0.0
        )
        t1_pct = (t1_gain / pattern.entry_price) * 100
        targets = (pattern.ipo_target_1, pattern.ipo_target_2, pattern.target_point_a)
        allocations = target_allocations(
            targets,
            (config.POSITION_SIZE_T1, config.POSITION_SIZE_T2, config.POSITION_SIZE_T3),
        )
        for i, (target, allocation) in enumerate(zip(targets, allocations), 1):
            lines.append(f"  Target {i}: {format_target(target)}")
            if target is not None:
                gain = abs(target - pattern.entry_price)
                lines.append(
                    f"    Potential Gain: ${gain:.2f} "
                    f"({gain / pattern.entry_price * 100:.2f}%); exit {allocation:.0%}"
                )
        lines.append("")

        # Risk/Reward
        lines.append("RISK/REWARD ANALYSIS:")
        lines.append(f"  Risk: ${stop_distance:.2f} ({(stop_distance/pattern.entry_price*100):.2f}%)")
        if pattern.ipo_target_1 is None:
            lines.append("  Reward: Undefined (TP targets not defined)")
            lines.append("  Risk/Reward Ratio: Undefined (TP targets not defined)")
        else:
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
            if pattern.ipo_target_1 is None:
                lines.append("  ⚠ TP targets are not defined")
            else:
                lines.append(f"  ✓ Risk/Reward ratio of {pattern.risk_reward:.2f}:1 meets minimum")
            lines.append(f"  ✓ All Fibonacci ratios validated per Carney's specifications")
            lines.append("")
            lines.append(f"  RECOMMENDATION: Consider buying at current price ${current_price:.2f}")
            lines.append(f"  Place stop loss at ${pattern.stop_loss:.2f}")
            lines.append(f"  Take profits at T1: {format_target(pattern.ipo_target_1)}")
        elif signal == "SELL":
            lines.append(f"  ✓ Bearish {pattern.pattern_type} pattern completed at ${pattern.entry_price:.2f}")
            lines.append(f"  ✓ Current price ${current_price:.2f} is within PRZ tolerance")
            if pattern.ipo_target_1 is None:
                lines.append("  ⚠ TP targets are not defined")
            else:
                lines.append(f"  ✓ Risk/Reward ratio of {pattern.risk_reward:.2f}:1 meets minimum")
            lines.append(f"  ✓ All Fibonacci ratios validated per Carney's specifications")
            lines.append("")
            lines.append(f"  RECOMMENDATION: Consider selling/shorting at current price ${current_price:.2f}")
            lines.append(f"  Place stop loss at ${pattern.stop_loss:.2f}")
            lines.append(f"  Take profits at T1: {format_target(pattern.ipo_target_1)}")

        lines.append(f"{'='*70}")

        return "\n".join(lines)


if __name__ == "__main__":
    # Test improved Carney-based detector
    from data_downloader import download_stock_data

    logger.info("="*80)
    logger.info("IMPROVED HARMONIC PATTERN DETECTOR TEST")
    logger.info("Pyharmonics Peak Detection + Carney's Exact Rules (Volumes 1-3)")
    logger.info("="*80)
    logger.info("")

    # Download test data
    df = download_stock_data("AAPL", period="6mo", interval="1d")
    df.columns = [c.lower() for c in df.columns]

    logger.info("Testing on AAPL - %d days of data", len(df))
    logger.info("")

    # Create detector with Carney's specifications
    detector = PatternDetector()

    # Detect patterns
    patterns = detector.detect_patterns(df, "AAPL")

    logger.info("Found %d harmonic patterns using Carney's exact specifications", len(patterns))
    logger.info("")

    # Display patterns
    for i, pattern in enumerate(patterns[:5], 1):  # Show first 5
        current_price = df['close'].iloc[-1]
        signal, explanation = detector.generate_signal(pattern, current_price)

        from utils import FormattingUtils

        logger.info("Pattern %d: %s (%s) [Grade %s]", i, pattern.pattern_type.upper(),
                   'BULLISH' if pattern.is_bullish else 'BEARISH', pattern.grade)
        logger.info("  Points: X=$%.2f -> A=$%.2f -> B=$%.2f -> C=$%.2f -> D=$%.2f",
                   pattern.x.price, pattern.a.price, pattern.b.price, pattern.c.price, pattern.d.price)
        logger.info("  Date Range: %s to %s", pattern.x.date.date(), pattern.d.date.date())
        logger.info("  Ratios: %s", FormattingUtils.format_pattern_ratios(pattern))
        logger.info("  Signal: %s", signal)
        logger.info("  %s", explanation)
        logger.info("")
