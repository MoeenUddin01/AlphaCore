# Backtest Findings — Signal-Source Edge Audit (2026-08-07)

> Purpose: determine whether the volatility-classifier (LSTMClassifier) strategy,
> the current direction-LSTM + sentiment pipeline, or sentiment alone show any
> statistically credible predictive edge. Pure research — **no live-system
> changes were made** as part of this audit.

## TL;DR

None of the three signal sources shows statistically credible edge:

1. **Volatility classifier** — its previously reported "76–89% accuracy" is a
   majority-class artifact (always predicts HIGH_VOL, MCC = 0.0). A
   volatility-primary strategy built on it degenerates.
2. **Direction LSTM** — coin-flip on the retrain test split (~50% acc, down-class
   never predicted). Only 5 trades fired across all 5 pairs in 1,360 OOS
   opportunities.
3. **Sentiment (FinBERT)** — winners/losers share the same sentiment scores
   (gap ~+0.02 on 17-trade cohort); below-threshold signal mass means most
   sentiment scores never produce trades.

---

## 1. Volatility-primary backtest results

### Method (reproducible)

- **Script:** `/tmp/opencode/bt/backtest.py` (research only, not committed).
- **Data:** 3,000 hourly Binance mainnet candles per pair (Apr 4 → Aug 7 2026),
  cached at `/tmp/opencode/bt/{BTC,ETH,SOL,BNB,ADA}.csv`.
- **Models:** current `models_saved/*_lstm_best.pt` (direction) and
  `models_saved/*_classifier_best.pt` (vol), with `artifacts/scaler_*.json`.
- **Out-of-sample window:** last 272 candles/pair = 1,360 candles
  (2026-07-26 23:00 → 2026-08-07 06:00). Predictions made from windows ending
  at candle `t`, entry at open of candle `t+1` (no lookahead).
- **Mechanics (identical to live config):** capital $10,000; base notional
  `min(5% · equity, $500)`; SL 3%, TP 6% checked intrabar; taker fee 0.1%
  per side; direction entry requires `prob_up ≥ 0.55`.

### Aggregate results (all 5 pairs, OOS)

| Strategy | Trades | Win% | PnL (USD) | PnL % | Max DD % | Sharpe |
|---|---|---|---|---|---|---|
| Baseline (dir LSTM, fixed size) | 5 | 40.0 | **+6.95** | +0.07 | 0.32 | 0.16 |
| Variant A (inverse vol sizing) | 5 | 40.0 | +3.48 | +0.03 | 0.16 | 0.16 |
| Variant B (skip entry on HIGH_VOL) | 0 | — | 0.00 | 0.00 | 0.00 | 0.00 |
| Variant B2 (vol-spike exit) | 73 | 23.3 | **−70.79** | −0.71 | 0.74 | −4.22 |

Per-pair baseline (direction LSTM): BTC 0 trades, ETH 0, SOL 3 (1 win,
−$20.05), BNB 2 (1 win, +$27.00), ADA 0. Total 5 trades — statistically
meaningless sample.

### Interpretation

- **Variant A** is identical to baseline except it always halves size
  (classifier always says HIGH) → same 5 trades, half the PnL.
- **Variant B** never enters (classifier always predicts HIGH_VOL) → 0 trades.
- **Variant B2** fires the vol-spike exit on nearly every bar → 72/73 exits are
  vol-spike, 23% win rate, −$70.79. A strategy keyed to the classifier output
  is worse than doing nothing.

### Why the variants look so broken

Because the classifier output is **constant**, every volatility-gated variant
collapses to a fixed behavior — always-halve, never-trade, or always-exit.
None of them can show edge because the underlying signal carries none.

---

## 2. Root cause — volatility classifier accuracy is a majority-class artifact

### Retrain metrics (commit `4507be2`, test split = last 10% ≈ 272 rows/pair)

