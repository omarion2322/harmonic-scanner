"""Descriptive regular divergence at initial D or the ordered Type 2 retest."""

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any, Optional

import numpy as np
import pandas as pd


ALGORITHM_VERSION = "initial-d-regular-v2"
TYPE2_ALGORITHM_VERSION = "d-to-type2-regular-v2"
POINT_MEASUREMENT_VERSION = "exact-point-rsi14-macd12-26-v1"
MEASURED_STATUSES = frozenset({"both", "rsi_only", "macd_only", "neither"})


@dataclass(frozen=True)
class DivergenceConfig:
    pivot_left: int = 2
    pivot_right: int = 2
    min_spacing: int = 5
    max_spacing: int = 60
    d_window: int = 2
    prz_distance_atr: float = 0.5
    min_price_atr: float = 0.1
    min_rsi_points: float = 3.0
    min_macd_atr: float = 0.05
    include_histogram: bool = False

    def __post_init__(self):
        for name in ("pivot_left", "pivot_right", "min_spacing", "max_spacing", "d_window"):
            value = getattr(self, name)
            minimum = 0 if name == "d_window" else 1
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                raise ValueError(f"{name} must be an integer >= {minimum}")
        if self.max_spacing < self.min_spacing:
            raise ValueError("max_spacing must be >= min_spacing")
        for name in ("prz_distance_atr", "min_price_atr", "min_rsi_points", "min_macd_atr"):
            value = getattr(self, name)
            if not np.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")

    @classmethod
    def from_settings(cls, settings: Any) -> "DivergenceConfig":
        return cls(**getattr(settings, "DIVERGENCE_SETTINGS", {}))

    @property
    def evaluation_id(self) -> str:
        return self.evaluation_id_for("initial_d")

    def evaluation_id_for(self, context: str) -> str:
        version = TYPE2_ALGORITHM_VERSION if context == "type2_retest" else ALGORITHM_VERSION
        return hashlib.sha256(
            json.dumps([version, asdict(self)], sort_keys=True).encode()
        ).hexdigest()


def utc_timestamp(value: Any = None) -> pd.Timestamp:
    timestamp = pd.Timestamp.now(tz="UTC") if value is None else pd.Timestamp(value)
    return timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")


def candle_availability(index: pd.DatetimeIndex, interval: str) -> pd.DatetimeIndex:
    """Conservative bar-end timestamps, not exchange-session close estimates."""
    match = re.fullmatch(r"([1-9]\d*)(m|h|d|wk|mo)", interval)
    if not match:
        raise ValueError(f"Unsupported candle interval: {interval}")
    count, unit = int(match[1]), match[2]
    if unit == "mo":
        ends = index + pd.DateOffset(months=count)
    else:
        ends = index + pd.Timedelta(**{
            {"m": "minutes", "h": "hours", "d": "days", "wk": "weeks"}[unit]: count
        })
    return pd.DatetimeIndex([utc_timestamp(end) for end in ends], tz="UTC")


def closed_retest_date(retest_date: Any, interval: str, as_of: Any = None) -> Optional[str]:
    """Do not select a retest discovered only in the still-open candle."""
    if not retest_date:
        return None
    date = utc_timestamp(retest_date)
    try:
        end = candle_availability(pd.DatetimeIndex([date]), interval)[0]
    except ValueError:
        return None
    return date.isoformat() if end <= utc_timestamp(as_of) else None


def _seeded_average(values: np.ndarray, period: int, alpha: float) -> np.ndarray:
    result = np.full(len(values), np.nan)
    valid = np.flatnonzero(np.isfinite(values))
    if not len(valid):
        return result
    start = int(valid[0])
    seed_end = start + period
    if seed_end > len(values):
        return result
    result[seed_end - 1] = np.mean(values[start:seed_end])
    for pos in range(seed_end, len(values)):
        result[pos] = alpha * values[pos] + (1 - alpha) * result[pos - 1]
    return result


