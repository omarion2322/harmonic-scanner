# Trading Strategy Snapshot — 2026-09-13

**Price data through:** 2026-09-11 close  
**Review target:** 2026-11-13  
**Purpose:** Preserve the current portfolio results, observations, and proposed
rules before future outcomes are known.

## Method

- Combined `paper_trades_daily.json` and `paper_trades.json`.
- Removed duplicate tickers and kept the earliest detected trade.
- Original records: 137.
- Unique tickers: 122.
- Entry assumption: invest $1,000 at the next market open after
  `detected_date`.
- Original stops and 20% / 30% / 50% target allocations were retained.
- Same-bar target and stop events are resolved conservatively with the stop
  first.
- Results exclude commissions, spread, slippage, borrow fees, dividends, and
  taxes.
- The stated SPY return of approximately 3.1% is supplied by the user and is
  not independently calculated in this snapshot.

## Portfolio result

| Metric | Result |
|---|---:|
| Unique tickers | 122 |
| Entered trades | 121 |
| Pending next-open entry | 1 |
| Open trades | 90 |
| Closed trades | 31 |
| Capital allocated | $121,000 |
| Realized P&L | -$1,972.95 (-1.63%) |
| Unrealized P&L | +$6,631.26 (+5.48%) |
| Total P&L | +$4,658.31 (+3.85%) |
| User-supplied SPY comparison | approximately +3.1% |
| Apparent excess over SPY | approximately +0.75 percentage points |

The portfolio is only slightly ahead of SPY, before trading costs. All net
profit is unrealized; realized P&L is negative.

## Current profitable and losing groups

- 61 trades currently have positive total P&L.
- 55 trades currently have negative total P&L or hit their stop.
- 5 trades are flat.
- 27 trades hit their stop.

### Traits seen more often in profitable trades

| Trait | Profitable trades | Losing/stopped trades |
|---|---:|---:|
| Next-open entry within 5% of planned entry | 75.4% | 45.5% |
| Actual stop distance no more than 20% | 83.6% | 58.2% |
| Bat, Butterfly, Shark, or 5-0 | 80.3% | 60.0% |
| Gartley or Deep Crab | 19.7% | 38.2% |
| Planned T1 between 2R and 5R | 77.0% | 50.9% |

The clearest difference is the distance between the planned entry and the next
market open. Trades opened near the planned reversal zone performed much
better. Pattern type and stop distance may help, but their evidence is weaker.

### Pattern results

| Pattern | Trades | Profitable | Profit rate | Average P&L per $1,000 | Stops |
|---|---:|---:|---:|---:|---:|
| Butterfly | 29 | 17 | 58.6% | +$54.40 | 3 |
| Shark | 17 | 10 | 58.8% | +$54.20 | 4 |
| Bat | 20 | 11 | 55.0% | +$62.90 | 5 |
| 5-0 | 20 | 11 | 55.0% | +$34.00 | 4 |
| Gartley | 23 | 8 | 34.8% | +$44.40 | 6 |
| Deep Crab | 11 | 4 | 36.4% | -$61.90 | 4 |
| Crab | 1 | 0 | 0.0% | -$114.90 | 1 |

Gartley has a low win rate but positive average P&L because a small number of
large open winners dominate its result. Deep Crab is the only repeated pattern
with negative average P&L. These are hypotheses, not statistically proven
pattern bans.

## Is the current profit-taking plan reasonable?

**No, not for harvesting profits consistently on the daily timeframe.**

| Target metric | Result |
|---|---:|
| Median T1 distance | 42.9% from actual entry |
| Median T1 distance in risk units | 2.37R |
| Trades reaching T1 | 30 / 121 (24.8%) |
| Trades reaching T2 | 11 / 121 (9.1%) |
| Trades reaching T3 | 4 / 121 (3.3%) |

The four apparent T3 completions include trades whose next-open price was
already above all planned targets, so they do not demonstrate useful target
quality.

For trades entered within 5% of the plan:

- Only 18/71 reached T1.
- Only 4/71 reached T2.
- None reached T3.
- 30 of the 46 profitable trades had not reached even T1.

Therefore, most profitable trades are producing no realized profit. The current
targets are useful as distant objectives, but they are too far away to be the
only profit-taking levels.

## Candidate selection hypothesis

The following rule reduced the historical set from 121 trades to 44:

1. Daily timeframe only.
2. Pattern is Bat, Butterfly, Shark, or 5-0.
3. Enter at the next market open only when it is within 5% of the planned
   entry.
4. Keep only the earliest active trade per ticker.

Historical result for this selected group:

| Metric | Result |
|---|---:|
| Trades | 44 |
| Profitable | 32 |
| Profit rate | 72.7% |
| Stop rate | 11.4% |
| Total P&L at $1,000 per trade | +$4,835.82 |
| Average P&L per trade | +$109.91 (+10.99%) |

A stricter 2% entry rule produced 13 trades, a 92.3% profitable rate, no stops,
and +$1,071.25 total P&L. That sample is too small to trust and is recorded only
as a hypothesis.

## Proposed manageable strategy

1. Keep at most 10 active positions.
2. Never open a second position in an already-active ticker.
3. Prefer daily Bat, Butterfly, Shark, and 5-0 patterns.
4. Enter on the next market open only if the opening price remains within 2%
   of the planned entry. Record a separate 5% comparison group.
5. Reject trades whose actual entry creates more than 20% stop risk.
6. Take 50% profit at 1R, 30% at 2R, and 20% at 3R.
7. Move the remaining stop to entry after 1R is confirmed.
8. Keep the original structure targets as reference objectives, not as the only
   exits.
9. Rank eligible trades by:
   - confirmed Type 1 reaction;
   - smallest distance from planned entry;
   - valid and liquid market data;
   - no conflicting active thesis;
   - pattern preference: Bat, Butterfly, Shark, then 5-0.

## Type 2 reaction hypothesis

The current data does **not** show that Type 2 reactions are more profitable
than Type 1 reactions.

| Tracker sample | Patterns | Average favorable excursion | Median favorable excursion | Average adverse excursion |
|---|---:|---:|---:|---:|
| Type 1 | 521 | 1.26R | 0.75R | 0.51R |
| Type 2 | 14 | 0.56R | 0.54R | 0.39R |

Type 2 had favorable excursion greater than adverse excursion more often
(78.6% versus 70.8%), but its favorable move was smaller. This is weak
evidence because there are only 14 Type 2 records and the tracker does not
store unbiased realized outcomes.

Scott Carney's Type 2 concept is event-driven: an initial reaction occurs,
price retraces or retests the Potential Reversal Zone or key structure, and a
second reversal is confirmed. It should not be defined only by pattern age.
The available nonzero Type 2 timing records averaged 19 trading days and had a
median of 23 trading days. The detector already monitors up to 30 bars.

The daily `MAX_DAYS_SINCE_PATTERN` value of 7 was suitable only for a fresh
initial entry. It was too short for Type 2 monitoring. Before the change,
reaction detection ran only after a pattern passed the signal-age filter, so
an expired HOLD could not display report-level Type 2 details.

Two pre-change scans on 2026-09-13 demonstrated the conflict:

| Ticker | Pattern completed | Age | Tracker state | Scanner result | Excursion so far |
|---|---|---:|---|---|---:|
| NTGR | 2026-08-24 | 20 days | Confirmed bullish Type 2 | HOLD: expired, maximum 7 days | +0.67R favorable, 0R adverse |
| ZO=F | 2026-09-01 | 12 days | Confirmed bearish Type 2 | HOLD: expired, maximum 7 days | +0.25R favorable, -0.48R adverse |

NTGR is a constructive example; ZO=F shows that Type 2 classification alone is
not enough to guarantee a profitable trade. Neither appeared among the first
100 HOLD records displayed in the full daily report, which truncates the other
1,867 HOLD records. No displayed expired HOLD in the available full reports
was in the useful 8-30 day monitoring window.

## Type 2 implementation baseline

**Implemented:** 2026-09-13

**Snapshot algorithm label:** `type2_ordered_v1`

**First forward reports:** The next daily and weekly reports generated and
pushed after this implementation.

The following changes are now implemented:

1. Keep `MAX_DAYS_TO_INITIAL_ENTRY = 7` for fresh direct entries.
2. Monitor completed patterns independently for up to
   `MAX_BARS_TO_MONITOR_REACTION = 30` bars.
3. Run reaction analysis before applying the fresh-entry age filter.
4. Report `TYPE_2_CANDIDATE` and `TYPE_2_CONFIRMED` separately from ordinary
   HOLD signals.
5. Require these events in order:
   - an initial move of at least 19.1% of the CD leg away from D;
   - a later return to the PRZ, using a 2% retest tolerance;
   - a still-later second move of at least 19.1% of CD.
6. Use the confirmation bar close as the reference Type 2 entry.
7. Set the new stop 2% beyond the retest price.
8. Calculate new Type 2 targets at 1R, 2R, and 3R.
9. Emit an actionable Type 2 BUY or SELL only when:
   - confirmation occurred no more than one bar ago;
   - the new stop has not been hit;
   - entry-to-stop risk is within the configured maximum.
