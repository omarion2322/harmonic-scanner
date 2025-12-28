"""
Take Profit Strategies Module

This module contains different take profit strategies for harmonic patterns:
- SCOTT: Scott Carney's Fibonacci-based approach (38.2%, 61.8%, 100%)
- MITCH: Mitch Ray's external market structure approach
- POSITION: Long-term strategy combining both approaches for x2-x5 gains
"""

from tp_strategies.base import TPStrategy, TPTargets
from tp_strategies.scott import ScottStrategy
from tp_strategies.mitch import MitchStrategy
from tp_strategies.position import PositionStrategy

__all__ = [
    'TPStrategy',
    'TPTargets',
    'ScottStrategy',
    'MitchStrategy',
    'PositionStrategy',
]
