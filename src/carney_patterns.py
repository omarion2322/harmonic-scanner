"""
Scott Carney Harmonic Pattern Specifications
Exact ratio requirements from Harmonic Trading Volumes 1, 2, and 3
"""

from typing import Dict, List, Optional, Tuple
from pydantic import BaseModel, Field, field_validator


class PatternSpec(BaseModel):
    """Specification for a harmonic pattern with validation."""
    name: str = Field(..., min_length=1, description="Pattern name")
    b_point_min: float = Field(..., ge=0.0, le=2.0, description="Minimum B point ratio")
    b_point_max: float = Field(..., ge=0.0, le=2.0, description="Maximum B point ratio")
    b_tolerance: float = Field(0.0, ge=0.0, le=0.2, description="B point tolerance")
    bc_projection_min: float = Field(..., ge=0.0, le=5.0, description="Minimum BC projection")
    bc_projection_max: float = Field(..., ge=0.0, le=5.0, description="Maximum BC projection")
    d_point_min: float = Field(..., ge=0.0, le=5.0, description="Minimum D point XA ratio")
    d_point_max: float = Field(..., ge=0.0, le=5.0, description="Maximum D point XA ratio")
    c_point_min: float = Field(..., ge=0.0, le=2.0, description="Minimum C point AB retracement")
    c_point_max: float = Field(..., ge=0.0, le=2.0, description="Maximum C point AB retracement")
    stop_loss_ratio: float = Field(..., ge=1.0, le=3.0, description="Stop loss ratio")
    is_extension: bool = Field(..., description="True if extends beyond X, False if retracement")

    @field_validator('b_point_max')
    @classmethod
    def validate_b_point_max(cls, v: float, info) -> float:
        """Ensure b_point_max >= b_point_min."""
        if 'b_point_min' in info.data and v < info.data['b_point_min']:
            raise ValueError(f'b_point_max ({v}) must be >= b_point_min ({info.data["b_point_min"]})')
        return v

    @field_validator('bc_projection_max')
    @classmethod
    def validate_bc_projection_max(cls, v: float, info) -> float:
        """Ensure bc_projection_max >= bc_projection_min."""
        if 'bc_projection_min' in info.data and v < info.data['bc_projection_min']:
            raise ValueError(f'bc_projection_max ({v}) must be >= bc_projection_min ({info.data["bc_projection_min"]})')
        return v

    @field_validator('d_point_max')
    @classmethod
    def validate_d_point_max(cls, v: float, info) -> float:
        """Ensure d_point_max >= d_point_min."""
        if 'd_point_min' in info.data and v < info.data['d_point_min']:
            raise ValueError(f'd_point_max ({v}) must be >= d_point_min ({info.data["d_point_min"]})')
        return v

    @field_validator('c_point_max')
    @classmethod
    def validate_c_point_max(cls, v: float, info) -> float:
        """Ensure c_point_max >= c_point_min."""
        if 'c_point_min' in info.data and v < info.data['c_point_min']:
            raise ValueError(f'c_point_max ({v}) must be >= c_point_min ({info.data["c_point_min"]})')
        return v

    class Config:
        frozen = True  # Make immutable like dataclass with frozen=True
        str_strip_whitespace = True


