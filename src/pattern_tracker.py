"""
Pattern State Tracking System for Real-Time Harmonic Pattern Detection

This module tracks harmonic patterns across daily scans to:
1. Monitor pattern evolution (forming → completed → confirmed)
2. Detect D-point extensions/invalidations
3. Analyze price reactions (Type 1, Type 2)
4. Maintain watchlists and trading signals

Author: Harmonic Trading System
"""

import json
import hashlib
import sqlite3
from types import SimpleNamespace
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum
from pydantic import BaseModel, Field, field_validator
from logging_config import get_logger
from reaction_detector import detect_ordered_type2
from divergence_detector import (
    DivergenceConfig, DivergenceDetector, MEASURED_STATUSES, closed_retest_date,
    pattern_anchor, utc_timestamp,
)

logger = get_logger(__name__)


class PatternStatus(Enum):
    """Pattern lifecycle states"""
    FORMING = "forming"              # 80-99% complete, approaching PRZ
    COMPLETED = "completed"          # 100% complete, at D-point
    AWAITING_CONFIRMATION = "awaiting_confirmation"  # Completed, waiting for reaction
    CONFIRMED_TYPE1 = "confirmed_type1"  # Type 1 reaction detected
    TYPE2_CANDIDATE = "type2_candidate"  # Retested PRZ, awaiting second reversal
    CONFIRMED_TYPE2 = "confirmed_type2"  # Type 2 reaction detected
    INVALIDATED = "invalidated"      # D-point extended beyond tolerance
    STOPPED_OUT = "stopped_out"      # Stop loss hit
    TARGET_HIT = "target_hit"        # At least one target reached
    EXPIRED = "expired"              # Too old, no longer relevant


class ReactionType(Enum):
    """Price reaction types at PRZ"""
    NONE = "none"
    TYPE_1 = "type_1"  # Quick reversal, reached 38.2% or 61.8% of CD
    TYPE_2_CANDIDATE = "type_2_candidate"  # Retest found, awaiting confirmation
    TYPE_2 = "type_2"  # Retest of PRZ after initial bounce
    FAILED = "failed"  # Broke through PRZ without reversal


class PatternSnapshot(BaseModel):
    """Snapshot of pattern state at a point in time with validation."""
    pattern_id: str = Field(..., min_length=1, description="Unique pattern identifier")
    ticker: str = Field(..., min_length=1, description="Stock ticker symbol")
    pattern_type: str = Field(..., min_length=1, description="Harmonic pattern type")
    is_bullish: bool = Field(..., description="Pattern direction")

    # XABCD points
    x_date: str = Field(..., description="X point date (ISO format)")
    x_price: float = Field(..., gt=0, description="X point price")
    a_date: str = Field(..., description="A point date (ISO format)")
    a_price: float = Field(..., gt=0, description="A point price")
    b_date: str = Field(..., description="B point date (ISO format)")
    b_price: float = Field(..., gt=0, description="B point price")
    c_date: str = Field(..., description="C point date (ISO format)")
    c_price: float = Field(..., gt=0, description="C point price")
    d_date: str = Field(..., description="D point date (ISO format)")
    d_price: float = Field(..., gt=0, description="D point price")

    # Trading levels
    entry_price: float = Field(..., gt=0, description="Entry price")
    stop_loss: float = Field(..., gt=0, description="Stop loss price")
    target_1: Optional[float] = Field(None, gt=0, description="First profit target")
    target_2: Optional[float] = Field(None, gt=0, description="Second profit target")
    target_3: Optional[float] = Field(None, gt=0, description="Third profit target")

    # Entry locking (Solution 1)
    entry_locked: bool = Field(False, description="True when pattern first completes")
    original_entry_price: float = Field(..., gt=0, description="First valid entry price")
    original_entry_date: str = Field("", description="When pattern first reached PRZ")

    # D-Point Range (Solution 2)
    d_point_range_min: float = Field(0.0, gt=0, description="Minimum valid D-point price")
    d_point_range_max: float = Field(0.0, gt=0, description="Maximum valid D-point price")

    # Pattern metrics
    grade: str = Field(..., pattern='^[A-D][+-]?$', description="Pattern grade")
    risk_reward: float = Field(..., ge=0, description="Risk/reward ratio")
    completion_percentage: float = Field(..., ge=0.0, le=1.0, description="Pattern completion")

    # State tracking
    status: str = Field(..., description="Pattern status")
    reaction_type: str = Field(..., description="Reaction type")
    first_detected: str = Field(..., description="ISO timestamp of first detection")
    last_updated: str = Field(..., description="ISO timestamp of last update")
    days_monitored: int = Field(0, ge=0, description="Days since first detection")

    # Evolution tracking
    d_price_history: List[float] = Field(default_factory=list, description="D-point price history")
    d_extended: bool = Field(False, description="D moved beyond tolerance")

    # Reaction metrics
    max_favorable_move: float = Field(0.0, ge=0, description="Max favorable move from D")
    max_adverse_move: float = Field(0.0, ge=0, description="Max adverse move from D")
    targets_hit: List[int] = Field(default_factory=list, description="Targets hit (1, 2, 3)")
    type1_date: str = Field("", description="First date the Type 1 threshold was reached")
    type2_retest_date: str = Field("", description="Date price retested the PRZ")
    type2_confirmation_date: str = Field("", description="Date the second reversal confirmed")
    type2_entry_price: Optional[float] = Field(None, gt=0, description="Type 2 confirmation entry")
    type2_stop_loss: Optional[float] = Field(None, gt=0, description="Stop derived from the retest")
    type2_target_1: Optional[float] = Field(None, gt=0, description="Type 2 1R target")
    type2_target_2: Optional[float] = Field(None, gt=0, description="Type 2 2R target")
    type2_target_3: Optional[float] = Field(None, gt=0, description="Type 2 3R target")
    type2_forward_return_pct: Optional[float] = Field(
        None, description="Return from Type 2 entry to latest close"
    )
    type2_stop_hit: bool = Field(False, description="Whether the Type 2 stop was hit")
    type2_max_favorable_move: Optional[float] = Field(None, ge=0)
    type2_max_adverse_move: Optional[float] = Field(None, ge=0)
    divergence: Optional[Dict[str, Any]] = Field(
        None, description="Contextual momentum evidence; not a trading confirmation"
    )

    @field_validator('targets_hit')
    @classmethod
    def validate_targets(cls, v: List[int]) -> List[int]:
        """Ensure targets are 1, 2, or 3."""
        for target in v:
            if target not in [1, 2, 3]:
                raise ValueError(f'Invalid target: {target}. Must be 1, 2, or 3')
        return v

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict) -> 'PatternSnapshot':
        """Create from dictionary with backward compatibility for old patterns."""
        # Add default values for new fields if they don't exist
        defaults = {
            'entry_locked': False,
            'original_entry_price': data.get('entry_price', 0.0),
            'original_entry_date': '',
            'd_point_range_min': 0.0,
            'd_point_range_max': 0.0,
            'd_price_history': [],
            'targets_hit': [],
            'type1_date': '',
            'type2_retest_date': '',
            'type2_confirmation_date': '',
            'type2_entry_price': None,
            'type2_stop_loss': None,
            'type2_target_1': None,
            'type2_target_2': None,
            'type2_target_3': None,
            'type2_forward_return_pct': None,
            'type2_stop_hit': False,
            'type2_max_favorable_move': None,
            'type2_max_adverse_move': None,
        }

        # Merge defaults with data (data takes precedence)
        for key, value in defaults.items():
            if key not in data:
                data[key] = value

        return cls(**data)

    class Config:
        str_strip_whitespace = True