10. Use the same ordered Type 2 detector in the scanner and persistent tracker.
11. Continue monitoring completed tracker patterns even when they are not
    returned again by the pattern detector.
12. Persist the Type 1 date, retest date, confirmation date, entry, stop,
    targets, forward return, favorable/adverse excursion, and stop status.

The implementation changed:

- `src/reaction_detector.py`
- `src/pattern_tracker.py`
- `src/harmonic_scanner.py`
- `src/pattern_detector.py`
- `src/utils.py`
- `src/config/config.py`
- `src/config/config_timeframes.py`
- `src/config/settings.py`
- `scripts/scan_stock.py`

### Immediate post-change examples

The same patterns were replayed after implementing the ordered detector:

| Ticker | New classification | Result |
|---|---|---|
| NTGR | Type 2 confirmed and actionable | Retest 2026-09-01; confirmation 2026-09-11; reference entry $22.23; stop $20.04; targets $24.42 / $26.61 / $28.80 |
| ZO=F | Type 2 candidate | Initial reaction and retest found, but no second reversal confirmation; remains HOLD |

This is the intended distinction: NTGR completed the full sequence, while
ZO=F did not. Neither example proves future profitability.

### Important historical-data boundary

All Type 2 labels created before `type2_ordered_v1` are **legacy labels**. The
old detector could classify Type 2 from a B-level or 88.6% CD break without an
ordered retest. Do not combine those records with the new forward sample.

The first daily and weekly reports generated after this implementation define
the new forward cohort. Preserve those report files unchanged. If the rules
change again, assign a new algorithm label and begin a separate cohort.

### Forward audit procedure

For every signal in the new daily and weekly reports:

1. Save the report date, ticker, timeframe, pattern ID, direction, pattern
   family, grade, and algorithm label.
2. Save the D date, Type 1 date, retest date, and Type 2 confirmation date.
3. Save the reference entry, retest-derived stop, and 1R/2R/3R targets.
4. Use the next market open as the simulated fill. The confirmation close is
   only the reference entry because it is not executable after an end-of-day
   scan.
5. Record the difference between the next open and the reference entry.
6. Skip the trade if that difference violates the configured entry or risk
   limits.
7. Track the original initial-entry strategy and the new Type 2 strategy as
   separate groups.
8. Limit the portfolio simulation to 10 active positions and one active
   position per ticker.
9. Record realized P&L, unrealized P&L, MFE, MAE, stop hits, and 1R/2R/3R hits.
10. Compare each trade with SPY over exactly the same entry and exit dates.

Review every cohort after 20 and 40 trading sessions. Do not judge Type 2 by
win rate alone. Compare expectancy in R, profit factor, stop rate, maximum
drawdown, return after costs, SPY-relative return, and capital utilization.
Treat results as preliminary until at least 30 ordered Type 2 confirmations
exist; 50 or more is preferable.

## Forward cohort from the 2026-09-13 report

Both signals were generated on Sunday and are pending the next market open.
They must be skipped if the opening price is outside the stated entry zone.

| Rank | Ticker | Pattern | Plan | Proposed 1R / 2R / 3R | Reason |
|---|---|---|---|---|---|
| 1 | SEVN | Bullish Butterfly, B- | Entry $7.31, stop $6.21 | $8.41 / $9.51 / $10.61 | Already showed a Type 1 reaction and is currently inside the PRZ |
| 2 | XNDU | Bullish Butterfly, B+ | Entry $8.60, stop $7.31 | $9.89 / $11.18 / $12.47 | Inside the PRZ, but no reaction yet and its ETF trend is down |

The original T1 is approximately 3.15R for both trades. The proposed 1R scale
would realize profit much earlier.

## Claims to test at the next review

1. Entry within 2% of plan has higher expectancy and a lower stop rate than
   entry 2–5% away.
2. Bat, Butterfly, Shark, and 5-0 outperform Gartley and Deep Crab.
3. A 1R / 2R / 3R exit plan realizes more profit and produces fewer full losses
   than the original targets.
4. Moving the stop to entry after 1R reduces losses without materially reducing
   average return.
5. Limiting the portfolio to the 10 highest-ranked active trades beats the
   equal-weight SPY benchmark.
6. Ordered and newly confirmed Type 2 entries monitored for up to 30 bars have
   positive expectancy after costs.
7. Type 2 confirmation adds value beyond the entry-distance, stop-risk, and
   pattern-family filters.

Do not declare these claims confirmed until the forward cohort has enough
observations. Review both 20-session and 40-session results, and compare the
original plan with the proposed plan on exactly the same fills.