# Carney's Exact Pattern Specifications from Volumes 1-3
CARNEY_PATTERNS = {
    'gartley': PatternSpec(
        name='Gartley',
        b_point_min=0.55,   # Scott Carney's Real-Market Range: 0.55-0.68
        b_point_max=0.68,   # (Ideal: 0.618, Supported: 0.618 ± 0.05)
        b_tolerance=0.0,  # Tolerance handled by ToleranceLevel
        bc_projection_min=1.272,  # CD = 1.272-1.618 AB
        bc_projection_max=1.618,  # CRITICAL: >1.618 = BAT
        d_point_min=0.786,  # D = 0.786 XA (exact)
        d_point_max=0.786,
        c_point_min=0.382,  # BC = 0.382-0.886 AB
        c_point_max=0.886,
        stop_loss_ratio=1.0,
        is_extension=False
    ),

    'bat': PatternSpec(
        name='Bat',
        b_point_min=0.35,   # Scott Carney's Real-Market Range: 0.35-0.53
        b_point_max=0.53,   # (Official: 0.382-0.500)
        b_tolerance=0.0,  # Tolerance handled by ToleranceLevel
        bc_projection_min=1.618,  # CD = 1.618-2.618 BC
        bc_projection_max=2.618,
        d_point_min=0.886,  # D = 0.886 XA (MOST IMPORTANT number)
        d_point_max=0.886,
        c_point_min=0.382,  # BC = 0.382-0.886 AB
        c_point_max=0.886,
        stop_loss_ratio=1.13,
        is_extension=False
    ),

    'alternate_bat': PatternSpec(
        name='Alternate Bat',
        b_point_min=0.382,  # AB = ≤0.382 XA (can be less with tolerance)
        b_point_max=0.382,
        b_tolerance=0.0,  # Tolerance handled by ToleranceLevel
        bc_projection_min=2.0,  # CD = 2.0-3.618 BC
        bc_projection_max=3.618,
        d_point_min=0.886,  # D = 0.886-1.13 XA (extension beyond X)
        d_point_max=1.13,
        c_point_min=0.382,  # BC = 0.382-0.886 AB
        c_point_max=0.886,
        stop_loss_ratio=1.27,
        is_extension=True
    ),

    'butterfly': PatternSpec(
        name='Butterfly',
        b_point_min=0.75,   # Scott Carney's Real-Market Range: 0.75-0.82
        b_point_max=0.82,   # (Ideal: 0.786, Supported: 0.786 ± 0.03)
        b_tolerance=0.0,  # Tolerance handled by ToleranceLevel
        bc_projection_min=1.618,  # Optional: CD = 2.0-3.618 BC (using lower range)
        bc_projection_max=2.24,
        d_point_min=1.272,  # CD = 1.272-1.618 XA (extension)
        d_point_max=1.618,
        c_point_min=0.382,  # BC = 0.382-0.886 AB
        c_point_max=0.886,
        stop_loss_ratio=1.414,
        is_extension=True
    ),

    'crab': PatternSpec(
        name='Crab',
        b_point_min=0.35,   # Scott Carney's Real-Market Range: 0.35-0.65
        b_point_max=0.65,   # (Official: 0.382-0.618)
        b_tolerance=0.0,  # Tolerance handled by ToleranceLevel
        bc_projection_min=2.618,  # CD = 2.618-3.618 BC extension
        bc_projection_max=3.618,
        d_point_min=1.618,  # CD = 1.618 XA (exact extension)
        d_point_max=1.618,
        c_point_min=0.382,  # BC = 0.382-0.886 AB
        c_point_max=0.886,
        stop_loss_ratio=2.0,
        is_extension=True
    ),

    'deep_crab': PatternSpec(
        name='Deep Crab',
        b_point_min=0.86,   # Scott Carney's Real-Market Range: 0.86-0.90
        b_point_max=0.90,   # (Ideal: 0.886, Supported: 0.886 ± 0.02)
        b_tolerance=0.0,  # Tolerance handled by ToleranceLevel
        bc_projection_min=2.0,  # CD = 2.0-3.618 BC (optional check)
        bc_projection_max=3.618,
        d_point_min=2.24,  # CD = 2.24-3.618 XA (extension)
        d_point_max=3.618,
        c_point_min=0.382,  # BC = 0.382-0.886 AB
        c_point_max=0.886,
        stop_loss_ratio=2.0,
        is_extension=True
    ),

    'cypher': PatternSpec(
        name='Cypher',
        b_point_min=0.35,   # Scott Carney's Real-Market Range: 0.35-0.53
        b_point_max=0.53,   # (Official: 0.382-0.500)
        b_tolerance=0.0,  # Tolerance handled by ToleranceLevel
        bc_projection_min=1.272,  # BC = 1.272-1.414 XA (C extends beyond A)
        bc_projection_max=1.414,
        d_point_min=0.786,  # D = 0.786 XC (measured from XC, not XA)
        d_point_max=0.786,
        c_point_min=1.272,  # C point extends 1.272-1.414 of XA (special case)
        c_point_max=1.414,
        stop_loss_ratio=1.414,
        is_extension=True  # C extends beyond A
    ),

    'shark': PatternSpec(
        name='Shark',
        b_point_min=0.85,   # Scott Carney's Real-Market Range: 0.85-0.90 (for 0.886 target)
        b_point_max=0.90,   # Alternative range: 1.10-1.16 (for 1.13 target)
        b_tolerance=0.0,  # Tolerance handled by ToleranceLevel
        bc_projection_min=1.618,  # BC = 1.618-2.24 AB
        bc_projection_max=2.24,
        d_point_min=0.886,  # D = 0.886 OX or 1.13 AB (using 0.886 as primary)
        d_point_max=1.13,  # Alternative: 1.13 AB
        c_point_min=1.13,  # C retraces from extended B
        c_point_max=1.618,
        stop_loss_ratio=1.27,
        is_extension=False  # Using 0.886 retracement, not extension
    ),

    '5_0': PatternSpec(
        name='5-0',
        b_point_min=1.13,  # B = 1.13-1.618 of A-X
        b_point_max=1.618,
        b_tolerance=0.0,  # Tolerance handled by ToleranceLevel
        bc_projection_min=1.618,  # D = 1.618 BC extension
        bc_projection_max=1.618,
        d_point_min=0.50,  # C = 0.5 AB retracement
        d_point_max=0.50,
        c_point_min=0.50,  # C = 0.5 AB retracement (exact)
        c_point_max=0.50,
        stop_loss_ratio=1.13,
        is_extension=True  # B extends beyond X
    )
}


