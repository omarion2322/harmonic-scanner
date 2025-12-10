"""
Tolerance Levels for Harmonic Pattern Detection
Based on Scott Carney's Harmonic Trading Framework - CORRECTED

Carney's Key Principles:
1. B-point defines the pattern type (must be precise ±3%)
2. BC projection checked against specific Fib ratios (±0.10 standard)
3. D-point creates a PRZ "zone" not a line (±5% acceptable)
4. Pattern differentiation is critical (Gartley vs Bat, Butterfly vs Crab)
"""

from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass
class ToleranceLevel:
    """Defines tolerances for pattern detection"""
    name: str
    b_point_tolerance: float        # Tight tolerance required (Pattern Definition)
    bc_projection_tolerance: float  # Applied to the specific Fib ratio (e.g., ±0.10)
    d_point_tolerance: float        # PRZ Calculation tolerance
    micro_swing_mode: bool          # Enable 2-bar minimum swing detection
    description: str


# Define the three tolerance levels
# HYBRID SYSTEM: Pattern specs use Scott Carney's real-market ranges as BASE
# Tolerance levels are MODIFIERS applied on top of those ranges
TOLERANCE_LEVELS = {
    'Textbook': ToleranceLevel(
        name='Textbook',
        # Textbook: Tight tolerances matching Carney's textbook specifications (±3-5%)
        b_point_tolerance=0.04,  # ±4% (within textbook ±3-5% range)
        bc_projection_tolerance=0.04,  # ±4% for BC projection
        d_point_tolerance=0.03,  # ±3% PRZ width (within textbook 2-4% range)
        micro_swing_mode=False,  # Disabled for textbook mode (use standard Pyharmonics detection)
        description="Textbook - Tight tolerances matching Carney's specifications (B:±4%, PRZ:±3%)"
    ),

    'Standard': ToleranceLevel(
        name='Standard',
        # Standard: Safe real-market tolerances for reliable trading (±5-8%)
        b_point_tolerance=0.06,  # ±6% (within safe real-market ±5-8% range)
        bc_projection_tolerance=0.06,  # ±6% for BC projection
        d_point_tolerance=0.055,  # ±5.5% PRZ width (within safe 5-6% range)
        micro_swing_mode=True,  # Enabled for standard mode (2-bar minimum swing detection)
        description="Standard - Safe real-market tolerances for trading (B:±6%, PRZ:±5.5%)"
    ),

    'Relaxed': ToleranceLevel(
        name='Relaxed',
        # Relaxed: Wider tolerances for scanning while staying under hard limits
        b_point_tolerance=0.08,  # ±8% (at safe upper limit, under 10% hard limit)
        bc_projection_tolerance=0.08,  # ±8% for BC projection
        d_point_tolerance=0.065,  # ±6.5% PRZ width (under 7% hard limit)
        micro_swing_mode=True,  # Enabled for relaxed mode (2-bar minimum swing detection)
        description="Relaxed - Scanner-friendly tolerances under hard limits (B:±8%, PRZ:±6.5%)"
    )
}


# Updated Minimum BC Projections based on Carney's specific pattern rules
# Note: These are the ranges of acceptable BC projections
# Format: (minimum, maximum)
BC_PROJECTION_RANGES = {
    'gartley': (1.272, 1.618),      # CD = 1.272-1.618 AB
    'bat': (1.618, 2.618),          # CD = 1.618-2.618 BC
    'alternate_bat': (2.0, 3.618),  # CD = 2.0-3.618 BC
    'butterfly': (1.618, 2.24),     # Optional: CD = 2.0-3.618 BC (using lower range)
    'crab': (2.618, 3.618),         # CD = 2.618-3.618 BC extension
    'deep_crab': (2.0, 3.618),      # CD = 2.0-3.618 BC
    'cypher': (1.272, 1.414),       # BC = 1.272-1.414 XA (C extends beyond A)
    'shark': (1.618, 2.24),         # BC = 1.618-2.24 AB
    '5_0': (1.618, 1.618)           # D = 1.618 BC extension (exact)
}


# Common BC projection Fibonacci levels to check against
# The actual BC projection should be close to ONE of these specific ratios
COMMON_BC_PROJECTIONS = [1.13, 1.27, 1.618, 2.0, 2.24, 2.618, 3.14, 3.618]


def get_tolerance_level(level_name: str) -> ToleranceLevel:
    """Get tolerance level by name"""
    mapping = {
        'STRICT': 'Textbook',
        'MODERATE': 'Standard',
        'RELAXED': 'Relaxed',
        'TEXTBOOK': 'Textbook',
        'STANDARD': 'Standard'
    }
    level_key = mapping.get(level_name.upper(), level_name)
    return TOLERANCE_LEVELS.get(level_key, TOLERANCE_LEVELS['Standard'])


def get_all_tolerance_levels() -> Dict[str, ToleranceLevel]:
    """Get all defined tolerance levels"""
    return TOLERANCE_LEVELS


def validate_bc_projection(pattern_name: str, actual_bc: float, tolerance: ToleranceLevel) -> bool:
    """
    Validate BC projection using Carney's framework.

    Checks if the actual BC projection:
    1. Falls within the pattern's acceptable range
    2. Is close to a common Fibonacci ratio (within tolerance)

    Args:
        pattern_name: Pattern type ('gartley', 'bat', etc.)
        actual_bc: Actual BC projection ratio
        tolerance: ToleranceLevel object with bc_projection_tolerance

    Returns:
        True if BC projection is valid
    """
    # Get acceptable range for this pattern
    bc_range = BC_PROJECTION_RANGES.get(pattern_name)
    if not bc_range:
        return False

    bc_min, bc_max = bc_range
    bc_tolerance = tolerance.bc_projection_tolerance

    # Apply tolerance to range boundaries for sensitivity
    # This allows patterns slightly outside the strict range to be considered
    bc_min_adjusted = bc_min - bc_tolerance
    bc_max_adjusted = bc_max + bc_tolerance

    # Check if within adjusted pattern range
    if not (bc_min_adjusted <= actual_bc <= bc_max_adjusted):
        return False

    # Check if close to any common Fibonacci ratio

    for fib_ratio in COMMON_BC_PROJECTIONS:
        # Only check Fib ratios that are within this pattern's range
        if bc_min <= fib_ratio <= bc_max:
            # Check if actual BC is within tolerance of this Fib ratio
            if abs(actual_bc - fib_ratio) <= bc_tolerance:
                return True

    # FIXED: If no common ratio matched but it's in range, accept it with Standard or Relaxed tolerance
    # This handles cases where BC is between common ratios (e.g., 1.45 for Gartley is between 1.27 and 1.618)
    # Only Textbook tolerance requires exact match to specific Fibonacci ratios
    if tolerance.name in ['Standard', 'Relaxed']:
        return True

    return False