| Pair | Reported test acc % |
|---|---|
| BTC | 83.82 |
| ETH | 76.47 |
| SOL | 88.97 |
| BNB | 83.82 |
| ADA | 83.09 |

These looked strong. They are the **base rate**, not skill:

### OOS classifier diagnostics (same window as backtest)

| Pair | Pred HIGH % | Label HIGH % | Accuracy % | Majority-baseline % |
|---|---|---|---|---|
| BTC | 100.0 | 81.6 | 81.6 | 81.6 |
| ETH | 100.0 | 82.0 | 82.0 | 82.0 |
| SOL | 100.0 | 84.9 | 84.9 | 84.9 |
| BNB | 100.0 | 84.2 | 84.2 | 84.2 |
| ADA | 100.0 | 87.1 | 87.1 | 87.1 |

- Output probability is near-constant ~0.79–0.80 (prob_std ~0.001–0.05).
- **MCC = 0.0 for all 5 pairs** (model never outputs the minority class).
- **AUC ≈ 0.58–0.60** — the tiny probability jitter is near-random rank info.
- Brier score ≈ what a constant base-rate predictor achieves.

**Conclusion:** the high reported accuracy equals predicting the majority class
every time. Label distribution in this window is ~81–87% HIGH_VOL, so a
degenerate always-HIGH model trivially hits 81–87%. The classifier has **zero
discriminative skill** for regime timing or sizing. (Root cause suspected:
LSTM with BCE loss collapses to the class prior under class imbalance — no
class-weighting/oversampling in the retrain loop.)

---

## 3. Direction LSTM — coin-flip (earlier retrain)

From `backups/artifacts_20260802/metrics_*_lstm.json` (commit `4507be2`,
test split, 272 samples/pair):

| Pair | Test acc % | Up correct | Up total | Down correct | Down total |
|---|---|---|---|---|---|
| BTC | 49.26 | 134 | 134 | **0** | 138 |
| ETH | 49.26 | 117 | 130 | 17 | 142 |
| SOL | 52.57 | 143 | 143 | **0** | 129 |
| BNB | 51.10 | 139 | 139 | **0** | 133 |
| ADA | 47.43 | 129 | 129 | **0** | 143 |

- Accuracy ~47–53% ≈ coin-flip.
- The down-class is effectively never predicted (0 correct downs for
  BTC/SOL/BNB/ADA) — the model always says "up".
- This is the second majority-class artifact in the pipeline: "up" was the
  majority direction, so the model learned to always emit it.
- Backtest consequence: `prob_up` rarely exceeds the 0.55 entry threshold in
  the right direction → only 5 entries in 1,360 opportunities.

---

## 4. Sentiment gap — winners and losers share the same score

Documented in commit `b1f037c` (UPGRADES.md §8, 2026-07-11) and reproduced
below from the current signal DB.

### 17-trade cohort (2026-07-11, single-article FinBERT, CoinDesk RSS only)

- Winners avg sentiment = **+0.49**, Losers avg sentiment = **+0.51**
- Gap ≈ **+0.02** — indistinguishable; side selection by sentiment is
  effectively random at this sample size.

### Current signal database (all-time, `alphacore.db`)

- 135 signals with sentiment: mean **−0.1071**, std 0.4764, range
  [−0.9203, +0.7721].
- **49/135 (36%)** have `|sentiment| < 0.30` — i.e. below the trade threshold
  `MIN_SENTIMENT_STRENGTH`, so no trade can fire from them.
- Trade PnL in the local DB is not populated (46/47 zeros), so a fresh
  win/loss sentiment split is not currently computable from this table — the
  gap above relies on the July cohort and the API's sentiment-validation
  summary (`crud.get_sentiment_validation_summary`).

### Note on later pipeline versions