def get_pattern_spec(pattern_name: str) -> Optional[PatternSpec]:
    """
    Get pattern specification by name.

    Args:
        pattern_name: Pattern name (case insensitive)

    Returns:
        PatternSpec or None if not found
    """
    return CARNEY_PATTERNS.get(pattern_name.lower().replace(' ', '_'))


def differentiate_gartley_vs_bat(b_ratio: float, bc_projection: float) -> str:
    """
    Differentiate between Gartley and Bat using Carney's "Great Gartley Controversy" rule.

    Critical Rule: BC projection > 1.618 = BAT, NOT Gartley

    Args:
        b_ratio: B point as XA retracement
        bc_projection: BC projection ratio

    Returns:
        'gartley', 'bat', or 'neither'
    """
    # BC > 1.618 means it's definitively a BAT
    if bc_projection > 1.618:
        # Must have B < 0.618 for Bat
        if b_ratio < 0.618 + 0.05:  # 5% tolerance
            return 'bat'
        else:
            return 'neither'

    # BC <= 1.618 could be Gartley
    if 0.618 - 0.03 <= b_ratio <= 0.618 + 0.03:  # 3% tolerance for Gartley
        return 'gartley'

    return 'neither'


def differentiate_butterfly_vs_crab(b_ratio: float, d_xa_ratio: float) -> str:
    """
    Differentiate between Butterfly and Crab.

    Critical Rules:
    - Butterfly: B = 0.786 (±3%), D = 1.27 XA, NO 1.618 XA
    - Crab: B = 0.382-0.618, D = 1.618 XA

    Args:
        b_ratio: B point as XA retracement
        d_xa_ratio: D point as XA ratio (extension)

    Returns:
        'butterfly', 'crab', or 'neither'
    """
    # Check for Butterfly: B must be 0.786 ±3%
    if 0.786 - 0.03 <= b_ratio <= 0.786 + 0.03:
        # D should be around 1.27, NOT 1.618
        if 1.20 <= d_xa_ratio <= 1.35:
            return 'butterfly'
        # If B is 0.786 but extends to 1.618, likely became a Crab
        elif 1.55 <= d_xa_ratio <= 1.95:
            return 'crab'

    # Check for Crab: B = 0.382-0.618, D = 1.618
    if 0.382 <= b_ratio <= 0.618:
        if 1.55 <= d_xa_ratio <= 1.95:  # 1.618 with tolerance
            return 'crab'

    return 'neither'