def calculate_indicators(df: pd.DataFrame, include_histogram: bool = False) -> pd.DataFrame:
    """Wilder RSI/ATR14; SMA-seeded EMA12-EMA26, optionally EMA9 histogram."""
    close = df["close"].to_numpy(dtype=float)
    delta = np.diff(close, prepend=np.nan)
    gain = _seeded_average(np.maximum(delta, 0), 14, 1 / 14)
    loss = _seeded_average(np.maximum(-delta, 0), 14, 1 / 14)
    with np.errstate(divide="ignore", invalid="ignore"):
        rsi = 100 - 100 / (1 + gain / loss)
    rsi[(loss == 0) & (gain > 0)] = 100
    rsi[(loss == 0) & (gain == 0)] = 50
    previous = df["close"].shift()
    true_range = pd.concat([
        df["high"] - df["low"],
        (df["high"] - previous).abs(),
        (df["low"] - previous).abs(),
    ], axis=1).max(axis=1).to_numpy(dtype=float)
    macd = (
        _seeded_average(close, 12, 2 / 13)
        - _seeded_average(close, 26, 2 / 27)
    )
    result = pd.DataFrame({
        "rsi": rsi,
        "macd": macd,
        "atr": _seeded_average(true_range, 14, 1 / 14),
    }, index=df.index)
    if include_histogram:
        result["histogram"] = macd - _seeded_average(macd, 9, 2 / 10)
    return result


def pattern_anchor(pattern: Any, retest_date: Any = None) -> dict:
    anchor = {
        "d_date": pd.Timestamp(pattern.d.date).isoformat(),
        "d_price": float(pattern.d.price),
        "prz_low": float(getattr(pattern, "d_point_range_min", 0) or pattern.d.price),
        "prz_high": float(getattr(pattern, "d_point_range_max", 0) or pattern.d.price),
        "is_bullish": bool(pattern.is_bullish),
    }
    if retest_date is not None:
        anchor["retest_date"] = utc_timestamp(retest_date).isoformat()
    return anchor


def _valid_ohlc(data: pd.DataFrame) -> bool:
    values = data.to_numpy()
    return bool(
        np.isfinite(values).all() and (values > 0).all()
        and (data["high"] >= data["low"]).all()
        and (data["close"] <= data["high"]).all()
        and (data["close"] >= data["low"]).all()
    )


def point_reading_value(evidence: Optional[dict], indicator: str) -> Optional[float]:
    """Display only the chosen exact candle, including provably exact legacy pivots."""
    if not evidence:
        return None
    role = "retest" if evidence.get("context") == "type2_retest" else "d"
    if "point_readings" in evidence:
        reading = evidence["point_readings"].get(role) or {}
        return reading.get(indicator, {}).get("value")
    date = evidence.get("anchor", {}).get("retest_date" if role == "retest" else "d_date")
    pivots = evidence.get("pivots", [])
    if date and pivots and utc_timestamp(pivots[-1]["date"]) == utc_timestamp(date):
        return evidence.get(indicator, {}).get("second")
    return None