News was expanded to multi-source (CoinDesk RSS, CryptoPanic, Currents,
CoinMarketCap Fear & Greed, crypto-compare) and sentiment went to exponential
time-decay weighting (half-life 12h) in commits `5cd1378`/`84d55be`/`ab111ff`.
This improved **coverage** (25 → ~233 articles, fewer zero scores) but the
pipeline-level validation win rate remained inconsistent (33–57% across
phases; see UPGRADES.md daily reports) and no phase demonstrated a
statistically significant winner/loser sentiment gap. The 30-trade
statistical-readiness gate (`is_statistically_ready`) has **not** been
reached, so no phase has produced a significant result.

---

## 5. Overall conclusion

Across the three signal sources evaluated:

- **Volatility classifier:** no skill (MCC = 0, constant output, accuracy =
  base rate). Cannot time regime changes or size positions.
- **Direction LSTM:** coin-flip (~50% acc, always-predicts-"up"). No usable
  entry signal.
- **Sentiment (FinBERT):** winner/loser scores indistinguishable in the only
  analyzable cohort; below-threshold mass limits effective coverage.

**None currently shows a statistically credible predictive edge.** The paper
portfolio's positive return (+27.6% at peak) is best attributed to the
bullish market drift and the system's risk controls (position sizing,
stop-loss, drawdown circuit breaker, auto-exit), not to signal skill — a
conclusion consistent with the README's own honest assessment.

### Recommended posture

1. Do **not** build volatility-gated sizing/entry/exit logic on the current
   classifier — its output is constant and will only degrade the strategy
   (see Variant B2: −$70.79).
2. Revisit the classifier training with class weighting / over-sampling or
   switch to a calibrated regression (predicted realized-vol magnitude)
   before it can contribute.
3. Treat sentiment as a gating feature, not a primary signal, until a
   ≥30-trade validation cohort shows a significant gap.
4. Consider walk-forward validation (already flagged U01/UPGRADES) before
   trusting any retrained checkpoint.

---

---

## 6. Technical baseline backtests — EMA crossover vs RSI mean-reversion

> Added: 2026-08-08. Research only — nothing wired into the live system.
> Purpose: test whether two standard, non-ML rules show any tradeable edge
> on the same historical data, as a baseline before further ML work.

### 6.1 Method (reproducible)

- **Script:** `/tmp/opencode/bt/technical.py` (research only, not committed).
- **Data:** a **full year** of Binance mainnet hourly candles per pair
  (Aug 10 2025 → Aug 8 2026, **8,717 candles/pair**, equal depth for all 5
  pairs — no data-availability gap). Cached at
  `/tmp/opencode/bt/full/{BTC,ETH,SOL,BNB,ADA}.csv`. This is a much larger
  sample than the 272-candle ML OOS window.
- **Strategies** (spot-only, long-only — matches live system, no shorts):
  - **A — EMA crossover:** BUY when EMA(20) crosses above EMA(50); exit when
    EMA(20) crosses below EMA(50) (`EMA_cross_down`), or SL/TP first.
  - **B — RSI mean-reversion:** BUY when RSI crosses below 30; exit when RSI
    rises above 70 (`RSI_overbought`), or SL/TP first.
- **Mechanics (live-identical, verified against `config.py`/`manager_agent.py`):**
  start capital $10,000; notional `min(5%·equity, $500)`; SL 3%, TP 6%
  (= 2×SL, as in `manager_agent.py`); taker fee 0.1% per side; signal at
  close of candle `t` → trade at open of candle `t+1` (no lookahead);
  SL/TP checked intrabar. No slippage modelled (consistent with the ML
  backtests — `execution_agent` applies random 0–0.15% slippage live, so live
  results would be slightly worse than shown).
- **Two reporting windows:** full year (large sample) and the same trailing
  272-candle OOS window as the ML backtests (direct comparability).

### 6.2 EMA crossover (20/50)

**Full year (8,717 candles/pair):**

