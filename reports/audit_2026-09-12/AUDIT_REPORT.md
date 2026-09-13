# Harmonic Pattern Bot — Historical Audit (1d)

**As-of date:** 2026-09-12  
**Primary files (locked):**
1. `reports/2026-06-27/1d/tradingview_watchlist_2026-06-27_1d.txt`
2. `reports/2026-07-21/1d/tradingview_watchlist_2026-07-21_1d.txt`
3. `reports/2026-08-02/1d/tradingview_notes_2026-08-02_1d.txt`
4. `reports/2026-08-18/1d/tradingview_notes_2026-08-18_1d.txt`

Harmonic reports for the same dates were used only as *contemporaneous enrichment* (ratios, ETF trend, confluence). They did **not** replace or rewrite the four signal files. The 2026-06-27 harmonic report is effectively empty (1 HOLD) and was not substituted.

Machine-readable trades: `reports/audit_2026-09-12/primary_trades.csv`

---

## 0. Evaluation protocol (locked before outcomes)

Defined from code, then applied. Outcomes were not used to choose these rules.

| Rule | Setting |
|---|---|
| Canonical trade | First chronological appearance of a ticker |
| Report timing | Post-close; first bar = next session |
| Fill | Limit at plan entry; gap-through at Open; chase only if Open still inside ±2% PRZ |
| Fill window | 7 trading days (`MAX_DAYS_SINCE_PATTERN` for 1d) |
| Same-bar stop+target | `AMBIGUOUS` (excluded from primary R). Count in this sample: **0** |
| Management | 20% T1 / 30% T2 / 50% T3 (`POSITION_SIZE_*`) |
| Costs | 5 bps per side |
| Prices | Unadjusted daily OHLC (so report-time entries match) |
| Horizons | 20d, 40d, and full sample through 2026-09-12 (right-censored) |
| Walk-forward | Research = 2026-06-27 cohort; validate = 2026-07-21; test = 2026-08-02 + 2026-08-18 |

**Existing system (Phase 1)**

- Patterns actually present: Gartley, Bat, Butterfly, Crab, Deep Crab, Shark, 5-0. Cypher / Alternate Bat not in these four reports.
- Detection: pyharmonics peaks + Carney ratio bands, fib tolerance 5%, swing window 4, 1d.
- Grade: D 45% / B 35% / BC 20% + PRZ/time multipliers → A+…C-. Mapped C/C- = “Marginal / Scalp Only”.
- Filters already on: min long R/R 6, min short R/R 3, stop 8–15%, max pattern age, temporal-leg filters.
- Filters already **off**: RSI, volume, and the PRZ-still-valid check (commented out in `generate_signal`).
- TP strategy: MITCH (structure + scoring engine), not Scott IPO. Stops clamped to 8–15%.
- ETF confluence is reported but **not** required (most notes say NOT CONFIRMED).
- Type 1/2 reaction is monitored, not required for export.

---

## 1. Historical audit summary

| | Signals | Unique primary | Filled | No entry | Ambiguous |
|---|---:|---:|---:|---:|---:|
| All four reports | 153 | 139 | 83 | 56 | 0 |

Appearances by file: 2026-06-27 **48**, 2026-07-21 **50**, 2026-08-02 **41**, 2026-08-18 **14**.

Primary direction: 102 LONG / 37 SHORT. Grade mix: **102/139 are C-**. 12 tickers appeared more than once.

### Primary performance (filled trades only, mark-to-market through 2026-09-12)

R uses fill price vs stated stop as 1R, 20/30/50 scaling, 10 bps round-trip on closed slices, remainder marked at last close.

| Book | n filled | Win rate | Avg R | Med R | PF | Avg W | Avg L | Max DD R | MFE | MAE | Full win | Partial | Full loss | Open | No entry |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| FULL | 83 | 53.0% | 0.250 | 0.089 | 1.695 | 1.148 | -0.764 | -8.505 | 1.470 | 0.649 | 0 | 15 | 24 | 44 | 56 |
| 40d | 83 | 50.6% | 0.245 | 0.034 | 1.719 | 1.156 | -0.688 | -9.411 | 1.426 | 0.619 | 0 | 13 | 23 | 47 | 56 |
| 20d | 83 | 55.4% | 0.227 | 0.139 | 1.776 | 0.938 | -0.674 | -7.913 | 1.196 | 0.543 | 0 | 7 | 19 | 57 | 56 |
| LONG | 58 | 51.7% | 0.311 | 0.078 | 1.829 | 1.326 | -0.777 | -7.630 | 1.701 | 0.604 | 0 | 7 | 17 | 34 | 44 |
| SHORT | 25 | 56.0% | 0.107 | 0.089 | 1.333 | 0.767 | -0.732 | -3.223 | 0.933 | 0.753 | 0 | 8 | 7 | 10 | 12 |

**Critical censoring:** T3 hit **0** times, T2 **1** time, T1 **15/83** (18%). 44/83 still OPEN. Closed-only mean R of the 39 completed trades is **+0.12R** with win rate **36%**. If OPEN trades are counted as 0R, mean R collapses to **~+0.06R**. Headline +0.25R is mostly unrealized.

**Evidence strength for “the strategy is profitable”: LOW.** Positive MTM expectancy, but right-censored, 40% never fill, and equal-weight DD is −8.4R.

### Why 56 never filled

54/56 had already run away by the first session (median first-bar distance **~6%** from entry). This is a trade-construction/execution failure, not a harmonic-ratio failure. Carney entries are PRZ limits. `generate_signal` already computed `in_prz` and then **commented out** the HOLD. That is the single largest operational defect.

Data-quality mismatches (report entry vs report-date close >50%): `WETO` $0.03 vs ~$9, `GOSS` $0.11 vs ~$12.40, `JTAI` $0.33 vs ~$2.31, `FEIM` $49.22 vs ~$79.85. Treat as `DATA_INSUFFICIENT` for those four.

21/139 signals have identical planned R/R **18.33:1** (fantasy T3). Outcomes: 14 OPEN, 6 no-entry, 1 full loss. T3 never hit.

---

## 2. Trade outcome table (canonical = first appearance)