class DivergenceDetector:
    def __init__(self, config: Optional[DivergenceConfig] = None):
        self.config = config or DivergenceConfig()

    def measure_point(self, df: pd.DataFrame, date: Any, interval: str = "1d",
                      as_of: Any = None) -> dict:
        """Read a closed exact candle independently of any divergence decision."""
        now, date = utc_timestamp(as_of), utc_timestamp(date)
        result = {
            "measurement_version": POINT_MEASUREMENT_VERSION,
            "date": date.isoformat(), "interval": interval, "available_at": None,
            "rsi": {"value": None, "reason": "not_evaluated", "observed_at": None},
            "macd": {"value": None, "reason": "not_evaluated", "observed_at": None},
        }

        def unavailable(reason: str) -> dict:
            for name in ("rsi", "macd"):
                result[name]["reason"] = reason
            return result

        if not isinstance(df.index, pd.DatetimeIndex) or df.index.hasnans:
            return unavailable("invalid_datetime_index")
        if not df.index.is_unique or not df.index.is_monotonic_increasing:
            return unavailable("unordered_or_duplicate_candles")
        if not {"high", "low", "close"}.issubset(df.columns):
            return unavailable("missing_ohlc")
        try:
            ends = candle_availability(df.index, interval)
            point_end = candle_availability(pd.DatetimeIndex([date]), interval)[0]
        except ValueError:
            return unavailable("unsupported_interval")
        if point_end > now:
            return unavailable("point_candle_not_closed")
        timestamps = pd.DatetimeIndex([utc_timestamp(value) for value in df.index])
        matches = np.flatnonzero(timestamps == date)
        if not len(matches):
            return unavailable("point_candle_missing")
        pos = int(matches[0])
        data = df.iloc[:pos + 1][["high", "low", "close"]]
        # Every input bar, not just the target, must be closed.
        if (ends[:pos + 1] > now).any():
            return unavailable("input_candle_not_closed")
        try:
            data = data.astype(float)
        except (TypeError, ValueError):
            return unavailable("invalid_ohlc")
        if not _valid_ohlc(data):
            return unavailable("invalid_ohlc")
        result["available_at"] = point_end.isoformat()
        provenance = {
            "data_start": data.index[0].isoformat(), "data_end": data.index[-1].isoformat(),
            "data_sha256": hashlib.sha256(
                pd.util.hash_pandas_object(data, index=True).values.tobytes()
            ).hexdigest(),
        }
        values = calculate_indicators(data)
        for name in ("rsi", "macd"):
            value = values[name].iloc[-1]
            available = bool(np.isfinite(value))
            result[name] = {
                "value": float(value) if available else None,
                "point_date": date.isoformat(),
                "reason": "measured" if available else "indicator_warmup",
                "observed_at": now.isoformat() if available else None,
                "available_at": point_end.isoformat() if available else None,
                **provenance,
            }
        return result

    def detect(self, df: pd.DataFrame, anchor: dict, interval: str = "1d",
               as_of: Any = None) -> dict:
        cfg = self.config
        now = utc_timestamp(as_of)
        type2 = anchor.get("retest_date") is not None
        result = {
            "algorithm_version": TYPE2_ALGORITHM_VERSION if type2 else ALGORITHM_VERSION,
            "evaluation_id": cfg.evaluation_id_for("type2_retest" if type2 else "initial_d"),
            "config": asdict(cfg),
            "context": "type2_retest" if type2 else "initial_d",
            "source": "Type 2 reaction area" if type2 else "D point",
            "interval": interval,
            "anchor": dict(anchor),
            "status": "insufficient_data",
            "reason": "",
            "rsi": {"confirmed": None},
            "macd": {"confirmed": None},
            "histogram": None,
            "pivots": [],
            "available_at": None,
            "evaluated_at": now.isoformat(),
            "closed_through": None,
            "price_delta_atr": None,
            "atr_reference": None,
            "data_start": None,
            "data_end": None,
            "data_sha256": None,
            "closure_policy": "bar_start_plus_interval; naive timestamps treated as UTC",
            "point_readings": {
                "d": self.measure_point(df, anchor["d_date"], interval, now),
                "retest": self.measure_point(df, anchor["retest_date"], interval, now) if type2 else None,
            },
        }
        result["initial_d_reading"] = result["point_readings"]["d"]

        def unavailable(reason: str, status: str = "insufficient_data") -> dict:
            result.update(reason=reason, status=status)
            return result

        if not isinstance(df.index, pd.DatetimeIndex) or df.index.hasnans:
            return unavailable("invalid_datetime_index")
        if not df.index.is_unique or not df.index.is_monotonic_increasing:
            return unavailable("unordered_or_duplicate_candles")
        if not {"high", "low", "close"}.issubset(df.columns):
            return unavailable("missing_ohlc")
        try:
            ends = candle_availability(df.index, interval)
        except ValueError:
            return unavailable("unsupported_interval")
        closed = ends <= now
        data = df.loc[closed, ["high", "low", "close"]].copy()
        ends = ends[closed]
        if data.empty:
            return unavailable("no_closed_candles")
        result["closed_through"] = ends[-1].isoformat()
        timestamps = pd.DatetimeIndex([utc_timestamp(date) for date in data.index])
        d_date = utc_timestamp(anchor["d_date"])
        matches = np.flatnonzero(timestamps == d_date)
        if not len(matches) and not type2:
            return unavailable(
                "d_candle_not_closed" if d_date >= timestamps[-1] else "d_candle_missing",
                "developing" if d_date >= timestamps[-1] else "insufficient_data",
            )
        d_pos = int(matches[0]) if len(matches) else None
        if type2:
            retest_date = utc_timestamp(anchor["retest_date"])
            matches = np.flatnonzero(timestamps == retest_date)
            if not len(matches):
                pending = retest_date >= timestamps[-1]
                return unavailable(
                    "retest_candle_not_closed" if pending else "retest_candle_missing",
                    "developing" if pending else "insufficient_data",
                )
            second = int(matches[0])
            if retest_date <= d_date:
                return unavailable("retest_not_after_d")
            horizon = second + cfg.pivot_right
        else:
            horizon = d_pos + cfg.d_window + cfg.pivot_right
        if not type2 and horizon >= len(data):
            return unavailable("awaiting_d_window_and_right_confirmation", "developing")

        # Freeze the input horizon: later candles cannot influence pivot selection or seeds.
        data = data.iloc[:horizon + 1]
        ends = ends[:horizon + 1]
        try:
            data = data.astype(float)
        except (ValueError, TypeError):
            return unavailable("invalid_ohlc")
        if not _valid_ohlc(data):
            return unavailable("invalid_ohlc")
        result.update(
            data_start=data.index[0].isoformat(),
            data_end=data.index[-1].isoformat(),
            data_sha256=hashlib.sha256(
                pd.util.hash_pandas_object(data, index=True).values.tobytes()
            ).hexdigest(),
        )
        indicators = calculate_indicators(data, cfg.include_histogram)
        bullish = anchor["is_bullish"]
        prices = data["low" if bullish else "high"].to_numpy()

        def number(value):
            return float(value) if np.isfinite(value) else None

        if type2:
            # Read the reached retest immediately, but never infer confirmation early.
            result["measurement_date"] = data.index[second].isoformat()
            for name in ("rsi", "macd"):
                result[name].update(
                    first=number(indicators[name].iloc[d_pos]) if d_pos is not None else None,
                    second=number(indicators[name].iloc[second]),
                )
            if horizon >= len(data):
                return unavailable("awaiting_retest_right_confirmation", "developing")
            if d_pos is None:
                return unavailable("d_candle_missing")
        pivots = []
        for pos in range(cfg.pivot_left, len(data) - cfg.pivot_right):
            neighbours = np.concatenate((
                prices[pos - cfg.pivot_left:pos], prices[pos + 1:pos + cfg.pivot_right + 1]
            ))
            extreme = (prices[pos] < neighbours).all() if bullish else (prices[pos] > neighbours).all()
            if extreme:
                pivots.append(pos)
        if type2:
            first = d_pos
            if second not in pivots:
                return unavailable("retest_not_confirmed_price_pivot")
            if first not in pivots:
                return unavailable("d_not_confirmed_price_pivot")
            if not cfg.min_spacing <= second - first <= cfg.max_spacing:
                return unavailable("d_to_retest_outside_spacing_window")
        else:
            near_d = [pos for pos in pivots if abs(pos - d_pos) <= cfg.d_window]
            if not near_d:
                return unavailable("no_confirmed_price_pivot_near_d")
            # Distance to D, then earlier date; never rank by oscillator strength.
            second = min(near_d, key=lambda pos: (abs(pos - d_pos), pos))
            preceding = [pos for pos in pivots if cfg.min_spacing <= second - pos <= cfg.max_spacing]
            if not preceding:
                return unavailable("no_preceding_pivot_in_spacing_window")
            first = max(preceding)

        for pos in (first, second):
            result["pivots"].append({
                "date": data.index[pos].isoformat(),
                "confirmed_at": ends[pos + cfg.pivot_right].isoformat(),
                "price": float(prices[pos]),
                "rsi": number(indicators["rsi"].iloc[pos]),
                "macd": number(indicators["macd"].iloc[pos]),
                "histogram": number(indicators["histogram"].iloc[pos]) if cfg.include_histogram else None,
            })
        result["spacing_bars"] = second - first
        atr = number(indicators["atr"].iloc[second])
        result["atr_reference"] = atr
        if atr is None or atr <= 0:
            return unavailable("atr_unavailable_or_zero")
        low, high = sorted((anchor["prz_low"], anchor["prz_high"]))
        distance = max(low - prices[second], prices[second] - high, 0) / atr
        result["prz_distance_atr"] = float(distance)
        # Ordered Type 2 already establishes area membership by candle overlap.
        if not type2 and distance > cfg.prz_distance_atr:
            return unavailable("second_pivot_outside_prz_tolerance")
        direction = 1 if bullish else -1
        price_delta = direction * (prices[first] - prices[second])
        result["price_delta"] = float(price_delta)
        result["price_delta_atr"] = float(price_delta / atr)
        price_qualifies = price_delta > 0 and price_delta / atr >= cfg.min_price_atr
        result["price_qualifies"] = bool(price_qualifies)
        for name, threshold, divisor in (
            ("rsi", cfg.min_rsi_points, 1),
            ("macd", cfg.min_macd_atr, atr),
        ):
            before = result["pivots"][0][name]
            after = result["pivots"][1][name]
            delta = direction * (after - before) if before is not None and after is not None else None
            result[name] = {
                "first": before, "second": after, "delta": delta,
                "normalized_delta": delta / divisor if delta is not None else None,
                "confirmed": bool(price_qualifies and delta > 0 and delta / divisor >= threshold)
                if delta is not None else None,
            }
        if cfg.include_histogram:
            before, after = (pivot["histogram"] for pivot in result["pivots"])
            result["histogram"] = {
                "first": before, "second": after,
                "delta_atr": direction * (after - before) / atr
                if before is not None and after is not None else None,
                "role": "metadata_only_not_confirmation",
            }
        if any(result[name]["confirmed"] is None for name in ("rsi", "macd")):
            return unavailable("indicator_warmup")
        rsi, macd = (result[name]["confirmed"] for name in ("rsi", "macd"))
        result.update(
            status="both" if rsi and macd else "rsi_only" if rsi else "macd_only" if macd else "neither",
            reason="regular_divergence_measured",
            available_at=ends[horizon].isoformat(),
        )
        return result