class PatternTracker:
    """
    Tracks harmonic patterns across daily scans to monitor evolution and detect confirmations.
    """

    def __init__(self, storage_dir: str = "./pattern_tracking") -> None:
        """
        Initialize pattern tracker.

        Args:
            storage_dir: Directory to store pattern state files
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # Configuration
        self.D_EXTENSION_TOLERANCE = 0.05  # 5% - D-point can move this much
        self.MAX_PATTERN_AGE_DAYS = 30     # Expire patterns after 30 days
        self.MAX_REACTION_BARS = 30        # Monitor completed patterns for Type 2
        self.TYPE1_RETRACE_MIN = 0.382     # Type 1 needs 38.2% retrace of CD
        self.TYPE2_RETEST_TOLERANCE = 0.02 # 2% tolerance for PRZ retest

        # State files
        self.active_patterns_file = self.storage_dir / "active_patterns.json"
        self.history_file = self.storage_dir / "pattern_history.json"

        # Load existing state
        self.active_patterns = self._load_active_patterns()
        self.divergence_config = DivergenceConfig()
        self.divergence_interval = "1d"

    def analyze_divergence(self, ticker: str, pattern: Any, price_data: pd.DataFrame,
                           interval: str = "1d", as_of: Any = None,
                           retest_date: Any = None) -> dict:
        """Persist separate initial-D and ordered-retest samples beyond active expiry.

        SQLite transactions also serialize parallel ticker workers. Configuration
        revisions are evaluations of the same sample, not additional observations.
        """
        observed_at = utc_timestamp(as_of).isoformat()
        retest_date = closed_retest_date(retest_date, interval, observed_at)
        initial_evidence = None
        if retest_date is not None:
            # Never replace the initial-D ledger with a retest evaluation.
            initial_evidence = self.analyze_divergence(
                ticker, pattern, price_data, interval, observed_at
            )
        context = "type2_retest" if retest_date is not None else "initial_d"
        identity = [
            ticker, pattern.pattern_type, bool(pattern.is_bullish), interval, context,
            *[utc_timestamp(getattr(pattern, point).date).isoformat() for point in "xabc"],
        ]
        if retest_date is not None:
            identity.extend([utc_timestamp(pattern.d.date).isoformat(), retest_date])
        sample_id = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
        evaluation_id = self.divergence_config.evaluation_id_for(context)
        with sqlite3.connect(self.storage_dir / "divergence.sqlite3", timeout=30) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS divergence_samples "
                "(sample_id TEXT PRIMARY KEY, identity_json TEXT NOT NULL, "
                "anchor_json TEXT NOT NULL, first_observed_at TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS divergence_evaluations "
                "(sample_id TEXT NOT NULL, evaluation_id TEXT NOT NULL, payload TEXT NOT NULL, "
                "PRIMARY KEY (sample_id, evaluation_id))"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS divergence_point_readings "
                "(sample_id TEXT NOT NULL, measurement_version TEXT NOT NULL, "
                "point_role TEXT NOT NULL, indicator TEXT NOT NULL, payload TEXT NOT NULL, "
                "PRIMARY KEY (sample_id, measurement_version, point_role, indicator))"
            )
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT OR IGNORE INTO divergence_samples VALUES (?, ?, ?, ?)",
                (sample_id, json.dumps(identity),
                 json.dumps(pattern_anchor(pattern, retest_date)), observed_at),
            )
            anchor_json, first_observed = connection.execute(
                "SELECT anchor_json, first_observed_at FROM divergence_samples WHERE sample_id = ?",
                (sample_id,),
            ).fetchone()
            previous = connection.execute(
                "SELECT payload FROM divergence_evaluations WHERE sample_id = ? AND evaluation_id = ?",
                (sample_id, evaluation_id),
            ).fetchone()
            old = json.loads(previous[0]) if previous else None
            anchor = json.loads(anchor_json)
            detector = DivergenceDetector(self.divergence_config)
            immutable = bool(old and old["status"] in MEASURED_STATUSES)
            if immutable and utc_timestamp(old["available_at"]) <= utc_timestamp(observed_at):
                evidence = old
                evidence["point_readings"] = {
                    "d": detector.measure_point(price_data, anchor["d_date"], interval, observed_at),
                    "retest": detector.measure_point(
                        price_data, anchor["retest_date"], interval, observed_at
                    ) if context == "type2_retest" else None,
                }
            else:
                evidence = detector.detect(
                    price_data, anchor, interval, as_of=observed_at
                )
                evidence.update(
                    sample_id=sample_id,
                    sample_first_observed_at=first_observed,
                    evaluation_first_observed_at=(
                        old["evaluation_first_observed_at"] if old else observed_at
                    ),
                    confirmed_observed_at=(
                        observed_at if evidence["status"] in MEASURED_STATUSES else None
                    ),
                )
            # Numeric observations freeze independently: pending decisions and a
            # missing MACD warmup must not erase an already captured RSI reading.
            for role, reading in evidence["point_readings"].items():
                if reading is None:
                    continue
                for name in ("rsi", "macd"):
                    identity = (sample_id, reading["measurement_version"], role, name)
                    if reading[name]["value"] is not None:
                        connection.execute(
                            "INSERT OR IGNORE INTO divergence_point_readings VALUES (?, ?, ?, ?, ?)",
                            (*identity, json.dumps(reading[name], allow_nan=False)),
                        )
                    saved = connection.execute(
                        "SELECT payload FROM divergence_point_readings WHERE sample_id=? "
                        "AND measurement_version=? AND point_role=? AND indicator=?",
                        identity,
                    ).fetchone()
                    if saved:
                        observation = json.loads(saved[0])
                        if utc_timestamp(observation["available_at"]) <= utc_timestamp(observed_at):
                            reading[name] = observation
                            reading["available_at"] = observation["available_at"]
            evidence["initial_d_reading"] = (
                initial_evidence["initial_d_reading"] if initial_evidence is not None
                else evidence["point_readings"]["d"]
            )
            if not immutable:
                connection.execute(
                    "INSERT OR REPLACE INTO divergence_evaluations VALUES (?, ?, ?)",
                    (sample_id, evaluation_id, json.dumps(evidence, allow_nan=False)),
                )
        pattern.divergence = evidence
        return evidence

    def _refresh_snapshot_divergence(self, snapshot: PatternSnapshot,
                                    price_data: pd.DataFrame, as_of: Any) -> None:
        if getattr(snapshot, "status", None) == PatternStatus.FORMING.value:
            # Completion percentage can fall after a bounce even though D was hit.
            # Do not freeze a projected/missing D, but capture an actual closed bar.
            closed_d = closed_retest_date(snapshot.d_date, self.divergence_interval, as_of)
            if (closed_d is None or not isinstance(price_data.index, pd.DatetimeIndex)
                    or utc_timestamp(closed_d) not in pd.to_datetime(price_data.index, utc=True)):
                return
        retest_date = getattr(snapshot, "type2_retest_date", None) or (
            snapshot.divergence.get("anchor", {}).get("retest_date") if snapshot.divergence else None
        )
        retest_date = closed_retest_date(retest_date, self.divergence_interval, as_of)
        context = "type2_retest" if retest_date is not None else "initial_d"
        if (snapshot.divergence and snapshot.divergence["status"] in MEASURED_STATUSES
                and utc_timestamp(snapshot.divergence["available_at"]) <= utc_timestamp(as_of)
                and not snapshot.divergence.get("persistence_error")
                and snapshot.divergence.get("context") == context
                and snapshot.divergence.get("anchor", {}).get("retest_date") == retest_date
                and (retest_date is None or
                     utc_timestamp(snapshot.divergence["anchor"]["d_date"])
                     == utc_timestamp(snapshot.d_date))
                and snapshot.divergence.get("evaluation_id")
                == self.divergence_config.evaluation_id_for(context)
                and all(
                    reading and all(reading.get(name, {}).get("value") is not None
                                    for name in ("rsi", "macd"))
                    for reading in (
                        snapshot.divergence.get("point_readings", {}).get("d"),
                        snapshot.divergence.get("initial_d_reading"),
                        *([snapshot.divergence.get("point_readings", {}).get("retest")]
                          if retest_date is not None else []),
                    )
                )):
            return
        pattern = SimpleNamespace(
            **{point: SimpleNamespace(
                date=getattr(snapshot, f"{point}_date"),
                price=getattr(snapshot, f"{point}_price"),
            ) for point in "xabcd"},
            pattern_type=snapshot.pattern_type, is_bullish=snapshot.is_bullish,
            d_point_range_min=snapshot.d_point_range_min,
            d_point_range_max=snapshot.d_point_range_max,
        )
        try:
            snapshot.divergence = self.analyze_divergence(
                snapshot.ticker, pattern, price_data, self.divergence_interval, as_of,
                retest_date=retest_date,
            )
        except (sqlite3.Error, OSError) as exc:
            logger.warning("Could not persist divergence for %s: %s", snapshot.pattern_id, exc)
            snapshot.divergence = DivergenceDetector(self.divergence_config).detect(
                price_data, pattern_anchor(pattern, retest_date), self.divergence_interval, as_of
            )
            snapshot.divergence["persistence_error"] = True

    def _calculate_completion(self, pattern: Any, price_data: pd.DataFrame) -> Tuple[float, str]:
        """
        Calculate pattern completion percentage based on current price vs projected D-point.

        Args:
            pattern: HarmonicPattern object
            price_data: DataFrame with OHLC data

        Returns:
            Tuple of (completion_percentage, status)
        """
        try:
            # Get current price (most recent close)
            current_price = price_data['close'].iloc[-1] if 'close' in price_data.columns else price_data['Close'].iloc[-1]

            # Get C and D prices
            c_price = pattern.c.price
            d_price = pattern.d.price  # Projected D point

            # Calculate CD range
            cd_range = abs(d_price - c_price)

            if cd_range == 0:
                # If C and D are same price, pattern is either complete or invalid
                return (1.0, PatternStatus.COMPLETED.value)

            # Calculate how far from C to D we've moved
            if pattern.is_bullish:
                # Bullish: D should be below C (price moving down to PRZ)
                # Completion = (C - current) / (C - D)
                progress = (c_price - current_price) / (c_price - d_price)
            else:
                # Bearish: D should be above C (price moving up to PRZ)
                # Completion = (current - C) / (D - C)
                progress = (current_price - c_price) / (d_price - c_price)

            # Clamp between 0 and 1
            completion_pct = max(0.0, min(1.0, progress))

            # Determine status
            # FORMING: 80-99% complete (approaching D but not there yet)
            # COMPLETED: >= 100% (reached or passed D-point)
            if completion_pct >= 0.99:  # Within 1% of D-point, consider it complete
                status = PatternStatus.COMPLETED.value
                completion_pct = 1.0
            elif completion_pct >= 0.80:  # 80-99% complete
                status = PatternStatus.FORMING.value
            else:
                # Less than 80% complete - not worth tracking yet
                # But we'll still track it as FORMING with lower completion
                status = PatternStatus.FORMING.value

            return (completion_pct, status)

        except Exception as e:
            # If we can't calculate, assume pattern is complete
            # (this handles patterns detected by search() which are already at D)
            return (1.0, PatternStatus.COMPLETED.value)

    def _load_active_patterns(self) -> Dict[str, PatternSnapshot]:
        """Load active patterns from storage"""
        if not self.active_patterns_file.exists():
            return {}

        try:
            with open(self.active_patterns_file, 'r') as f:
                data = json.load(f)
                patterns = {}
                for k, v in data.items():
                    try:
                        patterns[k] = PatternSnapshot.from_dict(v)
                    except (KeyError, ValueError, TypeError) as e:
                        logger.warning("Could not load pattern %s (invalid data): %s", k, e)
                        # Skip corrupted patterns
                        continue
                    except Exception as e:
                        logger.warning("Unexpected error loading pattern %s: %s", k, e)
                        # Skip corrupted patterns
                        continue
                return patterns
        except json.JSONDecodeError as e:
            logger.warning("Could not parse active patterns file (invalid JSON): %s", e)
            logger.info("Starting with empty pattern tracker. Old data preserved as backup.")
            # Backup the corrupted file
            import shutil
            backup_path = self.active_patterns_file.with_suffix('.json.bak')
            try:
                shutil.copy(self.active_patterns_file, backup_path)
                logger.info("Backup saved to: %s", backup_path)
            except (OSError, IOError) as backup_e:
                logger.warning("Could not create backup: %s", backup_e)
            return {}
        except (OSError, IOError) as e:
            logger.warning("Could not read active patterns file: %s", e)
            logger.info("Starting with empty pattern tracker.")
            return {}
        except Exception as e:
            logger.warning("Unexpected error loading active patterns: %s", e)
            logger.info("Starting with empty pattern tracker.")
            return {}

    def _save_active_patterns(self) -> None:
        """Save active patterns to storage"""
        try:
            data = {k: v.to_dict() for k, v in self.active_patterns.items()}
            with open(self.active_patterns_file, 'w') as f:
                json.dump(data, f, indent=2)
        except (OSError, IOError) as e:
            logger.error("Failed to write active patterns file: %s", e)
        except (TypeError, ValueError) as e:
            logger.error("Failed to serialize active patterns (invalid data): %s", e)
        except Exception as e:
            logger.error("Unexpected error saving active patterns: %s", e)

    def _archive_pattern(self, pattern: PatternSnapshot) -> None:
        """Archive completed/invalidated pattern to history"""
        try:
            history = []
            if self.history_file.exists():
                try:
                    with open(self.history_file, 'r') as f:
                        history = json.load(f)
                except json.JSONDecodeError as e:
                    # Corrupted JSON file - backup and start fresh
                    logger.warning("Corrupted history file detected: %s", e)
                    import shutil
                    backup_path = self.history_file.with_suffix(f'.json.corrupt.{datetime.now().strftime("%Y%m%d_%H%M%S")}')
                    try:
                        shutil.copy(self.history_file, backup_path)
                        logger.info("Corrupted history backed up to: %s", backup_path)
                    except Exception as backup_error:
                        logger.error("Could not backup corrupted file: %s", backup_error)
                    # Start with empty history
                    history = []

            history.append(pattern.to_dict())

            with open(self.history_file, 'w') as f:
                json.dump(history, f, indent=2)
        except Exception as e:
            logger.error("Error archiving pattern: %s", e)

    def generate_pattern_id(self, ticker: str, x_date: str, a_date: str,
                           b_date: str, c_date: str, pattern_type: str) -> str:
        """
        Generate unique pattern ID based on XABC points.
        D-point is NOT included because it can extend/change.

        Args:
            ticker: Stock ticker
            x_date, a_date, b_date, c_date: Point dates (ISO format)
            pattern_type: Pattern type (e.g., 'butterfly')

        Returns:
            Unique pattern ID
        """
        # Use XABC dates only (D can change)
        return f"{ticker}_{pattern_type}_{x_date}_{a_date}_{b_date}_{c_date}"

    def update_patterns(self, ticker: str, detected_patterns: List[Any],
                       price_data: pd.DataFrame, current_date: datetime) -> Dict[str, List[PatternSnapshot]]:
        """
        Update pattern states based on newly detected patterns and price action.

        Args:
            ticker: Stock ticker being scanned
            detected_patterns: List of HarmonicPattern objects from detector
            price_data: OHLC price data
            current_date: Current scan date

        Returns:
            Dictionary with categorized patterns:
            {
                'new_patterns': [...],
                'watchlist': [...],        # Forming patterns
                'confirmed': [...],         # Ready to trade
                'monitoring': [...],        # Awaiting confirmation
                'invalidated': [...],       # D-point extended
                'completed': [...]          # Targets hit or stopped out
            }
        """
        results: Dict[str, List[PatternSnapshot]] = {
            'new_patterns': [],
            'watchlist': [],
            'confirmed': [],
            'monitoring': [],
            'invalidated': [],
            'completed': []
        }

        current_timestamp = current_date.isoformat()
        processed_pattern_ids = set()

        # Process each detected pattern
        for pattern in detected_patterns:
            pattern_id = self.generate_pattern_id(
                ticker=ticker,
                x_date=pattern.x.date.isoformat(),
                a_date=pattern.a.date.isoformat(),
                b_date=pattern.b.date.isoformat(),
                c_date=pattern.c.date.isoformat(),
                pattern_type=pattern.pattern_type
            )
            processed_pattern_ids.add(pattern_id)

            # Check if this is an existing pattern
            if pattern_id in self.active_patterns:
                # Update existing pattern
                snapshot = self._update_existing_pattern(
                    pattern_id, pattern, price_data, current_timestamp
                )
            else:
                # New pattern detected
                snapshot = self._create_new_pattern(
                    pattern_id, ticker, pattern, price_data, current_timestamp
                )
                results['new_patterns'].append(snapshot)

            if (isinstance(getattr(pattern, 'divergence', None), dict)
                    and not (snapshot.divergence
                             and snapshot.divergence["status"] in MEASURED_STATUSES
                             and snapshot.divergence.get("sample_id")
                             == pattern.divergence.get("sample_id")
                             and snapshot.divergence.get("context")
                             == pattern.divergence.get("context")
                             and snapshot.divergence.get("evaluation_id")
                             == pattern.divergence.get("evaluation_id"))):
                snapshot.divergence = pattern.divergence
            self._refresh_snapshot_divergence(snapshot, price_data, current_timestamp)

            # Categorize pattern by status
            if snapshot.status == PatternStatus.FORMING.value:
                results['watchlist'].append(snapshot)
            elif snapshot.status in [PatternStatus.CONFIRMED_TYPE1.value,
                                    PatternStatus.CONFIRMED_TYPE2.value]:
                results['confirmed'].append(snapshot)
            elif snapshot.status in [PatternStatus.COMPLETED.value,
                                    PatternStatus.AWAITING_CONFIRMATION.value,
                                    PatternStatus.TYPE2_CANDIDATE.value]:
                results['monitoring'].append(snapshot)
            elif snapshot.status == PatternStatus.INVALIDATED.value:
                results['invalidated'].append(snapshot)
                self._archive_pattern(snapshot)
                del self.active_patterns[pattern_id]
            elif snapshot.status in [PatternStatus.TARGET_HIT.value,
                                    PatternStatus.STOPPED_OUT.value,
                                    PatternStatus.EXPIRED.value]:
                results['completed'].append(snapshot)
                self._archive_pattern(snapshot)
                del self.active_patterns[pattern_id]

        # Continue monitoring completed patterns even if the detector no longer
        # returns them in the current scan.
        for pattern_id, snapshot in list(self.active_patterns.items()):
            if snapshot.ticker != ticker or pattern_id in processed_pattern_ids:
                continue
            if snapshot.status == PatternStatus.FORMING.value:
                self._refresh_snapshot_divergence(snapshot, price_data, current_timestamp)
                continue
            if snapshot.status not in {
                PatternStatus.COMPLETED.value,
                PatternStatus.AWAITING_CONFIRMATION.value,
                PatternStatus.CONFIRMED_TYPE1.value,
                PatternStatus.TYPE2_CANDIDATE.value,
                PatternStatus.CONFIRMED_TYPE2.value,
            }:
                continue

            self._analyze_reaction(snapshot, price_data)
            self._refresh_snapshot_divergence(snapshot, price_data, current_timestamp)
            if snapshot.status in {
                PatternStatus.CONFIRMED_TYPE1.value,
                PatternStatus.CONFIRMED_TYPE2.value,
            }:
                results['confirmed'].append(snapshot)
            elif snapshot.status in {
                PatternStatus.COMPLETED.value,
                PatternStatus.AWAITING_CONFIRMATION.value,
                PatternStatus.TYPE2_CANDIDATE.value,
            }:
                results['monitoring'].append(snapshot)
            elif snapshot.status in {
                PatternStatus.TARGET_HIT.value,
                PatternStatus.STOPPED_OUT.value,
                PatternStatus.EXPIRED.value,
            }:
                results['completed'].append(snapshot)
                self._archive_pattern(snapshot)
                del self.active_patterns[pattern_id]

        # Check for expired patterns not in current scan
        self._check_expired_patterns(current_date, results)

        # Save updated state
        self._save_active_patterns()

        return results

    def _create_new_pattern(self, pattern_id: str, ticker: str,
                           pattern: Any, price_data: pd.DataFrame,
                           current_timestamp: str) -> PatternSnapshot:
        """Create new pattern snapshot"""
        # Calculate completion percentage based on current price vs D-point
        completion_pct, pattern_status = self._calculate_completion(pattern, price_data)

        # Get D-point range from pattern (if available)
        d_range_min = getattr(pattern, 'd_point_range_min', pattern.d.price)
        d_range_max = getattr(pattern, 'd_point_range_max', pattern.d.price)

        # Entry locking: lock entry when pattern first completes
        entry_locked = (pattern_status == PatternStatus.COMPLETED.value)
        original_entry_price = pattern.entry_price if entry_locked else pattern.d.price
        original_entry_date = current_timestamp if entry_locked else ""

        snapshot = PatternSnapshot(
            pattern_id=pattern_id,
            ticker=ticker,
            pattern_type=pattern.pattern_type,
            is_bullish=pattern.is_bullish,
            x_date=pattern.x.date.isoformat(),
            x_price=pattern.x.price,
            a_date=pattern.a.date.isoformat(),
            a_price=pattern.a.price,
            b_date=pattern.b.date.isoformat(),
            b_price=pattern.b.price,
            c_date=pattern.c.date.isoformat(),
            c_price=pattern.c.price,
            d_date=pattern.d.date.isoformat(),
            d_price=pattern.d.price,
            entry_price=pattern.entry_price,
            stop_loss=pattern.stop_loss,
            target_1=pattern.ipo_target_1,
            target_2=pattern.ipo_target_2,
            target_3=pattern.target_point_a,
            # Entry locking fields
            entry_locked=entry_locked,
            original_entry_price=original_entry_price,
            original_entry_date=original_entry_date,
            # D-point range fields
            d_point_range_min=d_range_min,
            d_point_range_max=d_range_max,
            grade=pattern.grade,
            risk_reward=pattern.risk_reward,
            completion_percentage=completion_pct,
            status=pattern_status,
            reaction_type=ReactionType.NONE.value,
            first_detected=current_timestamp,
            last_updated=current_timestamp,
            days_monitored=0,
            d_price_history=[pattern.d.price],
            d_extended=False,
            max_favorable_move=0.0,
            max_adverse_move=0.0,
            targets_hit=[],
            type1_date="",
            type2_retest_date="",
            type2_confirmation_date="",
            type2_entry_price=None,
            type2_stop_loss=None,
            type2_target_1=None,
            type2_target_2=None,
            type2_target_3=None,
            type2_forward_return_pct=None,
            type2_stop_hit=False,
            type2_max_favorable_move=None,
            type2_max_adverse_move=None,
        )

        # Analyze initial reaction (only if completed)
        if pattern_status == PatternStatus.COMPLETED.value:
            self._analyze_reaction(snapshot, price_data)

        # Store in active patterns
        self.active_patterns[pattern_id] = snapshot

        return snapshot

    def _update_existing_pattern(self, pattern_id: str, pattern: Any,
                                 price_data: pd.DataFrame,
                                 current_timestamp: str) -> PatternSnapshot:
        """Update existing pattern with new data"""
        snapshot = self.active_patterns[pattern_id]

        # Update last_updated timestamp
        snapshot.last_updated = current_timestamp

        # Update days monitored
        first_detected = datetime.fromisoformat(snapshot.first_detected)
        current_date = datetime.fromisoformat(current_timestamp)
        snapshot.days_monitored = (current_date - first_detected).days

        # Check pattern completion status to lock entry
        completion_pct, pattern_status = self._calculate_completion(pattern, price_data)

        # Lock entry when pattern first transitions to COMPLETED
        if not snapshot.entry_locked and pattern_status == PatternStatus.COMPLETED.value:
            snapshot.entry_locked = True
            snapshot.original_entry_price = pattern.entry_price
            snapshot.original_entry_date = current_timestamp
            logger.info("Pattern %s: Entry locked at $%.2f", pattern_id, pattern.entry_price)

        # Check if D-point has moved
        old_d_price = snapshot.d_price
        new_d_price = pattern.d.price

        # Track D-point history
        if new_d_price not in snapshot.d_price_history:
            snapshot.d_price_history.append(new_d_price)

        # Check if D extended beyond tolerance
        d_move_pct = abs(new_d_price - old_d_price) / old_d_price
        if d_move_pct > self.D_EXTENSION_TOLERANCE:
            if snapshot.is_bullish:
                # For bullish, D should not go lower
                if new_d_price < old_d_price:
                    snapshot.d_extended = True
                    snapshot.status = PatternStatus.INVALIDATED.value
                    logger.warning("Pattern %s: D-point extended %.2f -> %.2f (bearish extension in bullish pattern)",
                                 pattern_id, old_d_price, new_d_price)
            else:
                # For bearish, D should not go higher
                if new_d_price > old_d_price:
                    snapshot.d_extended = True
                    snapshot.status = PatternStatus.INVALIDATED.value
                    logger.warning("Pattern %s: D-point extended %.2f -> %.2f (bullish extension in bearish pattern)",
                                 pattern_id, old_d_price, new_d_price)

        # Update D-point if not extended
        if not snapshot.d_extended:
            snapshot.d_date = pattern.d.date.isoformat()
            snapshot.d_price = new_d_price

            # Update current entry_price (for tracking), but preserve original_entry_price if locked
            snapshot.entry_price = pattern.entry_price

            # Update D-point range ONLY if entry is not locked
            # Once entry is locked, the PRZ zone is fixed and should not change
            if not snapshot.entry_locked:
                snapshot.d_point_range_min = getattr(pattern, 'd_point_range_min', pattern.d.price)
                snapshot.d_point_range_max = getattr(pattern, 'd_point_range_max', pattern.d.price)
            # If entry is locked, preserve the original PRZ zone

            # Re-analyze reaction with updated data
            if snapshot.status in [
                PatternStatus.COMPLETED.value,
                PatternStatus.AWAITING_CONFIRMATION.value,
                PatternStatus.CONFIRMED_TYPE1.value,
                PatternStatus.TYPE2_CANDIDATE.value,
                PatternStatus.CONFIRMED_TYPE2.value,
            ]:
                self._analyze_reaction(snapshot, price_data)

        return snapshot

    def _analyze_reaction(self, snapshot: PatternSnapshot, price_data: pd.DataFrame) -> None:
        """
        Analyze price reaction after D-point completion.
        Detects Type 1 and Type 2 reactions.
        """
        try:
            # Validate price_data
            if price_data is None or len(price_data) == 0:
                snapshot.status = PatternStatus.AWAITING_CONFIRMATION.value
                return

            # Get price action after D-point
            d_date = pd.Timestamp(snapshot.d_date)
            after_d = price_data[price_data.index > d_date].copy()

            if len(after_d) == 0:
                # No price action yet
                snapshot.status = PatternStatus.AWAITING_CONFIRMATION.value
                return

            # Calculate moves from D-point (handle both uppercase and lowercase column names)
            high_col = 'high' if 'high' in after_d.columns else 'High'
            low_col = 'low' if 'low' in after_d.columns else 'Low'

            if snapshot.is_bullish:
                # For bullish: favorable = up, adverse = down
                favorable_moves = after_d[high_col] - snapshot.d_price
                adverse_moves = snapshot.d_price - after_d[low_col]
            else:
                # For bearish: favorable = down, adverse = up
                favorable_moves = snapshot.d_price - after_d[low_col]
                adverse_moves = after_d[high_col] - snapshot.d_price

            max_favorable = favorable_moves.max()
            max_adverse = adverse_moves.max()

            # Ensure values are non-negative (can be negative if price never moved against pattern)
            snapshot.max_favorable_move = max(0.0, max_favorable)
            snapshot.max_adverse_move = max(0.0, max_adverse)

            cd_range = abs(snapshot.d_price - snapshot.c_price)
            type1_threshold = cd_range * self.TYPE1_RETRACE_MIN
            if max_favorable >= type1_threshold:
                if snapshot.is_bullish:
                    crossed = after_d[high_col] >= snapshot.d_price + type1_threshold
                else:
                    crossed = after_d[low_col] <= snapshot.d_price - type1_threshold
                if not snapshot.type1_date and crossed.any():
                    snapshot.type1_date = pd.Timestamp(
                        crossed[crossed].index[0]
                    ).isoformat()
                if snapshot.reaction_type != ReactionType.TYPE_2.value:
                    snapshot.reaction_type = ReactionType.TYPE_1.value

            # Detect the ordered Type 2 sequence before assigning the final state.
            terminal_matches = price_data.index.get_indexer([d_date], method='nearest')
            terminal_bar_idx = int(terminal_matches[0])
            type2 = detect_ordered_type2(
                price_data,
                terminal_bar_idx=terminal_bar_idx,
                is_bullish=snapshot.is_bullish,
                d_price=snapshot.d_price,
                c_price=snapshot.c_price,
                stop_loss=snapshot.stop_loss,
                max_bars=self.MAX_REACTION_BARS,
                retest_tolerance=self.TYPE2_RETEST_TOLERANCE,
                type1_retrace_min=self.TYPE1_RETRACE_MIN,
            )

            if type2.get('candidate'):
                snapshot.type2_retest_date = pd.Timestamp(type2['retest_date']).isoformat()

            if type2.get('detected'):
                snapshot.reaction_type = ReactionType.TYPE_2.value
                snapshot.type2_confirmation_date = pd.Timestamp(
                    type2['confirmation_date']
                ).isoformat()
                snapshot.type2_entry_price = type2['entry_price']
                snapshot.type2_stop_loss = type2['stop_loss']
                snapshot.type2_target_1 = type2['target_1']
                snapshot.type2_target_2 = type2['target_2']
                snapshot.type2_target_3 = type2['target_3']
                snapshot.type2_forward_return_pct = type2['forward_return_pct']
                snapshot.type2_stop_hit = type2['stop_hit']
                snapshot.type2_max_favorable_move = type2['max_favorable_move']
                snapshot.type2_max_adverse_move = type2['max_adverse_move']

            # Check for stop loss hit
            if snapshot.is_bullish:
                if after_d[low_col].min() <= snapshot.stop_loss:
                    snapshot.status = PatternStatus.STOPPED_OUT.value
                    if snapshot.reaction_type not in [
                        ReactionType.TYPE_1.value,
                        ReactionType.TYPE_2.value,
                    ]:
                        snapshot.reaction_type = ReactionType.FAILED.value
                    return
            else:
                if after_d[high_col].max() >= snapshot.stop_loss:
                    snapshot.status = PatternStatus.STOPPED_OUT.value
                    if snapshot.reaction_type not in [
                        ReactionType.TYPE_1.value,
                        ReactionType.TYPE_2.value,
                    ]:
                        snapshot.reaction_type = ReactionType.FAILED.value
                    return

            # Check for targets hit
            targets_hit = []
            if snapshot.is_bullish:
                if snapshot.target_1 is not None and after_d[high_col].max() >= snapshot.target_1:
                    targets_hit.append(1)
                if snapshot.target_2 is not None and after_d[high_col].max() >= snapshot.target_2:
                    targets_hit.append(2)
                if snapshot.target_3 is not None and after_d[high_col].max() >= snapshot.target_3:
                    targets_hit.append(3)
            else:
                if snapshot.target_1 is not None and after_d[low_col].min() <= snapshot.target_1:
                    targets_hit.append(1)
                if snapshot.target_2 is not None and after_d[low_col].min() <= snapshot.target_2:
                    targets_hit.append(2)
                if snapshot.target_3 is not None and after_d[low_col].min() <= snapshot.target_3:
                    targets_hit.append(3)

            snapshot.targets_hit = targets_hit

            if len(targets_hit) > 0:
                snapshot.status = PatternStatus.TARGET_HIT.value
                return

            if type2.get('detected'):
                snapshot.status = PatternStatus.CONFIRMED_TYPE2.value
                logger.info("Type 2 Reaction detected for %s: ordered retest and reversal", snapshot.pattern_id)
                return

            if type2.get('candidate'):
                snapshot.reaction_type = ReactionType.TYPE_2_CANDIDATE.value
                snapshot.status = PatternStatus.TYPE2_CANDIDATE.value
                return

            if snapshot.reaction_type == ReactionType.TYPE_1.value:
                snapshot.status = PatternStatus.CONFIRMED_TYPE1.value
                logger.info("Type 1 Reaction detected for %s: %.2f move from D", snapshot.pattern_id, max_favorable)
                return

            if len(after_d) > self.MAX_REACTION_BARS:
                snapshot.status = PatternStatus.EXPIRED.value
                return

            # No clear reaction yet
            snapshot.status = PatternStatus.AWAITING_CONFIRMATION.value

        except (KeyError, ValueError, IndexError) as e:
            # Expected errors from data access/calculation
            logger.debug("Data error analyzing reaction for %s: %s", snapshot.pattern_id, e)
            snapshot.status = PatternStatus.AWAITING_CONFIRMATION.value
        except Exception as e:
            # Unexpected errors
            logger.error("Unexpected error analyzing reaction for %s: %s", snapshot.pattern_id, e, exc_info=True)
            snapshot.status = PatternStatus.AWAITING_CONFIRMATION.value

    def _check_expired_patterns(self, current_date: datetime, results: Dict[str, List[PatternSnapshot]]) -> None:
        """Check for patterns that have expired (too old)"""
        expired_ids = []

        for pattern_id, snapshot in self.active_patterns.items():
            first_detected = datetime.fromisoformat(snapshot.first_detected)
            days_old = (current_date - first_detected).days

            expirable_statuses = {
                PatternStatus.FORMING.value,
            }
            if days_old > self.MAX_PATTERN_AGE_DAYS and snapshot.status in expirable_statuses:
                snapshot.status = PatternStatus.EXPIRED.value
                results['completed'].append(snapshot)
                self._archive_pattern(snapshot)
                expired_ids.append(pattern_id)
                logger.info("Pattern %s expired (%d days old)", pattern_id, days_old)

        # Remove expired patterns
        for pattern_id in expired_ids:
            del self.active_patterns[pattern_id]

    def get_active_patterns(self, ticker: Optional[str] = None,
                           status: Optional[PatternStatus] = None) -> List[PatternSnapshot]:
        """
        Get active patterns, optionally filtered by ticker and/or status.

        Args:
            ticker: Filter by ticker (None = all tickers)
            status: Filter by status (None = all statuses)

        Returns:
            List of PatternSnapshot objects
        """
        patterns = list(self.active_patterns.values())

        if ticker:
            patterns = [p for p in patterns if p.ticker == ticker]

        if status:
            patterns = [p for p in patterns if p.status == status.value]

        return patterns

    def get_summary(self) -> Dict[str, Any]:
        """Get summary statistics of tracked patterns"""
        summary: Dict[str, Any] = {
            'total_active': len(self.active_patterns),
            'by_status': {},
            'by_ticker': {},
            'confirmed_count': 0,
            'awaiting_confirmation': 0
        }

        for snapshot in self.active_patterns.values():
            # Count by status
            status = snapshot.status
            by_status: Dict[str, int] = summary['by_status']
            by_status[status] = by_status.get(status, 0) + 1

            # Count by ticker
            ticker = snapshot.ticker
            by_ticker: Dict[str, int] = summary['by_ticker']
            by_ticker[ticker] = by_ticker.get(ticker, 0) + 1

            # Special counts
            if status in [PatternStatus.CONFIRMED_TYPE1.value, PatternStatus.CONFIRMED_TYPE2.value]:
                summary['confirmed_count'] = summary['confirmed_count'] + 1  # type: ignore
            elif status in [
                PatternStatus.AWAITING_CONFIRMATION.value,
                PatternStatus.TYPE2_CANDIDATE.value,
            ]:
                summary['awaiting_confirmation'] = summary['awaiting_confirmation'] + 1  # type: ignore

        return summary