| Asset | First report | Pattern | Dir | Entry | Stop | Targets | Outcome | R | MFE | MAE | Multi | Reason |
|---|---|---|---|---:|---:|---|---|---:|---:|---:|---|---|
| AAOI | 2026-06-27 | BUTTERFLY | LONG | 127.01 | 107.96 | 194.44 / 233.67 / 280.4 | FULL_LOSS | -1.006 | 0.64 | 1.10 | NO | Favorable then stopped |
| ALGM | 2026-06-27 | BUTTERFLY | SHORT | 61.67 | 70.93 | 44.91 / 35.71 / 27.61 | FULL_LOSS | -1.008 | 0.47 | 1.09 | NO | Immediate stop |
| APC | 2026-06-27 | GARTLEY | LONG | 17.89 | 15.21 | 31.31 / 53.67 / 89.45 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| ARCC | 2026-06-27 | SHARK | LONG | 17.72 | 15.06 | 31.01 / 53.16 / 88.6 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| BCAR | 2026-06-27 | GARTLEY | LONG | 10.35 | 8.8 | 18.11 / 31.05 / 51.75 | FULL_LOSS | -1.006 | 0.01 | 1.83 | YES | Never worked |
| BKR | 2026-06-27 | BAT | LONG | 55.56 | 47.23 | 83.4 / 100.08 / 120.09 | OPEN | 0.325 | 1.11 | 0.44 | NO | Right-censored MTM |
| BWMN | 2026-06-27 | GARTLEY | LONG | 28.23 | 24 | 42.08 / 50.49 / 60.59 | PARTIAL_WIN | 2.854 | 3.02 | 0.78 | NO | T1 2026-08-10, OPEN mark 42.42 |
| BZ=F | 2026-06-27 | BUTTERFLY | LONG | 71.4 | 60.69 | 109.17 / 131 / 157.2 | PARTIAL_WIN | 2.731 | 3.12 | 0.21 | NO | T1 2026-09-11, OPEN mark 104.61 |
| CD | 2026-06-27 | BAT | LONG | 4.25 | 3.61 | 6.18 / 7.65 / 9.9 | FULL_LOSS | -1.006 | 0.73 | 1.02 | NO | Favorable then stopped |
| CG | 2026-06-27 | BUTTERFLY | LONG | 40.47 | 34.4 | 60.65 / 72.78 / 87.34 | OPEN | 0.308 | 1.93 | 0.14 | NO | Right-censored MTM |
| CIFR | 2026-06-27 | BUTTERFLY | SHORT | 30.14 | 34.66 | 22.3 / 16.64 / 13.22 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| CLNE | 2026-06-27 | GARTLEY | LONG | 1.66 | 1.41 | 2.56 / 3.09 / 4.01 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| EGAN | 2026-06-27 | BAT | LONG | 6.09 | 5.18 | 9.01 / 11 / 14.21 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| ESQ | 2026-06-27 | 5-0 | SHORT | 119.81 | 137.78 | 102.79 / 81.27 / 35.33 | OPEN | -0.068 | 0.43 | 0.84 | NO | Right-censored MTM |
| FANG | 2026-06-27 | GARTLEY | LONG | 179.35 | 152.45 | 313.87 / 538.06 / 896.77 | OPEN | 0.889 | 1.32 | 0.36 | NO | Right-censored MTM |
| GASS | 2026-06-27 | BUTTERFLY | LONG | 7.96 | 6.77 | 11.74 / 14.19 / 17.31 | OPEN | 1.227 | 1.59 | 0.13 | NO | Right-censored MTM |
| GLPI | 2026-06-27 | SHARK | LONG | 44.12 | 37.5 | 77.21 / 132.36 / 220.6 | OPEN | -0.586 | 0.38 | 0.62 | NO | Right-censored MTM |
| HG=F | 2026-06-27 | BUTTERFLY | LONG | 5.93 | 5.04 | 10.37 / 17.79 / 29.64 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| INDA | 2026-06-27 | SHARK | SHORT | 50.02 | 54.65 | 43.74 / 32.7 / 20.16 | OPEN | 0.095 | 0.28 | 0.27 | NO | Right-censored MTM |
| IPX | 2026-06-27 | SHARK | LONG | 25.3 | 21.5 | 38.13 / 49.57 / 61.17 | FULL_LOSS | -1.008 | 0.93 | 1.19 | NO | Favorable then stopped |
| KMB | 2026-06-27 | BAT | SHORT | 109.91 | 126.4 | 91.27 / 60.59 / 47.97 | OPEN | 0.713 | 0.77 | 0.42 | NO | Right-censored MTM |
| MIRM | 2026-06-27 | CRAB | SHORT | 124.43 | 143.09 | 103.05 / 77.99 / 48.85 | PARTIAL_WIN | 1.352 | 1.91 | 0.30 | NO | T1 2026-08-03, OPEN mark 98.22 |
| MLCO | 2026-06-27 | BAT | LONG | 5.07 | 4.31 | 7.43 / 9.02 / 11 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| MNPR | 2026-06-27 | SHARK | SHORT | 94.83 | 104.5 | 79.17 / 57.75 / 38.47 | FULL_LOSS | -1.011 | 0.88 | 1.83 | NO | Favorable then stopped |
| MPLT | 2026-06-27 | BUTTERFLY | SHORT | 34.37 | 39.53 | 26.46 / 18.43 / 14.74 | FULL_LOSS | -1.008 | 0.38 | 1.07 | NO | Never worked |
| MZTI | 2026-06-27 | 5-0 | SHORT | 116.86 | 131.74 | 97.53 / 54.28 / 43.42 | OPEN | 0.641 | 0.87 | 0.36 | NO | Right-censored MTM |
| OCUL | 2026-06-27 | GARTLEY | SHORT | 10.62 | 11.49 | 8.76 / 6.96 / 5.14 | NO_VALID_ENTRY |  |  |  | YES | Price left PRZ / no fill |
| PHVS | 2026-06-27 | 5-0 | SHORT | 35.33 | 40.62 | 29.63 / 23.1 / 8.9 | FULL_LOSS | -1.008 | 0.72 | 1.50 | NO | Favorable then stopped |
| POET | 2026-06-27 | GARTLEY | LONG | 9.3 | 7.91 | 13.32 / 16.53 / 20.91 | FULL_LOSS | -1.006 | 0.78 | 1.06 | NO | Favorable then stopped |
| PPTA | 2026-06-27 | BUTTERFLY | LONG | 20.37 | 17.31 | 29.94 / 37.37 / 44.84 | FULL_LOSS | -1.006 | 0.65 | 1.09 | YES | Favorable then stopped |
| PRCT | 2026-06-27 | 5-0 | LONG | 19.92 | 16.93 | 29.39 / 35.95 / 43.65 | FULL_LOSS | -1.006 | 0.55 | 1.09 | NO | Favorable then stopped |
| PSNY | 2026-06-27 | GARTLEY | LONG | 16.93 | 14.39 | 24.39 / 33.11 / 42.88 | FULL_LOSS | -1.006 | 1.59 | 1.08 | YES | T1 too far (MFE≥1R then stop) |
| QUIK | 2026-06-27 | SHARK | LONG | 17.15 | 14.58 | 24.8 / 64.61 / 86.34 | FULL_LOSS | -1.006 | 0.36 | 1.05 | YES | Immediate stop |
| RR | 2026-06-27 | GARTLEY | LONG | 1.81 | 1.54 | 2.61 / 3.46 / 4.16 | FULL_LOSS | -1.006 | 0.15 | 1.04 | NO | Never worked |
| RUM | 2026-06-27 | GARTLEY | LONG | 5.83 | 5.04 | 8.61 / 10.55 / 13.47 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| SHIP | 2026-06-27 | SHARK | LONG | 14.01 | 11.91 | 25.05 / 30.06 / 36.07 | OPEN | 2.110 | 2.50 | 0.39 | NO | Right-censored MTM |
| SI=F | 2026-06-27 | 5-0 | LONG | 57.25 | 48.66 | 83.65 / 119.25 / 143.1 | OPEN | 0.850 | 1.62 | 0.26 | NO | Right-censored MTM |
| TARS | 2026-06-27 | BUTTERFLY | SHORT | 69.48 | 78.34 | 60.89 / 44.36 / 31.54 | PARTIAL_WIN | -0.615 | 1.76 | 1.52 | NO | T1 2026-07-10, SL 2026-09-02 |
| TIP | 2026-06-27 | GARTLEY | LONG | 108.88 | 92.55 | 190.54 / 326.64 / 544.4 | OPEN | -0.229 | 0.01 | 0.23 | YES | Right-censored MTM |
| TSAT | 2026-06-27 | 5-0 | LONG | 40.8 | 34.68 | 61.49 / 79.9 / 95.88 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| TYGO | 2026-06-27 | DEEP CRAB | LONG | 2.23 | 1.97 | 3.79 / 5.28 / 21.63 | FULL_LOSS | -1.008 | 1.58 | 1.42 | NO | T1 too far (MFE≥1R then stop) |
| UAL | 2026-06-27 | CRAB | SHORT | 138.44 | 159.21 | 113.14 / 86.18 / 40.38 | PARTIAL_WIN | 1.078 | 1.35 | 0.13 | NO | T1 2026-07-23, OPEN mark 109.82 |
| USO | 2026-06-27 | 5-0 | LONG | 104.07 | 88.46 | 151.32 / 236.23 / 283.48 | PARTIAL_WIN | 3.208 | 3.51 | 0.11 | NO | T1 2026-09-10, OPEN mark 154.9 |
| VSTM | 2026-06-27 | BAT | LONG | 3.43 | 2.92 | 4.89 / 6.71 / 8.74 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| WRD | 2026-06-27 | BUTTERFLY | LONG | 5.18 | 4.4 | 8.12 / 10.09 / 12.26 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| WSBC | 2026-06-27 | CRAB | SHORT | 39.25 | 45.14 | 32.87 / 24.5 / 14.82 | OPEN | -0.245 | 0.05 | 0.68 | NO | Right-censored MTM |
| Z | 2026-06-27 | 5-0 | LONG | 29.23 | 24.85 | 45.19 / 55.49 / 71.3 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| ZG | 2026-06-27 | 5-0 | LONG | 29.03 | 24.68 | 42 / 50.83 / 64.56 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| ADEA | 2026-07-21 | 5-0 | LONG | 24.37 | 20.71 | 42.65 / 73.11 / 121.85 | OPEN | 0.639 | 2.14 | 0.37 | NO | Right-censored MTM |
| ALMU | 2026-07-21 | GARTLEY | LONG | 14.15 | 12.03 | 21.1 / 25.38 / 31.79 | OPEN | -0.349 | 2.26 | 0.81 | NO | Right-censored MTM |
| ANAB | 2026-07-21 | SHARK | LONG | 53.17 | 45.19 | 93.05 / 159.51 / 265.85 | OPEN | 0.145 | 0.99 | 0.30 | NO | Right-censored MTM |
| APLD | 2026-07-21 | SHARK | LONG | 24.03 | 20.43 | 34.11 / 43.26 / 51.91 | OPEN | 0.664 | 2.50 | 0.31 | YES | Right-censored MTM |
| ASPI | 2026-07-21 | BUTTERFLY | LONG | 3.61 | 3.07 | 5.45 / 6.91 / 8.32 | OPEN | -0.556 | 1.64 | 0.57 | YES | Right-censored MTM |
| AUGO | 2026-07-21 | BUTTERFLY | LONG | 48.05 | 40.84 | 74.34 / 92.89 / 111.47 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| AVR | 2026-07-21 | 5-0 | LONG | 8.07 | 6.86 | 14.12 / 24.21 / 40.35 | OPEN | 0.231 | 1.68 | 0.28 | NO | Right-censored MTM |
| BEAM | 2026-07-21 | 5-0 | LONG | 27.1 | 23.04 | 40.69 / 50.41 / 63.77 | OPEN | -0.755 | 1.18 | 0.77 | NO | Right-censored MTM |
| CDZI | 2026-07-21 | GARTLEY | LONG | 3.29 | 2.93 | 4.7 / 5.79 / 7.18 | FULL_LOSS | -1.008 | 0.32 | 1.03 | YES | Never worked |
| CENX | 2026-07-21 | 5-0 | LONG | 40.76 | 34.65 | 62.9 / 75.48 / 90.58 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| FAS | 2026-07-21 | BAT | SHORT | 174.79 | 201.01 | 155.66 / 113.66 / 13.78 | OPEN | 0.034 | 0.29 | 0.47 | NO | Right-censored MTM |
| FEIM | 2026-07-21 | SHARK | LONG | 49.22 | 41.84 | 74.01 / 88.81 / 106.57 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| FIBK | 2026-07-21 | GARTLEY | SHORT | 40.6 | 44.56 | 35.64 / 26.44 / 21.15 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| FLNC | 2026-07-21 | BAT | LONG | 13.23 | 11.25 | 19.01 / 23.08 / 29.78 | FULL_LOSS | -1.006 | 1.32 | 1.08 | NO | T1 too far (MFE≥1R then stop) |
| FRME | 2026-07-21 | BUTTERFLY | SHORT | 45.33 | 52.13 | 38.3 / 30.37 / 9.82 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| FWONA | 2026-07-21 | SHARK | SHORT | 94.06 | 108.17 | 79.74 / 28.46 / 22.58 | OPEN | 0.498 | 0.55 | 0.34 | YES | Right-censored MTM |
| FWONK | 2026-07-21 | SHARK | SHORT | 102.74 | 118.15 | 90.39 / 68.32 / 21 | OPEN | 0.464 | 0.52 | 0.30 | NO | Right-censored MTM |
| GILT | 2026-07-21 | BUTTERFLY | LONG | 10.91 | 9.27 | 15.31 / 20.3 / 24.37 | OPEN | -0.622 | 0.87 | 0.94 | NO | Right-censored MTM |
| GOSS | 2026-07-21 | 5-0 | LONG | 0.11 | 0.1 | 0.18 / 0.24 / 0.38 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| IAI | 2026-07-21 | 5-0 | SHORT | 196.44 | 225.91 | 171.25 / 123.55 / 53.81 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| INOD | 2026-07-21 | DEEP CRAB | LONG | 58 | 49.3 | 91.81 / 114.3 / 137.16 | OPEN | -0.551 | 2.46 | 0.62 | NO | Right-censored MTM |
| INV | 2026-07-21 | BAT | LONG | 3.35 | 3 | 4.82 / 5.79 / 7.16 | FULL_LOSS | -1.009 | 0.77 | 1.09 | NO | Favorable then stopped |
| IOVA | 2026-07-21 | GARTLEY | SHORT | 5.13 | 5.63 | 4.32 / 3.33 / 2.45 | FULL_LOSS | -1.043 | 3.08 | 1.08 | NO | T1 too far (MFE≥1R then stop) |
| JTAI | 2026-07-21 | BUTTERFLY | LONG | 0.33 | 0.28 | 0.57 / 0.68 / 0.89 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| LTBR | 2026-07-21 | DEEP CRAB | LONG | 6.92 | 5.88 | 10.43 / 12.83 / 15.43 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| MANH | 2026-07-21 | BUTTERFLY | SHORT | 166.56 | 191.54 | 139.37 / 64.53 / 51.62 | FULL_LOSS | -1.008 | 0.16 | 1.94 | NO | Immediate stop |
| MTCH | 2026-07-21 | 5-0 | SHORT | 41.03 | 47.18 | 34.22 / 10.87 / 8.08 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| NNE | 2026-07-21 | BUTTERFLY | LONG | 15.44 | 13.12 | 22.8 / 27.5 / 35.22 | OPEN | 0.418 | 2.45 | 0.32 | YES | Right-censored MTM |
| NVTS | 2026-07-21 | BAT | LONG | 10.74 | 9.25 | 15.14 / 19.67 / 23.96 | OPEN | 2.902 | 8.34 | 0.23 | NO | Right-censored MTM |
| ORBS | 2026-07-21 | BUTTERFLY | LONG | 0.57 | 0.49 | 0.88 / 1.11 / 1.37 | PARTIAL_WIN | 5.312 | 7.88 | 0.03 | NO | T1 2026-08-21, T2 2026-09-08, OPEN mark 0.973 |
| PLPC | 2026-07-21 | 5-0 | LONG | 314.58 | 267.39 | 550.51 / 943.74 / 1572.9 | OPEN | 1.941 | 3.47 | 0.80 | NO | Right-censored MTM |
| PLXS | 2026-07-21 | 5-0 | LONG | 238.11 | 202.39 | 416.69 / 714.33 / 1190.55 | OPEN | 0.482 | 1.68 | 0.23 | NO | Right-censored MTM |
| PRGS | 2026-07-21 | BAT | SHORT | 41.19 | 47.37 | 35.59 / 27.9 / 6.35 | OPEN | 0.206 | 0.33 | 0.84 | NO | Right-censored MTM |
| PSIX | 2026-07-21 | GARTLEY | LONG | 29.56 | 25.13 | 43.92 / 56.68 / 68.33 | PARTIAL_WIN | 2.913 | 3.30 | 0.97 | YES | T1 2026-08-10, OPEN mark 42.11 |
| PTON | 2026-07-21 | SHARK | SHORT | 6.44 | 7.05 | 5.41 / 4.15 / 3.32 | PARTIAL_WIN | 1.827 | 2.02 | 0.55 | NO | T1 2026-08-10, OPEN mark 4.95 |
| QNST | 2026-07-21 | BAT | SHORT | 18.02 | 19.46 | 15.43 / 11.34 / 8.34 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| REMX | 2026-07-21 | BUTTERFLY | LONG | 69.49 | 59.07 | 107.94 / 129.53 / 155.44 | OPEN | 0.103 | 1.09 | 0.52 | NO | Right-censored MTM |
| ROBO | 2026-07-21 | BUTTERFLY | LONG | 76.64 | 65.14 | 134.12 / 229.92 / 383.2 | OPEN | 0.215 | 0.77 | 0.10 | NO | Right-censored MTM |
| SFM | 2026-07-21 | GARTLEY | LONG | 72.19 | 61.36 | 114.25 / 140.07 / 168.08 | OPEN | 0.053 | 1.95 | 0.20 | NO | Right-censored MTM |
| SLNH | 2026-07-21 | GARTLEY | LONG | 1.03 | 0.91 | 1.55 / 1.88 / 2.33 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| STIM | 2026-07-21 | BAT | SHORT | 2.33 | 2.68 | 1.98 / 1.46 / 0.78 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| STRL | 2026-07-21 | BUTTERFLY | LONG | 593.62 | 504.58 | 910.52 / 1092.62 / 1311.15 | FULL_LOSS | -1.006 | 0.09 | 1.13 | NO | Immediate stop |
| SWKS | 2026-07-21 | BAT | LONG | 55.43 | 47.12 | 83.21 / 103.02 / 139.41 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| TMC | 2026-07-21 | 5-0 | LONG | 3.57 | 3.03 | 5.31 / 6.68 / 8.09 | PARTIAL_WIN | 1.183 | 3.35 | 0.32 | NO | T1 2026-08-28, OPEN mark 3.935 |
| WATT | 2026-07-21 | DEEP CRAB | LONG | 14.23 | 12.1 | 20.48 / 26.42 / 32.38 | FULL_LOSS | -1.006 | 2.71 | 1.16 | NO | T1 too far (MFE≥1R then stop) |
| ZW=F | 2026-07-21 | CRAB | SHORT | 698.25 | 777.88 | 627.01 / 470.63 / 376.51 | PARTIAL_WIN | 0.089 | 0.90 | 0.97 | NO | T1 2026-08-06, OPEN mark 707 |
| ACDC | 2026-08-02 | SHARK | LONG | 3.55 | 3.02 | 5.13 / 6.35 / 7.69 | PARTIAL_WIN | 3.100 | 4.02 | 0.07 | NO | T1 2026-08-10, OPEN mark 5.21 |
| ALM | 2026-08-02 | BUTTERFLY | LONG | 10.74 | 9.13 | 15.1 / 19.64 / 24.14 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| AXSM | 2026-08-02 | BAT | LONG | 217.64 | 184.99 | 380.87 / 652.92 / 1088.2 | OPEN | 0.212 | 0.51 | 0.59 | NO | Right-censored MTM |
| CMPR | 2026-08-02 | BAT | LONG | 82 | 69.7 | 122.19 / 167.7 / 201.24 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| CRDO | 2026-08-02 | BUTTERFLY | LONG | 177 | 150.45 | 280.09 / 336.1 / 403.32 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| CZWI | 2026-08-02 | BAT | LONG | 20.52 | 17.44 | 35.91 / 61.56 / 102.6 | OPEN | 1.552 | 2.77 | 0.00 | NO | Right-censored MTM |
| DUOT | 2026-08-02 | BAT | LONG | 7.46 | 6.34 | 11.3 / 15.28 / 18.34 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| FDMT | 2026-08-02 | GARTLEY | LONG | 9.39 | 8 | 13.7 / 17.12 / 21.38 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| FTRE | 2026-08-02 | BUTTERFLY | SHORT | 21.39 | 23.65 | 19.16 / 14.15 / 10.11 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| HLIT | 2026-08-02 | BUTTERFLY | LONG | 10.45 | 8.88 | 15.49 / 28.45 / 35.66 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| INVZ | 2026-08-02 | DEEP CRAB | LONG | 0.38 | 0.32 | 0.66 / 0.86 / 1.07 | FULL_LOSS | -1.005 | 1.50 | 1.00 | NO | T1 too far (MFE≥1R then stop) |
| KRNT | 2026-08-02 | BAT | LONG | 14.36 | 12.21 | 21.95 / 29.13 / 37.46 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| LAES | 2026-08-02 | BAT | LONG | 2.22 | 1.89 | 3.39 / 4.38 / 5.29 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| MVBF | 2026-08-02 | GARTLEY | SHORT | 31.99 | 36.79 | 27.27 / 21.03 / 9.39 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| NG=F | 2026-08-02 | SHARK | LONG | 2.62 | 2.23 | 3.93 / 4.8 / 5.77 | OPEN | 0.541 | 1.04 | 0.01 | NO | Right-censored MTM |
| NOVT | 2026-08-02 | BUTTERFLY | LONG | 135.9 | 115.52 | 237.83 / 407.7 / 679.5 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| PBW | 2026-08-02 | DEEP CRAB | LONG | 29.82 | 25.35 | 45.71 / 55.55 / 74.3 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| QQQX | 2026-08-02 | SHARK | LONG | 28.72 | 24.41 | 50.26 / 86.16 / 143.6 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| QS | 2026-08-02 | DEEP CRAB | LONG | 4.77 | 4.05 | 7.08 / 9.59 / 11.66 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| QSI | 2026-08-02 | BUTTERFLY | LONG | 0.69 | 0.61 | 1.01 / 1.29 / 1.56 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| REFI | 2026-08-02 | DEEP CRAB | LONG | 9.69 | 8.24 | 14.59 / 19.61 / 23.53 | OPEN | 0.537 | 0.72 | 0.01 | NO | Right-censored MTM |
| SHAZ | 2026-08-02 | BUTTERFLY | LONG | 39.13 | 33.26 | 60.25 / 75.84 / 97.48 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| SKYW | 2026-08-02 | CRAB | SHORT | 114.27 | 131.41 | 97.72 / 75.32 / 38.49 | PARTIAL_WIN | 1.038 | 1.24 | 0.20 | NO | T1 2026-08-31, OPEN mark 96.14 |
| SND | 2026-08-02 | GARTLEY | LONG | 4.06 | 3.65 | 5.79 / 7.44 / 9.43 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| SSNC | 2026-08-02 | DEEP CRAB | SHORT | 80 | 88.79 | 66.54 / 48.88 / 32.56 | OPEN | -0.031 | 0.21 | 0.56 | NO | Right-censored MTM |
| SUPN | 2026-08-02 | GARTLEY | LONG | 44.35 | 37.7 | 77.61 / 133.05 / 221.75 | OPEN | -0.408 | 1.23 | 0.49 | NO | Right-censored MTM |
| SYNA | 2026-08-02 | BUTTERFLY | LONG | 103.51 | 87.98 | 181.14 / 310.53 / 517.55 | OPEN | -0.207 | 0.54 | 0.81 | NO | Right-censored MTM |
| TRI | 2026-08-02 | SHARK | SHORT | 108.29 | 124.53 | 96.24 / 48.65 / 38.92 | PARTIAL_WIN | 0.686 | 0.78 | 0.32 | NO | T1 2026-09-10, OPEN mark 97.35 |
| TSSI | 2026-08-02 | BUTTERFLY | LONG | 8.66 | 7.36 | 12.67 / 15.44 / 19.38 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| USAU | 2026-08-02 | DEEP CRAB | LONG | 12.23 | 10.4 | 17.93 / 23.08 / 32.1 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| WBTN | 2026-08-02 | BAT | LONG | 8.81 | 7.49 | 13.08 / 17.41 / 21.16 | OPEN | 1.492 | 1.74 | 0.73 | NO | Right-censored MTM |
| WETO | 2026-08-02 | BUTTERFLY | LONG | 0.03 | 0.02 | 0.53 / 0.7 / 0.86 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| WOOF | 2026-08-02 | GARTLEY | SHORT | 2.87 | 3.21 | 2.36 / 1.89 / 1.51 | FULL_LOSS | -1.009 | 1.09 | 1.03 | NO | T1 too far (MFE≥1R then stop) |
| EXE | 2026-08-18 | SHARK | SHORT | 98.88 | 107.28 | 88.3 / 60.15 / 48.12 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| JRVR | 2026-08-18 | BAT | LONG | 3.88 | 3.3 | 5.74 / 7.2 / 8.88 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| KMDA | 2026-08-18 | BAT | LONG | 6.85 | 5.82 | 9.95 / 12.05 / 15.1 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| LQD | 2026-08-18 | GARTLEY | LONG | 105.67 | 89.82 | 184.92 / 317.01 / 528.35 | OPEN | -0.133 | 0.03 | 0.13 | NO | Right-censored MTM |
| MQ | 2026-08-18 | SHARK | LONG | 15.28 | 12.99 | 22.14 / 26.57 / 37.91 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| NPCE | 2026-08-18 | 5-0 | LONG | 15.38 | 13.07 | 23.21 / 27.85 / 33.42 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| PRTH | 2026-08-18 | BUTTERFLY | LONG | 5.1 | 4.33 | 7.57 / 11.18 / 13.42 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| SCHH | 2026-08-18 | SHARK | LONG | 23.52 | 20.81 | 41.16 / 70.56 / 117.6 | OPEN | -0.244 | 0.10 | 0.31 | NO | Right-censored MTM |
| STNE | 2026-08-18 | BAT | LONG | 9.38 | 7.97 | 14.03 / 17.18 / 28.52 | OPEN | 0.651 | 1.19 | 0.09 | NO | Right-censored MTM |
| SVRA | 2026-08-18 | GARTLEY | LONG | 5.14 | 4.37 | 8.99 / 15.42 / 25.7 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |
| TRUP | 2026-08-18 | BUTTERFLY | SHORT | 31.41 | 34.42 | 27.13 / 19.84 / 15.87 | PARTIAL_WIN | 2.015 | 2.30 | 0.23 | NO | T1 2026-09-08, OPEN mark 24.89 |
| WYFI | 2026-08-18 | BUTTERFLY | SHORT | 32.36 | 37.21 | 23.66 / 18.21 / 14.04 | NO_VALID_ENTRY |  |  |  | NO | Price left PRZ / no fill |