def format_divergence(evidence: Optional[dict]) -> str:
    """Audit text separates exact point observations from pivot-pair decisions."""
    if not evidence:
        return "Initial-D divergence (experimental): insufficient_data — not evaluated"
    title = "D-to-Type-2 divergence" if evidence.get("context") == "type2_retest" else "Initial-D divergence (experimental)"
    source = "Type 2 reaction area" if evidence.get("context") == "type2_retest" else "D point"
    lines = [f"{title}: {evidence['status']}", f"Source: {source}"]
    points = evidence.get("point_readings", {})
    initial = evidence.get("initial_d_reading") or points.get("d")
    readings = [("Initial D point readings", initial)]
    if evidence.get("context") == "type2_retest":
        event_d = points.get("d")
        if event_d and initial and event_d != initial:
            readings.append(("Reaction event D point readings", event_d))
        readings.append(("Type 2 retest point readings", points.get("retest")))
    for label, reading in readings:
        if not reading:
            lines.append(f"{label}: unavailable (legacy evaluation; exact candle not recorded)")
            continue
        lines.append(f"{label}: {reading['date']} | measurement {reading['measurement_version']}")
        for name, indicator in (("rsi", "RSI14"), ("macd", "MACD")):
            item = reading[name]
            value = item["value"]
            if value is None:
                lines.append(f"  {indicator}: N/A | {item['reason']}")
            else:
                lines.append(
                    f"  {indicator}: {value:.3f} | candle available: {item['available_at']} "
                    f"| first observed: {item['observed_at']}"
                )
                lines.append(
                    f"    Input: {item['data_start']} -> {item['data_end']} "
                    f"| SHA256: {item['data_sha256']}"
                )
    lines.append("Divergence comparison (confirmed price pivots, separate from exact point readings):")
    if evidence.get("context") == "type2_retest":
        lines.append(
            f"D baseline: {evidence['anchor']['d_date']} | "
            f"Retest candle: {evidence['anchor']['retest_date']}"
        )
    for key, label in (("rsi", "RSI14"), ("macd", "MACD line (12-26)")):
        item = evidence[key]
        state = "unavailable" if item["confirmed"] is None else "yes" if item["confirmed"] else "no"
        text = f"{label}: {state}"
        if item.get("first") is not None and item.get("second") is not None:
            text += f" | {item['first']:.3f} -> {item['second']:.3f}"
            if item.get("normalized_delta") is not None:
                text += f" | improvement {'points' if key == 'rsi' else '/ATR'} {item['normalized_delta']:+.3f}"
        lines.append(text)
    if evidence.get("pivots"):
        lines.append("Price pivots: " + " -> ".join(
            f"{p['date'][:10]} ({p['price']:.3f})" for p in evidence["pivots"]
        ))
    if evidence.get("available_at"):
        lines.append(f"Evidence available: {evidence['available_at']}")
    else:
        lines.append(f"Pending/unavailable: {evidence['reason']}")
    if evidence.get("persistence_error"):
        lines.append("Persistence unavailable: this observation is not stored.")
    return "\n".join(lines)