| Pair | Trades | Win % | PnL (USD) | PnL % | Max DD % | Sharpe |
|---|---|---|---|---|---|---|
| BTC | 79 | 27.8 | +2.39 | +0.02 | 1.09 | 0.02 |
| ETH | 85 | 25.9 | −107.30 | −1.07 | 1.59 | −0.71 |
| SOL | 82 | 26.8 | −109.31 | −1.09 | 1.78 | −0.71 |
| BNB | 84 | 28.6 | −98.69 | −0.99 | 1.84 | −0.78 |
| ADA | 88 | 21.6 | −334.67 | −3.35 | 4.20 | −2.16 |
| **ALL** | **418** | **26.1** | **−647.58** | **−6.48** | **7.39** | **−2.03** |

Exits (ALL): 241 EMA_cross_down, 96 SL, 77 TP, 4 end_of_window.

**OOS window (last 272 candles, comparable to ML backtests):**
18 trades, 38.9% win, −$12.23 (−0.12%), max DD 0.51%. Sample too small to
conclude anything (n.s. vs 50%).

### 6.3 RSI mean-reversion (<30 buy, >70 sell)

**Full year (8,717 candles/pair):**

| Pair | Trades | Win % | PnL (USD) | PnL % | Max DD % | Sharpe |
|---|---|---|---|---|---|---|
| BTC | 67 | 44.8 | −157.89 | −1.58 | 2.46 | −1.20 |
| ETH | 78 | 39.7 | −79.23 | −0.79 | 2.74 | −0.46 |
| SOL | 70 | 28.6 | −265.53 | −2.66 | 3.16 | −1.64 |
| BNB | 61 | 42.6 | −114.05 | −1.14 | 2.31 | −0.83 |
| ADA | 81 | 25.9 | −423.52 | −4.24 | 4.24 | −2.62 |
| **ALL** | **357** | **35.9** | **−1040.21** | **−10.40** | **10.40** | **−3.05** |

Exits (ALL): 229 SL, 79 RSI_overbought, 48 TP, 1 end_of_window.

**OOS window:** 5 trades, 60% win, +$9.59 (+0.10%), max DD 0.32%. Sample too
small to conclude anything (n.s. vs 50%).

### 6.4 Buy & hold reference (same data)

| Pair | Full-year B&H % | OOS B&H % |
|---|---|---|
| BTC | −44.23 | +1.92 |
| ETH | −55.41 | +1.28 |
| SOL | −59.50 | +0.89 |
| BNB | −26.59 | +4.79 |
| ADA | −75.27 | +30.12 |

The full-year window is a **deep bear market** (−27% to −75% per pair). Both
technical strategies lost money in absolute terms, but because they only
deploy 5%-notional long positions with 3% stops, they lost *far less* than
buy & hold — which in a bear market is mostly a property of being mostly in
cash, not of timing skill.

---

## 7. Consolidated comparison — everything tested so far

Common yardsticks: win rate vs 50% (binomial z-test); break-even win rate for
the 3% SL / 6% TP + fees setup is **35.6%** (avg loss 3.20%, avg win 5.80%).

| Strategy | Period / data | Trades | Win % | PnL (USD) | Max DD % | Stat. meaningful? |
|---|---|---|---|---|---|---|
| Sentiment-primary (live, README) | Jun 23→ (17-tracked cohort) | 17 | 57.1 | +11.57 | n/a | No (n=17, n.s.) |
| Direction LSTM baseline | OOS 272c | 5 | 40.0 | +6.95 | 0.32 | **No** (n=5, nothing) |
| Vol Variant A (inv. sizing) | OOS 272c | 5 | 40.0 | +3.48 | 0.16 | **No** (n=5) |
| Vol Variant B (skip HIGH_VOL) | OOS 272c | 0 | — | 0.00 | 0.00 | **No** (never trades) |
| Vol Variant B2 (vol-spike exit) | OOS 272c | 73 | 23.3 | −70.79 | 0.74 | **Yes — sig. below 50%** (p<1e-5) |
| **EMA crossover** | **Full year** | **418** | **26.1** | **−647.58** | **7.39** | **Yes — sig. below 50%** (p≈0) |
| EMA crossover | OOS 272c | 18 | 38.9 | −12.23 | 0.51 | No (n=18, n.s.) |
| **RSI mean-reversion** | **Full year** | **357** | **35.9** | **−1040.21** | **10.40** | **Yes — sig. below 50%** (p=9e-8) |
| RSI mean-reversion | OOS 272c | 5 | 60.0 | +9.59 | 0.32 | No (n=5, n.s.) |
| Buy & hold (equal, reference) | Full year | — | — | ~−52% avg | ~70 | Yes (sig. negative) |