---

## 3. Duplicate / follow-up table

12 unique assets, 14 subsequent appearances. TIP and FWONA appeared three times. **Primary stats never count later prints as extra trades.**

| Asset | First | Later | Orig entry | New entry | Change | Orig outcome | Follow-up outcome | Interpretation |
|---|---|---|---:|---:|---|---|---|---|
| APLD | 2026-07-21 | 2026-08-02 | 24.03 | 22.93 | -1.10 | OPEN R=0.66 | NO_VALID_ENTRY R= | Same long thesis; later entry slightly better ($24.03→$22.93). First still OPEN +0.66R. Repeat is correlated, not independent. |
| ASPI | 2026-07-21 | 2026-08-02 | 3.61 | 3.51 | -0.10 | OPEN R=-0.56 | NO_VALID_ENTRY R= | Later entry $3.61→$3.51. First OPEN −0.56R; later no fill. Repeat did not rescue. |
| BCAR | 2026-06-27 | 2026-07-21 | 10.35 | 10.35 | +0.00 | FULL_LOSS R=-1.01 | FULL_LOSS R=-1.01 | Identical plan reprinted. First already FULL_LOSS −1.0R; later also FULL_LOSS. Pure duplicate, no new information. |
| CDZI | 2026-07-21 | 2026-08-02 | 3.29 | 2.87 | -0.42 | FULL_LOSS R=-1.01 | NO_VALID_ENTRY R= | Entry improved $3.29→$2.87 but first already stopped. Later no fill. Repeat after failure. |
| FWONA | 2026-07-21 | 2026-08-02 | 94.06 | 94.98 | +0.92 | OPEN R=0.50 | OPEN R=0.42 | Short shark reprinted with worse (higher) entries. First OPEN +0.50R; later still OPEN. Confirmation of same short, not a new trade. |
| FWONA | 2026-07-21 | 2026-08-18 | 94.06 | 96.5 | +2.44 | OPEN R=0.50 | OPEN R=0.58 | Short shark reprinted with worse (higher) entries. First OPEN +0.50R; later still OPEN. Confirmation of same short, not a new trade. |
| NNE | 2026-07-21 | 2026-08-02 | 15.44 | 14.71 | -0.73 | OPEN R=0.42 | NO_VALID_ENTRY R= | Slightly better long entry $15.44→$14.71. First OPEN +0.42R; later no fill. |
| OCUL | 2026-06-27 | 2026-08-02 | 10.62 | 8.15 | -2.47 | NO_VALID_ENTRY R= | OPEN R=1.63 | DIRECTION FLIP: first SHORT Gartley (no fill), later LONG Shark. Later OPEN +1.63R. Bot contradicted itself; do not treat as confirmation. |
| PPTA | 2026-06-27 | 2026-07-21 | 20.37 | 16.43 | -3.94 | FULL_LOSS R=-1.01 | NO_VALID_ENTRY R= | Better long entry $20.37→$16.43 after original stopped out. Chasing a failed long. Later no fill. |
| PSIX | 2026-07-21 | 2026-08-02 | 29.56 | 25.28 | -4.28 | PARTIAL_WIN R=2.91 | NO_VALID_ENTRY R= | Better entry $29.56→$25.28. First was the winner (T1, +2.91R); later no fill. Repeat after success is leftover detection. |
| PSNY | 2026-06-27 | 2026-07-21 | 16.93 | 14.2 | -2.73 | FULL_LOSS R=-1.01 | FULL_LOSS R=-1.01 | Better entry $16.93→$14.20 after original stopped. Later also FULL_LOSS. Repeat of a failed long. |
| QUIK | 2026-06-27 | 2026-07-21 | 17.15 | 12.16 | -4.99 | FULL_LOSS R=-1.01 | FULL_LOSS R=-1.01 | Much better entry $17.15→$12.16 after original stopped; later also FULL_LOSS. Pattern also changed Shark→Deep Crab. |
| TIP | 2026-06-27 | 2026-08-02 | 108.88 | 107.34 | -1.54 | OPEN R=-0.23 | NO_VALID_ENTRY R= | Bond ETF Gartley/Bat reprinted as price drifted down. First OPEN −0.23R; later no-fill then OPEN −0.10R. Noise, not confirmation. |
| TIP | 2026-06-27 | 2026-08-18 | 108.88 | 106.75 | -2.13 | OPEN R=-0.23 | OPEN R=-0.10 | Bond ETF Gartley/Bat reprinted as price drifted down. First OPEN −0.23R; later no-fill then OPEN −0.10R. Noise, not confirmation. |

