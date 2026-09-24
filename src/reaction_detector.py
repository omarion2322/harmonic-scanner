"""
Type 1 (Reaction) and Type 2 (Reversal) Detection
Based on Scott Carney's Harmonic Trading Volumes 1-3

Type 1: Immediate reaction from PRZ (Terminal Bar + 1-3 bars)
Type 2: Secondary retest of PRZ after Type 1 reaction fails
"""

import pandas as pd
import numpy as np
from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, field_validator


class ReactionData(BaseModel):
    """
    Stores data about Type 1 or Type 2 reactions after pattern completion with validation.
    """
    reaction_type: str = Field(..., pattern='^(TYPE_1|TYPE_2_CANDIDATE|TYPE_2|TYPE_1_FAILED|NONE|PENDING)$',
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
    type2_reaction_area_low: Optional[float] = Field(None, gt=0, description="Lower bound of the Type 2 retest zone")
    type2_reaction_area_high: Optional[float] = Field(None, gt=0, description="Upper bound of the Type 2 retest zone")
    type2_retest_price: Optional[float] = Field(None, gt=0, description="Directional extreme of the retest candle")
    type2_retest_bar_idx: Optional[int] = Field(None, ge=0, description="Type 2 retest bar index")
    type2_retest_date: Optional[datetime] = Field(None, description="Type 2 retest date")
    type2_terminal_bar_idx: Optional[int] = Field(None, ge=0, description="Type 2 terminal bar index")
    type2_terminal_bar_date: Optional[datetime] = Field(None, description="Type 2 terminal bar date")
    type2_terminal_bar_price: Optional[float] = Field(None, gt=0, description="Type 2 terminal bar price")
    type2_entry_price: Optional[float] = Field(None, gt=0, description="Entry at Type 2 confirmation")
    type2_stop_loss: Optional[float] = Field(None, gt=0, description="Stop derived from the retest")
    type2_target_1: Optional[float] = Field(None, gt=0, description="Type 2 1R target")
    type2_target_2: Optional[float] = Field(None, gt=0, description="Type 2 2R target")
    type2_target_3: Optional[float] = Field(None, gt=0, description="Type 2 3R target")
    type2_forward_return_pct: Optional[float] = Field(
        None, description="Return from Type 2 confirmation entry to latest close"
    )
    type2_stop_hit: bool = Field(False, description="Whether the retest-derived stop was hit")
    type2_max_favorable_move: Optional[float] = Field(None, ge=0)
    type2_max_adverse_move: Optional[float] = Field(None, ge=0)

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


def detect_ordered_type2(
    df: pd.DataFrame,
    *,
    terminal_bar_idx: int,
    is_bullish: bool,
    d_price: float,
    c_price: float,
    stop_loss: Optional[float] = None,
    max_bars: int = 30,
    retest_tolerance: float = 0.02,
    type1_retrace_min: float = 0.382,
) -> Dict[str, Any]:
    """Detect an ordered move-away, PRZ retest, and second reversal."""
    result: Dict[str, Any] = {
        'candidate': False,
        'detected': False,
        'initial_move_bar_idx': None,
        'initial_move_date': None,
        'retest_bar_idx': None,
        'retest_date': None,
        'retest_price': None,
        'confirmation_bar_idx': None,
        'confirmation_date': None,
        'confirmation_price': None,
        'entry_price': None,
        'stop_loss': None,
        'target_1': None,
        'target_2': None,
        'target_3': None,
        'forward_return_pct': None,
        'stop_hit': False,
        'max_favorable_move': None,
        'max_adverse_move': None,
    }

    if max_bars < 3 or terminal_bar_idx >= len(df) - 2:
        return result

    high_col = 'high' if 'high' in df.columns else 'High'
    low_col = 'low' if 'low' in df.columns else 'Low'
    close_col = 'close' if 'close' in df.columns else 'Close'
    end_idx = min(terminal_bar_idx + max_bars + 1, len(df))
    window = df.iloc[terminal_bar_idx + 1:end_idx]
    if len(window) < 3:
        return result

    # A stopped pattern cannot later qualify through unrelated price action.
    if stop_loss is not None:
        stopped = window[low_col] <= stop_loss if is_bullish else window[high_col] >= stop_loss
        if stopped.any():
            first_stop = int(np.flatnonzero(stopped.to_numpy())[0])
            window = window.iloc[:first_stop]
            if len(window) < 3:
                return result

    cd_range = abs(d_price - c_price)
    if cd_range <= 0:
        return result

    move_threshold = cd_range * type1_retrace_min * 0.5
    if is_bullish:
        moved = window[high_col] >= d_price + move_threshold
    else:
        moved = window[low_col] <= d_price - move_threshold
    if not moved.any():
        return result

    move_pos = int(np.flatnonzero(moved.to_numpy())[0])
    move_label = window.index[move_pos]
    result['initial_move_bar_idx'] = terminal_bar_idx + 1 + move_pos
    result['initial_move_date'] = move_label

    later = window.iloc[move_pos + 1:]
    if later.empty:
        return result

    zone_low = d_price * (1 - retest_tolerance)
    zone_high = d_price * (1 + retest_tolerance)
    retested = (later[low_col] <= zone_high) & (later[high_col] >= zone_low)
    if not retested.any():
        return result

    retest_pos_in_later = int(np.flatnonzero(retested.to_numpy())[0])
    retest_pos = move_pos + 1 + retest_pos_in_later
    retest_label = window.index[retest_pos]
    retest_row = window.iloc[retest_pos]
    result['candidate'] = True
    result['retest_bar_idx'] = terminal_bar_idx + 1 + retest_pos
    result['retest_date'] = retest_label
    result['retest_price'] = float(retest_row[low_col] if is_bullish else retest_row[high_col])

    after_retest = window.iloc[retest_pos + 1:]
    if after_retest.empty:
        return result

    if is_bullish:
        retest_price = float(retest_row[low_col])
        confirmed = after_retest[high_col] >= retest_price + move_threshold
    else:
        retest_price = float(retest_row[high_col])
        confirmed = after_retest[low_col] <= retest_price - move_threshold
    if not confirmed.any():
        return result

    confirmation_pos_after_retest = int(np.flatnonzero(confirmed.to_numpy())[0])
    confirmation_pos = retest_pos + 1 + confirmation_pos_after_retest
    confirmation_label = window.index[confirmation_pos]
    confirmation_row = window.iloc[confirmation_pos]
    entry_price = float(confirmation_row[close_col])
    type2_stop = (
        retest_price * (1 - retest_tolerance)
        if is_bullish
        else retest_price * (1 + retest_tolerance)
    )
    risk = abs(entry_price - type2_stop)
    if risk <= 0:
        return result

    direction = 1 if is_bullish else -1
    latest_close = float(df[close_col].iloc[-1])
    post_confirmation = df.iloc[terminal_bar_idx + 1 + confirmation_pos:]
    if is_bullish:
        stop_hit = bool((post_confirmation[low_col] <= type2_stop).any())
        max_favorable_move = float(post_confirmation[high_col].max() - entry_price)
        max_adverse_move = float(entry_price - post_confirmation[low_col].min())
    else:
        stop_hit = bool((post_confirmation[high_col] >= type2_stop).any())
        max_favorable_move = float(entry_price - post_confirmation[low_col].min())
        max_adverse_move = float(post_confirmation[high_col].max() - entry_price)
    result.update({
        'detected': True,
        'confirmation_bar_idx': terminal_bar_idx + 1 + confirmation_pos,
        'confirmation_date': confirmation_label,
        'confirmation_price': entry_price,
        'entry_price': entry_price,
        'stop_loss': type2_stop,
        'target_1': entry_price + direction * risk,
        'target_2': entry_price + direction * risk * 2,
        'target_3': entry_price + direction * risk * 3,
        'forward_return_pct': direction * (latest_close - entry_price) / entry_price * 100,
        'stop_hit': stop_hit,
        'max_favorable_move': max(0.0, max_favorable_move),
        'max_adverse_move': max(0.0, max_adverse_move),
    })
    return result


class ReactionDetector:
    """
    Detects Type 1 (Reaction) and Type 2 (Reversal) scenarios
    after harmonic pattern completion at point D
    """

    def __init__(
        self,
        max_type2_bars: int = 30,
        type2_retest_tolerance: float = 0.02,
    ) -> None:
        self.max_type1_bars = 10  # Monitor up to 10 bars for Type 1
        self.max_type2_bars = max_type2_bars
        self.type2_retest_tolerance = type2_retest_tolerance

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
        reaction_area = {
            'type2_reaction_area_low': terminal_bar_price * (1 - self.type2_retest_tolerance),
            'type2_reaction_area_high': terminal_bar_price * (1 + self.type2_retest_tolerance),
        }

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
                reaction_summary="Pattern just completed - monitoring for reaction",
                **reaction_area,
            )

        # Detect Type 1 Reaction
        type1_data = self._detect_type1(df, pattern, terminal_bar_idx,
                                       current_idx, target_382, target_618)

        # Type 2 requires an ordered move away, retest, and second reversal.
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
            bars_since_completion=bars_since_completion,
            **reaction_area,
        )

        # Add Type 2 data if detected
        if type2_data and type2_data.get('candidate'):
            reaction.type2_detected = bool(type2_data['detected'])
            reaction.type2_retest_bar_idx = type2_data.get('retest_bar_idx')
            reaction.type2_retest_date = type2_data.get('retest_date')
            reaction.type2_retest_price = type2_data.get('retest_price')
            reaction.type2_terminal_bar_idx = type2_data.get('confirmation_bar_idx')
            reaction.type2_terminal_bar_date = type2_data.get('confirmation_date')
            reaction.type2_terminal_bar_price = type2_data.get('confirmation_price')
            reaction.type2_entry_price = type2_data.get('entry_price')
            reaction.type2_stop_loss = type2_data.get('stop_loss')
            reaction.type2_target_1 = type2_data.get('target_1')
            reaction.type2_target_2 = type2_data.get('target_2')
            reaction.type2_target_3 = type2_data.get('target_3')
            reaction.type2_forward_return_pct = type2_data.get('forward_return_pct')
            reaction.type2_stop_hit = bool(type2_data.get('stop_hit'))
            reaction.type2_max_favorable_move = type2_data.get('max_favorable_move')
            reaction.type2_max_adverse_move = type2_data.get('max_adverse_move')

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
        Detect an ordered Type 2 sequence after pattern completion.
        """
        return detect_ordered_type2(
            df.iloc[:current_idx + 1],
            terminal_bar_idx=terminal_bar_idx,
            is_bullish=pattern.is_bullish,
            d_price=pattern.d.price,
            c_price=pattern.c.price,
            stop_loss=getattr(pattern, 'stop_loss', None),
            max_bars=self.max_type2_bars,
            retest_tolerance=self.type2_retest_tolerance,
        )

    def _determine_reaction_type(self, type1_data: Dict[str, Any], type2_data: Optional[Dict[str, Any]]) -> str:
        """Determine overall reaction type."""
        if type2_data and type2_data.get('detected'):
            return 'TYPE_2'
        elif type2_data and type2_data.get('candidate'):
            return 'TYPE_2_CANDIDATE'
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

        elif reaction.reaction_type == 'TYPE_2_CANDIDATE':
            return "TYPE 2 CANDIDATE: Initial reaction and PRZ retest found; waiting for a second reversal"

        elif reaction.reaction_type == 'TYPE_2':
            price_str = f" at ${reaction.type2_entry_price:.2f}" if reaction.type2_entry_price else ""
            return f"TYPE 2 CONFIRMED: Ordered reaction, PRZ retest, and second reversal{price_str}"

        return "Unknown reaction status"


if __name__ == "__main__":
    print("Reaction Detector - Type 1 and Type 2 Analysis")
    print("Based on Scott Carney's Harmonic Trading Volumes 1-3")