Binomial z-scores: EMA 26.1% → z=9.78 (p≈0); RSI 35.9% → z=5.35 (p=9.0e-8);
Variant B2 23.3% → z=4.56 (p=5.0e-6). All three are **statistically
significantly worse than a coin flip**. Nothing tested has shown a win rate
significantly above 50%.

Note on the sentiment row: the README's +27.6% portfolio return is measured
on a rising market window; the 17-trade cohort (57.1% win) is too small to
be significant and its win/loss sentiment gap was ≈ +0.02 (Section 4).

---

## 8. Honest conclusion (technical baselines)

1. **Neither simple strategy outperforms what's been tried before.** Both
   EMA crossover (26.1% win, −6.5%) and RSI mean-reversion (35.9% win,
   −10.4%) lose money over a full year, and both are **statistically
   significantly below 50% win rate** — i.e. significantly worse than random
   entry under these SL/TP/fee mechanics.
2. **Against the 35.6% all-in break-even win rate:** EMA's 26.1% is decisively
   below break-even; RSI's 35.9% sits right at the boundary, so its loss comes
   from avg win < TP (RSI_overbought / end-of-window exits) plus fee drag.
   Neither is profitable.
3. **The only strategies with statistically meaningful trade counts are the
   ones that are significantly negative** (EMA 418, RSI 357, Variant B2 73).
   Every strategy with a positive-looking result has n ≤ 18 and is not
   statistically distinguishable from luck. **Nothing has demonstrated a
   tradeable edge.**
4. **"Beats buy & hold" in a bear market is not evidence of skill** — with
   5%-notional, 3%-stopped long positions the strategy is effectively mostly
   in cash; a fully-in-cash portfolio would have also beaten buy & hold in
   Aug 2025→Aug 2026 while losing nothing.
5. **Caveats / lookahead checks:**
   - No lookahead: signals computed on close `t`, executed at open `t+1`,
     SL/TP intrabar; crossing-event re-entries only after a fresh cross.
   - Equal data depth (8,717 candles) for all 5 pairs — no pair has less
     history. The 272-candle ML windows are limited by the retrain split, not
     by data availability.
   - Long-only / spot only (matches live). No shorts, so trend-following
     could not profit from the year's downtrend.
   - Fixed 3%/6% SL/TP, 0.1% fee, no slippage in backtest. Live results would
     be slightly worse (random 0–0.15% slippage in `execution_agent`).
   - One year of hourly data = one market regime (bear). Walk-forward /
     multi-regime validation would be needed before any positive conclusion
     could be trusted.

**Bottom line:** none of the three ML signal sources, nor either standard
technical rule, shows a statistically credible predictive edge. If anything,
the technical rules — and Variant B2 — are significantly *worse* than random
under the current mechanics, which argues for keeping the system's current
sentiment-gated, risk-controlled design rather than switching to any of these
alternatives on the current evidence.

---

## Appendix — Reproduction commands

```bash
# Regenerate the vol-skill + backtest tables (research scripts in /tmp):
PYTHONPATH=. .venv/bin/python /tmp/opencode/bt/backtest.py

# Regenerate the technical baseline backtests (fetches/caches full-year data):
PYTHONPATH=. .venv/bin/python /tmp/opencode/bt/technical.py

# Retrain metrics source:
cat backups/artifacts_20260802/metrics_*_lstm.json        # direction
cat backups/artifacts_20260802/metrics_*_classifier.json  # vol
```