**Repeated-signal conclusion (Phase 9):** Repeats are **not** independent. Filled repeats: n=10, mean R **−0.11** vs non-repeats **+0.31**. Should **not** raise confidence, **not** be traded as a second ticket, and should be merged into the original working order. One direction flip (OCUL) is a detection inconsistency.

Evidence strength: **MODERATE** (n=12 names, correlated).

---

## 4. Pattern scorecard (filled primary trades, full horizon)

| Pattern | n filled | No entry | WR | Avg R | Med R | PF | Avg W | Avg L | MFE | MAE | Sample |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| BUTTERFLY | 18 | 17 | 0.444 | 0.238 | -0.382 | 1.533 | 1.541 | -0.804 | 1.574 | 0.72 | OK |
| GARTLEY | 15 | 10 | 0.267 | -0.1 | -0.408 | 0.818 | 1.677 | -0.746 | 1.341 | 0.808 | OK |
| BAT | 12 | 12 | 0.75 | 0.422 | 0.269 | 2.677 | 0.899 | -1.007 | 1.657 | 0.582 | OK |
| SHARK | 15 | 5 | 0.667 | 0.418 | 0.464 | 2.628 | 1.013 | -0.771 | 1.19 | 0.523 | OK |
| 5-0 | 12 | 8 | 0.667 | 0.528 | 0.56 | 3.234 | 1.147 | -0.709 | 1.766 | 0.576 | OK |
| DEEP CRAB | 6 | 4 | 0.167 | -0.511 | -0.778 | 0.149 | 0.537 | -0.72 | 1.53 | 0.796 | SMALL n — do not overfit |
| CRAB | 5 | 0 | 0.8 | 0.662 | 1.038 | 14.518 | 0.889 | -0.245 | 1.088 | 0.455 | SMALL n — do not overfit |

