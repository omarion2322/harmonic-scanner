"""
Type 1 (Reaction) and Type 2 (Reversal) Detection
Based on Scott Carney's Harmonic Trading Volumes 1-3

Type 1: Immediate reaction from PRZ (Terminal Bar + 1-3 bars)
Type 2: Secondary retest of PRZ after Type 1 reaction fails
"""

import pandas as pd
import numpy as np
from typing import Optional, Tuple, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, field_validator


class ReactionData(BaseModel):
    """
    Stores data about Type 1 or Type 2 reactions after pattern completion with validation.
    """
    reaction_type: str = Field(..., pattern='^(TYPE_1|TYPE_2|TYPE_1_FAILED|NONE|PENDING)$',
                                description="Reaction type classification")
    terminal_bar_idx: int = Field(..., ge=0, description="Index of Terminal Price Bar")
    terminal_bar_date: datetime = Field(..., description="Date of terminal bar")
    terminal_bar_price: float = Field(..., gt=0, description="Price at terminal bar")

    # Type 1 specific
    type1_detected: bool = Field(False, description="Whether Type 1 reaction detected")
    type1_reversal_bar_idx: Optional[int] = Field(None, ge=0, description="Type 1 reversal bar index")
    type1_reversal_date: Optional[datetime] = Field(None, description="Type 1 reversal date")
    type1_max_move: Optional[float] = Field(None, gt=0, description="Max price during Type 1")
    type1_reached_382: bool = Field(False, description="Reached 38.2% target")
    type1_reached_618: bool = Field(False, description="Reached 61.8% target")
    type1_trendline_broken: bool = Field(False, description="Trendline broken after reaction")

    # Type 2 specific
    type2_detected: bool = Field(False, description="Whether Type 2 reaction detected")
    type2_retest_bar_idx: Optional[int] = Field(None, ge=0, description="Type 2 retest bar index")
    type2_retest_date: Optional[datetime] = Field(None, description="Type 2 retest date")
    type2_terminal_bar_idx: Optional[int] = Field(None, ge=0, description="Type 2 terminal bar index")
    type2_terminal_bar_date: Optional[datetime] = Field(None, description="Type 2 terminal bar date")
    type2_terminal_bar_price: Optional[float] = Field(None, gt=0, description="Type 2 terminal bar price")

    # Profit target levels
    target_382: Optional[float] = Field(None, gt=0, description="38.2% profit target")
    target_618: Optional[float] = Field(None, gt=0, description="61.8% profit target")

    # Status
    bars_since_completion: int = Field(0, ge=0, description="Bars since pattern completion")
    reaction_summary: str = Field("", description="Human-readable reaction summary")

    @field_validator('terminal_bar_date', 'type1_reversal_date', 'type2_retest_date', 'type2_terminal_bar_date', mode='before')
    @classmethod
    def convert_timestamp_to_datetime(cls, v):
        """Convert pandas Timestamp to datetime."""
        if v is None:
            return v
        if isinstance(v, pd.Timestamp):
            return v.to_pydatetime()
        return v

    class Config:
        arbitrary_types_allowed = True  # Allow pandas Timestamp
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            pd.Timestamp: lambda v: v.isoformat()
        }