def calculate_ipo_target(pattern_high: float, pattern_low: float,
                        is_bullish: bool, blown_out_382: bool = False) -> Tuple[float, float]:
    """
    Calculate Initial Profit Objective (I.P.O.) using Carney's method.

    I.P.O. is 0.382 or 0.618 retracement from pattern extremes (high-low range),
    NOT from AD leg!

    Args:
        pattern_high: Highest price in completed pattern
        pattern_low: Lowest price in completed pattern
        is_bullish: True for bullish pattern
        blown_out_382: If True, use 0.618 instead of 0.382

    Returns:
        Tuple of (primary_target, secondary_target)
    """
    pattern_range = pattern_high - pattern_low

    if is_bullish:
        # Bullish: measure retracements from pattern low
        if blown_out_382:
            primary = pattern_low + (pattern_range * 0.618)
            secondary = pattern_high  # Point A or pattern high
        else:
            primary = pattern_low + (pattern_range * 0.382)
            secondary = pattern_low + (pattern_range * 0.618)
    else:
        # Bearish: measure retracements from pattern high
        if blown_out_382:
            primary = pattern_high - (pattern_range * 0.618)
            secondary = pattern_low  # Point A or pattern low
        else:
            primary = pattern_high - (pattern_range * 0.382)
            secondary = pattern_high - (pattern_range * 0.618)

    return primary, secondary


def calculate_382_trailer(reversal_point: float, current_extreme: float, is_bullish: bool) -> float:
    """
    Calculate 0.382 trailing stop after I.P.O. achieved.

    Strongest reversals only retrace to 0.382 before continuing.
    This is the "make-or-break" level of the reversal.

    Args:
        reversal_point: Price where reversal started (point D)
        current_extreme: Current extreme price since reversal
        is_bullish: True for bullish reversal

    Returns:
        Trailing stop level
    """
    reversal_range = abs(current_extreme - reversal_point)

    if is_bullish:
        trailer = current_extreme - (reversal_range * 0.382)
    else:
        trailer = current_extreme + (reversal_range * 0.382)

    return trailer


def calculate_stop_loss(pattern_spec: PatternSpec, x_price: float,
                       xa_range: float, is_bullish: bool) -> float:
    """
    Calculate stop loss using Carney's pattern-specific ratios.

    Args:
        pattern_spec: Pattern specification
        x_price: Point X price
        xa_range: Absolute XA price range
        is_bullish: True for bullish pattern

    Returns:
        Stop loss price
    """
    if is_bullish:
        # Bullish: stop below X point
        stop_loss = x_price - (xa_range * (pattern_spec.stop_loss_ratio - 1.0))
    else:
        # Bearish: stop above X point
        stop_loss = x_price + (xa_range * (pattern_spec.stop_loss_ratio - 1.0))

    return stop_loss


def calculate_prz_levels(x: float, a: float, b: float, c: float,
                        pattern_spec: PatternSpec) -> Dict[str, float]:
    """
    Calculate Potential Reversal Zone (PRZ) levels for pattern.

    PRZ = convergence of 3+ Fibonacci calculations at defined price level.

    Args:
        x, a, b, c: Price points
        pattern_spec: Pattern specification

    Returns:
        Dictionary of PRZ levels
    """
    xa_range = abs(a - x)
    ab_range = abs(b - a)
    bc_range = abs(c - b)

    is_bullish = a > x

    prz = {}

    # XA retracement/extension for D point
    if is_bullish:
        if pattern_spec.is_extension:
            prz['xa_min'] = x - (xa_range * pattern_spec.d_point_min)
            prz['xa_max'] = x - (xa_range * pattern_spec.d_point_max)
        else:
            prz['xa_min'] = a - (xa_range * pattern_spec.d_point_min)
            prz['xa_max'] = a - (xa_range * pattern_spec.d_point_max)
    else:
        if pattern_spec.is_extension:
            prz['xa_min'] = x + (xa_range * pattern_spec.d_point_min)
            prz['xa_max'] = x + (xa_range * pattern_spec.d_point_max)
        else:
            prz['xa_min'] = a + (xa_range * pattern_spec.d_point_min)
            prz['xa_max'] = a + (xa_range * pattern_spec.d_point_max)

    # BC projection for D point
    if is_bullish:
        prz['bc_min'] = c - (bc_range * pattern_spec.bc_projection_min)
        prz['bc_max'] = c - (bc_range * pattern_spec.bc_projection_max)
    else:
        prz['bc_min'] = c + (bc_range * pattern_spec.bc_projection_min)
        prz['bc_max'] = c + (bc_range * pattern_spec.bc_projection_max)

    return prz