Rank by avg R among n≥8: **5-0 (+0.53)** > **Shark (+0.42)** > **Bat (+0.41)** > **Butterfly (+0.24)** > **Gartley (−0.05)**. Deep Crab (−0.51, n=6) and Crab (+0.68, n=5) are too small to rank.

Gartley is the only large-enough pattern with negative expectancy and 7/24 of all full losses. **Do not ban it yet** (n=15, LOW–MODERATE). Flag and watch.

---

## 5. Failure analysis

24 FULL_LOSS. Almost all are **countertrend** (23/24). 16/24 had MFE ≥ 0.5R before the stop — the idea was not instantly wrong; **T1 was beyond the move**. Median days-to-stop ~8. Four stopped in 0–2 days (immediate invalidation).

| Failure mode | What it is | Whose fault |
|---|---|---|
| Stale PRZ / no fill (56) | Signal exported after price left entry | C. Trade plan / D. execution |
| T1 beyond typical MFE | Median long T1 = 3.47R vs median MFE = 1.10R | C. Trade plan (MITCH targets + 50% on T3) |
| Countertrend into local 20d downtrend | Harmonics are mean-reversion; June 27 printed into SPY BEAR | B. Context filter |
| Gartley / Deep Crab cluster | 10 of 24 losses | A. Detection quality (weak) |
| Repeats of failed names | BCAR, PSNY, PPTA, QUIK, CDZI | C. Duplicate handling |
| Fantasy 18.33:1 T3 | 21 signals, 0 T3 hits | C. Trade plan |
| Bad prints (WETO, GOSS, JTAI, FEIM) | Entry vs market disagree | D. Data |
| Grade C- flood | 102/139 C-; grade does not predict R | A. Scoring not discriminative |