class ReactionDetector:
    """
    Detects Type 1 (Reaction) and Type 2 (Reversal) scenarios
    after harmonic pattern completion at point D
    """

    def __init__(self) -> None:
        self.max_type1_bars = 10  # Monitor up to 10 bars for Type 1
        self.max_type2_bars = 30  # Monitor up to 30 bars total for Type 2

    def detect_reaction(self, df: pd.DataFrame, pattern: Any, current_idx: int) -> ReactionData:
        """
        Detect if Type 1 or Type 2 reaction occurred after pattern completion.

        Args:
            df: Price dataframe with OHLC data
            pattern: HarmonicPattern object
            current_idx: Current bar index (latest bar in df)

        Returns:
            ReactionData object with analysis results
        """
        # Terminal Bar is at point D - use date to find actual df index
        terminal_bar_date = pattern.d.date
        terminal_bar_price = pattern.d.price

        # Find the actual index in the dataframe using the date
        try:
            terminal_bar_idx = df.index.get_loc(terminal_bar_date)
        except KeyError:
            # If exact date not found, find closest
            terminal_bar_idx = df.index.searchsorted(terminal_bar_date)
            if terminal_bar_idx >= len(df):
                terminal_bar_idx = len(df) - 1

        # Calculate profit targets (38.2% and 61.8% of pattern range)
        # Type 1 uses retracement of full pattern range for better profit targets
        pattern_high = max(pattern.x.price, pattern.a.price, pattern.b.price,
                          pattern.c.price, pattern.d.price)
        pattern_low = min(pattern.x.price, pattern.a.price, pattern.b.price,
                         pattern.c.price, pattern.d.price)
        pattern_range = pattern_high - pattern_low

        if pattern.is_bullish:
            target_382 = terminal_bar_price + (pattern_range * 0.382)
            target_618 = terminal_bar_price + (pattern_range * 0.618)
        else:
            target_382 = terminal_bar_price - (pattern_range * 0.382)
            target_618 = terminal_bar_price - (pattern_range * 0.618)

        # Check how many bars have passed since pattern completion
        bars_since_completion = current_idx - terminal_bar_idx

        # Not enough data yet
        if bars_since_completion < 1:
            return ReactionData(
                reaction_type='PENDING',
                terminal_bar_idx=terminal_bar_idx,
                terminal_bar_date=terminal_bar_date,
                terminal_bar_price=terminal_bar_price,
                type1_detected=False,
                target_382=target_382,
                target_618=target_618,
                bars_since_completion=bars_since_completion,
                reaction_summary="Pattern just completed - monitoring for reaction"
            )

        # Detect Type 1 Reaction
        type1_data = self._detect_type1(df, pattern, terminal_bar_idx,
                                       current_idx, target_382, target_618)

        # Check for Type 2 independently (doesn't require Type 1 first)
        type2_data = self._detect_type2(df, pattern, terminal_bar_idx,
                                      current_idx, type1_data)

        # Build ReactionData
        reaction = ReactionData(
            reaction_type=self._determine_reaction_type(type1_data, type2_data),
            terminal_bar_idx=terminal_bar_idx,
            terminal_bar_date=terminal_bar_date,
            terminal_bar_price=terminal_bar_price,
            type1_detected=type1_data['detected'],
            type1_reversal_bar_idx=type1_data.get('reversal_bar_idx'),
            type1_reversal_date=type1_data.get('reversal_date'),
            type1_max_move=type1_data.get('max_move'),
            type1_reached_382=type1_data.get('reached_382', False),
            type1_reached_618=type1_data.get('reached_618', False),
            type1_trendline_broken=type1_data.get('trendline_broken', False),
            target_382=target_382,
            target_618=target_618,
            bars_since_completion=bars_since_completion
        )

        # Add Type 2 data if detected
        if type2_data and type2_data['detected']:
            reaction.type2_detected = True
            reaction.type2_retest_bar_idx = type2_data.get('retest_bar_idx')
            reaction.type2_retest_date = type2_data.get('retest_date')
            reaction.type2_terminal_bar_idx = type2_data.get('terminal_bar_idx')
            reaction.type2_terminal_bar_date = type2_data.get('terminal_bar_date')
            reaction.type2_terminal_bar_price = type2_data.get('terminal_bar_price')

        # Generate summary
        reaction.reaction_summary = self._generate_summary(reaction, pattern)

        return reaction

    def _detect_type1(self, df: pd.DataFrame, pattern: Any, terminal_bar_idx: int,
                     current_idx: int, target_382: float, target_618: float) -> Dict[str, Any]:
        """
        Detect Type 1 reaction (immediate counter-trend move within 1-3 bars).
        """
        result = {
            'detected': False,
            'reversal_bar_idx': None,
            'reversal_date': None,
            'max_move': None,
            'reached_382': False,
            'reached_618': False,
            'trendline_broken': False
        }

        # Look at bars T+1 to T+3 (or up to current_idx if less than 3 bars)
        max_check = min(terminal_bar_idx + 3, current_idx)

        # Get data window from Terminal Bar to current
        end_idx = min(terminal_bar_idx + self.max_type1_bars, current_idx + 1)
        df_window = df.iloc[terminal_bar_idx:end_idx]

        if len(df_window) < 2:
            return result

        terminal_price = pattern.d.price

        # Check for counter-trend movement
        if pattern.is_bullish:
            # Bullish pattern: expect price to move UP
            max_high = df_window['high'].max()
            max_high_idx = df_window['high'].idxmax()

            # Type 1 detected if price moved above terminal price within observation window
            if max_high > terminal_price:
                result['detected'] = True
                result['reversal_bar_idx'] = df.index.get_loc(max_high_idx)
                result['reversal_date'] = max_high_idx
                result['max_move'] = max_high

                # Check if profit targets reached
                if max_high >= target_382:
                    result['reached_382'] = True
                if max_high >= target_618:
                    result['reached_618'] = True

                # Check if trendline broken (price went back below terminal price)
                if result['reached_382'] or result['reached_618']:
                    # After reaching targets, check if price fell back
                    after_peak = df_window.loc[max_high_idx:]['close']
                    if len(after_peak) > 1 and after_peak.iloc[-1] < terminal_price * 0.98:
                        result['trendline_broken'] = True
        else:
            # Bearish pattern: expect price to move DOWN
            min_low = df_window['low'].min()
            min_low_idx = df_window['low'].idxmin()

            # Type 1 detected if price moved below terminal price
            if min_low < terminal_price:
                result['detected'] = True
                result['reversal_bar_idx'] = df.index.get_loc(min_low_idx)
                result['reversal_date'] = min_low_idx
                result['max_move'] = min_low

                # Check if profit targets reached
                if min_low <= target_382:
                    result['reached_382'] = True
                if min_low <= target_618:
                    result['reached_618'] = True

                # Check if trendline broken
                if result['reached_382'] or result['reached_618']:
                    after_peak = df_window.loc[min_low_idx:]['close']
                    if len(after_peak) > 1 and after_peak.iloc[-1] > terminal_price * 1.02:
                        result['trendline_broken'] = True

        return result

    def _detect_type2(self, df: pd.DataFrame, pattern: Any, terminal_bar_idx: int,
                     current_idx: int, type1_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Detect Type 2 reversal based on:
        1. Breaking key structural level (B)
        2. Reaction exceeds 88.6% of CD
        3. OR creates market structure shift
        """
        result = {
            'detected': False,
            'retest_bar_idx': None,
            'retest_date': None,
            'terminal_bar_idx': None,
            'terminal_bar_date': None,
            'terminal_bar_price': None,
            'b_level_broken': False,
            'cd_886_exceeded': False
        }

        # Need sufficient bars to detect Type 2
        if current_idx - terminal_bar_idx < 5:
            return result

        # Get data after D point
        end_idx = min(terminal_bar_idx + self.max_type2_bars, current_idx + 1)
        df_window = df.iloc[terminal_bar_idx:end_idx]

        if len(df_window) < 2:
            return result

        # Calculate 88.6% of CD move
        cd_range = abs(pattern.d.price - pattern.c.price)
        b_price = pattern.b.price
        d_price = pattern.d.price

        if pattern.is_bullish:
            # For bullish: Type 2 requires breaking above B and/or 88.6% CD retracement
            target_886 = d_price + (cd_range * 0.886)

            # Check if price broke above B level
            max_high = df_window['high'].max()
            if max_high >= b_price:
                result['b_level_broken'] = True

            # Check if price exceeded 88.6% of CD
            if max_high >= target_886:
                result['cd_886_exceeded'] = True

            # Type 2 detected if either condition met
            if result['b_level_broken'] or result['cd_886_exceeded']:
                result['detected'] = True
                max_high_idx = df_window['high'].idxmax()
                result['terminal_bar_idx'] = df.index.get_loc(max_high_idx)
                result['terminal_bar_date'] = max_high_idx
                result['terminal_bar_price'] = max_high

        else:
            # For bearish: Type 2 requires breaking below B and/or 88.6% CD retracement
            target_886 = d_price - (cd_range * 0.886)

            # Check if price broke below B level
            min_low = df_window['low'].min()
            if min_low <= b_price:
                result['b_level_broken'] = True

            # Check if price exceeded 88.6% of CD
            if min_low <= target_886:
                result['cd_886_exceeded'] = True

            # Type 2 detected if either condition met
            if result['b_level_broken'] or result['cd_886_exceeded']:
                result['detected'] = True
                min_low_idx = df_window['low'].idxmin()
                result['terminal_bar_idx'] = df.index.get_loc(min_low_idx)
                result['terminal_bar_date'] = min_low_idx
                result['terminal_bar_price'] = min_low

        return result

    def _determine_reaction_type(self, type1_data: Dict[str, Any], type2_data: Optional[Dict[str, Any]]) -> str:
        """Determine overall reaction type."""
        if type2_data and type2_data.get('detected'):
            return 'TYPE_2'
        elif type1_data.get('detected'):
            if type1_data.get('trendline_broken'):
                return 'TYPE_1_FAILED'  # Type 1 started but trendline broken, watching for Type 2
            else:
                return 'TYPE_1'
        else:
            return 'NONE'

    def _generate_summary(self, reaction: ReactionData, pattern: Any) -> str:
        """Generate human-readable summary of reaction."""
        if reaction.reaction_type == 'PENDING':
            return "Pattern just completed - monitoring for reaction"

        elif reaction.reaction_type == 'NONE':
            return f"No reaction detected after {reaction.bars_since_completion} bars"

        elif reaction.reaction_type == 'TYPE_1':
            targets_hit = []
            if reaction.type1_reached_618:
                targets_hit.append("61.8% of CD")
            elif reaction.type1_reached_382:
                targets_hit.append("38.2% of CD")

            price_str = f" (reached ${reaction.type1_max_move:.2f})" if reaction.type1_max_move else ""
            if targets_hit:
                return f"TYPE 1 REACTION: Quick reversal from PRZ, reached {' and '.join(targets_hit)}{price_str}"
            else:
                return f"TYPE 1 REACTION: Initial reversal from PRZ{price_str}"

        elif reaction.reaction_type == 'TYPE_1_FAILED':
            return f"TYPE 1 reaction started but trendline broken - watching for TYPE 2"

        elif reaction.reaction_type == 'TYPE_2':
            price_str = f" (reached ${reaction.type2_terminal_bar_price:.2f})" if reaction.type2_terminal_bar_price else ""
            return f"TYPE 2 REVERSAL: Structural break confirmed - exceeded 88.6% of CD or broke B level{price_str}"

        return "Unknown reaction status"


if __name__ == "__main__":
    print("Reaction Detector - Type 1 and Type 2 Analysis")
    print("Based on Scott Carney's Harmonic Trading Volumes 1-3")