---

## 6. Success analysis

Best MTM names were **not** high grade: ORBS Butterfly C +5.31R (penny — treat cautiously), USO 5-0 C- +3.21R, ACDC Shark C- +3.10R, PSIX Gartley C- +2.91R, NVTS Bat C- +2.90R (OPEN).

Common traits of the useful winners: **T1 actually reachable**, often **short T1** or a long that trended after fill, **non-repeat**, **not** 18.33:1 T3-or-bust. Shorts that worked (MIRM, UAL, PTON, SKYW, TRUP, TRI) hit T1 because short T1 median is only **1.13R**.

Partial winners had MFE 2.70R vs losers 0.89R — path quality, not grade.

---

## 7. Algorithm weaknesses

1. PRZ validity check is computed then disabled — exports untradeable entries.
2. 1d MITCH T1/T2/T3 are position-trade distances on a swing timeframe. Config comment claiming T1 hit 66.7% is **false** on this sample (18%).
3. 50% of size sits on T3 which never hit in 25–77 calendar days.
4. Grade compression to C- makes grade useless as a filter. Tightening to B **hurt** (n=8, −0.31R) — do not tighten.
5. ETF confluence is cosmetic; “CONFIRMED” n=3 and worse. Do not require it.
6. No handling of repeats; same thesis is re-emitted as a new idea.
7. Long min R/R 6 forces T1 out to ~3.5R, which the 1d path does not deliver.
8. Paper trader assumes a fill at plan entry — disagrees with reality.

---

## 8. Proposed changes

| # | Current | Proposed | Reason | Evidence | n | Benefit | Overfit risk | Confidence |
|---|---|---|---|---|---:|---|---|---|
| 1 | `in_prz` computed, HOLD commented out | **Re-enable PRZ HOLD** (`REQUIRE_PRICE_IN_PRZ=True`) | Carney: enter in PRZ. 40% never fill. | 54/56 no-fills already gone next session. In-PRZ subset n=24, mean R +0.45 vs +0.25 | 139 / 24 | Fewer ghost signals | Low — restoring existing rule | **HIGH** |
| 2 | T1 at MITCH structure (~3.5R longs) | **Insert 1.0R first scale on 1d**; keep old T1 as T2; drop/de-weight T3 | Median MFE 1.1R; only 24% ever see 2R; T3=0 hits | IS June: +0.045→+0.077R (tiny). OOS closer targets help more on short windows (horizon confound). Structural, not a 31.7-style threshold | 83 | Harvest typical excursion | Medium if we tune 0.8 vs 1.2R — keep **1.0R** | **MODERATE** |
| 3 | Every reprint is a new trade | **Dedupe by ticker**; do not raise confidence; do not second-ticket | Repeats correlated and worse | n=10 filled repeats −0.11R | 12 names | Avoid double risk | Low | **MODERATE** |
| 4 | Export sub-$1 / broken prints | **Reject if report-time close disagrees with entry by >50% or entry < $1** | Data integrity | WETO/GOSS/JTAI | 4 | Remove garbage | Low | **MODERATE** |
| 5 | Ban Gartley / Deep Crab | **Do not ban** | n too small; IS edge tiny | Gartley n=15 | 15 | — | High if banned | **Leave unchanged** |
| 6 | Tighten grade to B | **Do not** | B bucket worse | n=8 −0.31R | 8 | — | High | **Leave unchanged** |
| 7 | Require ETF CONFIRMED | **Do not** | Cosmetic; tiny n | n=3 | 3 | — | High | **Leave unchanged** |
| 8 | Ban shorts | **Do not**; shorts already have nearer T1 | Short E[R] +0.11 vs long +0.31 but T1 hits more | 25 shorts | 25 | Optional smaller size | Medium | **LOW** — no rule |

---

## 9. Before vs after

Implemented in code this session: **#1 PRZ HOLD only**.

| | Original export (all 139, 83 fills) | If only in-PRZ at report close (~25) | 1R/BE scale (simulated, not coded) |
|---|---|---|---|
| Filled n | 83 | 24 | 82 |
| Mean R (MTM) | +0.25 | +0.45 | +0.33 |
| Notes | 56 ghosts | Carney-faithful | IS improvement tiny; OOS mixed with horizon bias |

A modification is **not** declared a proven edge. PRZ is a correctness fix. 1R scale is a 1d geometry fix pending more data.

---

## 10. Out-of-sample / walk-forward

Holding period is confounded with cohort (June has ~77d, Aug 18 ~25d). Later books look better partly because losers have not finished stopping and because 20d MTM is still open.

| Cohort | Role | n filled | Mean R MTM | WR |
|---|---|---:|---:|---:|
| 2026-06-27 | Research | 34 | +0.06 | 44% |
| 2026-07-21 | Validate | 32 | +0.32 | 63% |
| 2026-08-02 + 08-18 | Test | 17 | +0.52 | 59% |

June was SPY **BEAR** (only bear cohort); later were **SIDEWAYS**. Strategy looks regime-dependent. **Do not** claim OOS superiority of filters trained on June — June itself was ~flat.

Skip Gartley+Deep Crab: June +0.12 (n=26) vs +0.06 all; later +0.62 (n=36) vs +0.39. Directionally consistent but **LOW–MODERATE** and not implemented.

**Insufficient observations for a statistically reliable train/validation/test split.** Stated explicitly.

---

## 11. Final algorithm specification (implementation-ready)

Keep: Carney pattern set, 5% fib tolerance, 1d swing window 4, stop clamp 8–15%, min R/R 6 long / 3 short, MITCH structure targets as **later** objectives,  Type 1/2 monitoring, ETF annotation without hard filter, grade display without a B+ cutoff.

**Change A (coded):** `REQUIRE_PRICE_IN_PRZ = True`. If current close is outside the existing PRZ band (2%, or 3% for Butterfly/Crab/Deep Crab), emit **HOLD** not BUY/SELL. This re-enables the commented block in `PatternDetector.generate_signal`.

**Change B (specified, not coded — avoid threshold fishing):** On `DATA_INTERVAL=1d` only, prepend T1′ = entry ± 1.0R, shift old T1→T2, old T2→T3, drop old T3. Suggested 1d weights 50/30/20. Do **not** apply to 1wk/1mo until those books are audited.

**Change C (operational):** Dedupe exports by ticker+direction. Reprints update the note, they do not open a second paper trade.

**Change D:** Skip signals with entry < $1 or \|report-close / entry − 1\| > 50%.

Paper trader: fill only if the next session trades the PRZ; otherwise `NO_VALID_ENTRY`. Same-bar stop+target → ambiguous, not a win.

---

## Executive answers

1. **How well did it perform?** Weakly positive MTM (+0.25R/fill, PF 1.70) that **does not survive conservative accounting** (OPEN=0 → ~+0.06R). 0 full wins. 40% never entered.
2. **Best patterns (n≥8):** 5-0, Shark, Bat.
3. **Worst (n≥8):** Gartley. Deep Crab worst but n=6.
4. **Best conditions:** SPY sideways (not the June bear print); fills that actually occur in PRZ; non-repeats.
5. **Worst conditions:** SPY bear (June 27), countertrend longs, stale PRZ, repeats of losers.
6. **Failure modes:** Stale entry, T1 too far vs MFE, countertrend, duplicate losers, bad prints.
7. **Change:** Re-enable PRZ HOLD (done). Specify 1R first scale on 1d. Dedupe. Kill garbage prints.
8. **Unchanged:** Pattern set, grade cutoff, ETF confluence requirement, short ban, Gartley ban, min R/R until 1R scale exists.
9. **New filters justified:** PRZ-still-valid (HIGH). Repeat-dedupe (MODERATE). Data-quality (MODERATE).
10. **Outperformance:** PRZ is fewer trades, not a magic PF. 1R scale simulated +0.08R MTM with horizon bias — **not claimed as proven**.
11. **OOS:** Sample too small and horizon-confounded. Later cohorts look better; June was flat. **Do not overclaim.**
12. **Uncertainty:** n=83 fills / 139 signals / 4 dates / ~11 weeks. Heavy censoring. Multiple-testing risk on pattern ranks.
13. **Multi-report assets:** APLD, ASPI, BCAR, CDZI, FWONA, NNE, OCUL, PPTA, PSIX, PSNY, QUIK, TIP.
14. **Did repeats help?** No. Mean R worse; one direction flip (OCUL). Treat as one working order.

Negative findings are the point: the bot is **not** currently a 6:1 daily swing system. It is a scanner that often publishes leftover PRZs and parks 50% in targets the 1d path does not reach.
