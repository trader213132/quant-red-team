# Quant Red Team v1: the Detection Matrix (design spec)

Date: 2026-10-07. Status: approved (the user delegated design decisions to Claude: "do whats needed").

## 1. Research question

> Of backtests that look publishable, which audits correctly reject the fake ones, how often do they
> wrongly reject real ones, and how much access does the auditor need?

A backtest **claims an edge** when its reported daily returns have a t-statistic of at least 2.0. Only
claims are audited, because flawed research is only ever shown when it looks good. Every claim gets a
ground-truth label from an oracle (section 5), so each audit verdict is scored as one of: a catch, a miss,
a false alarm, or a correct accept.

Closest prior art, which v1 must cite and position itself against:
- White (2000), Reality Check.
- Hansen (2005), SPA.
- Bailey & López de Prado (2012), PSR.
- Bailey & López de Prado (2014), Deflated Sharpe Ratio.
- Bailey, Borwein, López de Prado & Zhu (2017), PBO/CSCV.
- Harvey, Liu & Zhu (2016), multiple testing.
- Nikolopoulos (2026), *Spurious Predictability in Financial Machine Learning*, arXiv 2604.15531 (the
  falsification audit on synthetic nulls).

The v1 contribution is a ground-truth benchmark that scores all of these, plus re-run attacks, against
**ten named failure classes**, and records the **access tier** each audit needs.

## 2. Simulated markets

Each market is a panel of `N` assets over `T` trading days (252 per year). Every day `d` has a simple
overnight return `Ron[d]` (close d-1 to open d) and an intraday return `Rid[d]` (open d to close d):
`Open[d] = Close[d-1]·(1+Ron[d])`, `Close[d] = Open[d]·(1+Rid[d])`, `Close[-1] = 1`.

**Noise.** GARCH(1,1) applies per asset to the total daily shock: `σ²[d] = ω + a·e²[d-1] + b·σ²[d-1]`,
with `a = 0.08`, `b = 0.90`, and `ω` set by the target annual volatility. `σ[d]` is capped at 4% per day.
- Shocks are standardised Student-t with ν = 5, symmetrically clipped at |z| ≤ 20. That clip keeps the
  mean exactly zero by symmetry and guarantees returns stay above -1.
- The overnight shock is `√f·σ·z_on` and the intraday shock is `√(1-f)·σ·z_id`, with `f = 0.3` and
  independent z. The GARCH input is `e = e_on + e_id`.

| Market | Definition | Truth |
|---|---|---|
| `null` | `R = e` (25% annual vol) | Prices are martingales, so every causal strategy has zero expected gross return |
| `trend` | `R = μ[d] + e`, with hidden `μ[d] = ρ·μ[d-1] + η`, ρ = 0.99, η ~ N(0, s²); μ is split f / (1-f) between overnight and intraday | Momentum has a real edge. `s` is calibrated so the honest TSMOM(60) long-short portfolio (N = 10, at the true cost) has a true annual Sharpe of 0.70 |
| `reversal` | `R[d] = e[d] + θ·e[d-1]`, θ = -0.02, with the θ·e[d-1] term split f / (1-f) | One-day reversal has a real *gross* edge that is negative after costs |
| `delisting` | `null` at 40% annual vol, N = 50; an asset is delisted after the first close below 30% of its start price | Zero edge across the full point-in-time universe. After delisting, the asset's returns are 0 and it cannot be held; the forced exit costs nothing |

**Defaults.** N = 10 (the asset picker uses N = 20). T = 2520 (10 years). The warm-up is 250 days, and
positions are 0 during warm-up. Reported returns cover days `[warmup, T)`. The true cost is 2 bps per
unit of turnover (a liquid, futures-style universe). All market parameters live in the config, and `scripts/calibrate.py` fits `s`.

## 3. Strategies and the backtest engine

**Strategy families.** Each strategy is per-asset and uses closes only. Positions are in {-1, 0, +1}, or
{0, +1} when `long_only`.

| Family | Rule | Grid |
|---|---|---|
| `tsmom(L)` | sign(Close/Close[-L] - 1) | L ∈ {5,10,15,20,30,40,60,90,120,180,250} |
| `ma(F,S)` | sign(MA_F - MA_S) | F ∈ {3,5,10,20,30,50}, S ∈ {40,60,100,150,200,250}, F < S |
| `rev(L)` | -sign(Close/Close[-L] - 1) | L ∈ {1,2,3,4,5,7,10} |
| `breakout(L)` | +1 at an L-day closing high, -1 at an L-day low, otherwise hold the last signal | L ∈ {10,20,50,100,150,200,250} |
| `level` | -sign(z) where z = (log Close - mean)/std, active when \|z\| > 0.5; mean and std are `expanding` (honest) or `full_sample` (leak) | used only by researcher 6 |
| `dip(D)` | long when the drawdown from the trailing 252-day high is at least D | used only by researcher 8 (D = 30%) |

The mining grid is the first four families × {long-short, long-only}, giving 120 specs.

**Implementation.** An `Implementation` holds four settings, and the honest implementation is
`(lag=1, cost=true_cost, universe=pit, scope=expanding)`:
- `lag`: 0 is the look-ahead bug, 1 is honest, 2 is the delay attack.
- `cost_bps`
- `universe`: `pit` means every asset, including delisted ones; `survivors` means the given dataset only.
- `scope`: used by the `level` family only.

**Execution.** A position `w[t]` decided at close t takes effect at the open of day `t+lag`. Day d earns
`w[d-lag-1]·Ron[d] + w[d-lag]·Rid[d] - cost·|w[d-lag] - w[d-lag-1]|`. The portfolio return is the mean of
these over the assets alive at the start of the day; assets that aren't alive contribute 0. With lag = 0,
the signal from close d earns `Rid[d]`, which leaks part of the information it was computed from.

## 4. Researchers (the matrix rows)

| # | id | Market | What it does | Trials disclosed |
|---|---|---|---|---|
| 1 | `honest_null` | null | pre-specified `tsmom(60)` long-short, honest | 1 |
| 2 | `honest_trend` | trend | the same as 1. **Real edge.** | 1 |
| 3 | `miner_null` | null | backtests all 120 grid specs honestly and reports the best in-sample Sharpe | 120 |
| 4 | `miner_trend` | trend | the same as 3; the oracle decides real or fake | 120 |
| 5 | `lookahead` | null | `tsmom(60)` with lag = 0 | 1 |
| 6 | `normaliser` | null | `level` with `scope=full_sample` | 1 |
| 7 | `cost_ignorer` | reversal | `rev(1)` long-short at 0 bps | 1 |
| 8 | `survivor` | delisting | `dip(30%)` long-only on the survivors-only dataset | 1 |
| 9 | `window_picker` | null | `tsmom(60)` from 11 start dates (every 126 days from `warmup`), reports the best | 11 (zero before each start) |
| 10 | `asset_picker` | null, N = 20 | `tsmom(60)` on each asset alone, reports the best asset | 20 |

Each researcher returns a `Claim`: the selection (spec, implementation, assets, start), the reported daily
returns, the trial-return matrix (T_eval × K), and its t-statistic. A run is a **claim** when t ≥ 2.0.

## 5. Ground truth (the oracle)

The true annual Sharpe of a selection is the **honest** implementation of its spec, on the market's full
asset count (one asset for the asset picker), evaluated on a huge fresh sample from the same market. The fresh sample is 64 or more
independent 10-year paths, simulated as one wide panel, which gives about 2,000 effective years with a
standard error of about 0.02.
- The value depends only on (market, spec, n_assets), so it is cached.
- The labels are: **FAKE** if the true Sharpe ≤ 0.05, **REAL** if ≥ 0.20, and **MARGINAL** otherwise.
  Marginal cases are reported but not scored.
- Window choice doesn't matter in stationary markets, and the asset picker's oracle is single-asset.

## 6. Audits (the matrix columns)

Every audit sees only the view its tier allows. It returns a continuous statistic plus a verdict: ACCEPT
means the edge is credible, REJECT means it isn't. All thresholds are fixed here. α = 0.05.

| Tier | id | Rule (REJECT when…) |
|---|---|---|
| 1 returns only | `psr` | PSR(SR\* = 0) < 0.95, with skew and kurtosis adjusted (BLdP 2012) |
| 1 | `dsr_assumed` | DSR < 0.95, assuming N = 100 trials and SR variance = 1/T |
| 2 trials disclosed | `dsr` | DSR < 0.95 with the true K and the empirical variance of trial SRs (K = 1 gives PSR) |
| 2 | `pbo` | PBO > 0.5 (CSCV, S = 16, 12,870 splits). N/A when K = 1 |
| 2 | `bonferroni` | min(1, K·p_best) ≥ 0.05, one-sided t-test p |
| 2 | `reality_check` | White's RC p ≥ 0.05 (stationary bootstrap, mean block 10, B = 500) |
| 2 | `spa` | Hansen's SPA (consistent; studentised by each trial's sample s.d.) p ≥ 0.05 (same bootstrap draws) |
| 3 re-run access | `placebo` | re-running the **whole workflow** on M = 49 sign-flipped copies of its own data; p = (1 + #{SR_j ≥ SR_obs})/50 > 0.05 |
| 3 | `delay` | selection re-run with lag + 1: t < 1.645 |
| 3 | `cost_stress` | selection re-run at 2 × the true cost: t < 1.645 |
| 3 | `pit_universe` | selection re-run on the point-in-time universe (delisted names added back): t < 1.645 |
| 3 | `holdout` | workflow re-run on the first 70% of the data, with its selection evaluated by its own pipeline on the last 30%: t < 1.645 |
| 3 | `forward_1y` | honest selection on 252 fresh days: t < 1.645 |
| 3 | `forward_3y` | the same on 756 fresh days |

"Re-run" means through the researcher's **own pipeline**, so its bugs come along. Only the forward tests
use the honest implementation, because live trading cannot see the future.

## 7. Protocol

1. **Dev config** (`configs/dev.toml`): about 30 claims per row, for debugging and timing. Dev results are
   never quoted.
2. **Final config** (`configs/final.toml`): 300 claims per row, with a run cap of 20,000 per row. Its
   SHA-256 is recorded in `docs/DECISIONS.md` before the run.
3. **`docs/PREDICTIONS.md` and `predictions.csv`**: the user's guesses for each cell, made before the final
   run. This is optional, but the report compares predictions with actual results when they're present.
4. **Final run**: executed once with `--final`. It writes `results/<run_id>/LOCK`, and the CLI refuses to
   overwrite a locked run.

## 8. Outputs

`results/<run_id>/` contains:
- `manifest.json`: the config hash, seed, versions and timings.
- `cases_<row>.jsonl`: one record per claim, holding the selection, reported SR and t, true SR, label, and
  every audit's statistic and verdict.
- `matrix.csv`: for each cell, the catch rate on FAKE claims and the false-alarm rate on REAL claims, with
  n and Wilson 95% CIs.
- `auc.csv`: for each audit and failure class, a threshold-free AUC separating that class's FAKE claims
  from all REAL claims.
- `report.html`: a self-contained heatmap, a per-tier summary, plain-English explanations of every row and
  column, and predictions versus actual results.

## 9. Verification (the code's own test suite)

- **Causality.** Under the honest implementation, perturbing data after day d leaves returns up to d
  unchanged. With lag 0 and with `full_sample` scope, the test detects the dependence, which proves the
  planted bugs are real.
- **Accounting.** Hand-computed examples check P&L, costs, lag semantics, delisting and warm-up.
- **Markets.** The null mean ≈ 0. Volatility clustering and fat tails are present. The trend and reversal
  signals match their design. Delisting keeps the full universe at zero edge.
- **Audits.** PSR and DSR match an independent Monte Carlo. PBO ≈ 0.5 on noise and ≈ 0 for a dominant real
  strategy. RC, SPA, Bonferroni and placebo reject at ≤ α (within MC error) under an exact null.
- **Oracle.** Honest strategies in null markets have a true Sharpe of about 0 minus costs.
- **Determinism.** The same seed gives identical case records.

## 10. Stack and layout

Python 3.14, using only numpy, scipy and pytest, in a venv with system site-packages. Runs are
parallelised across 16 cores with `multiprocessing`. The final run should take about 3 hours or less.

```
quant-red-team/
  qrt/  config markets strategies engine workflows oracle stats bootstrap audits/ experiment matrix report cli
  configs/  dev.toml final.toml
  scripts/  calibrate.py
  tests/
  docs/  DECISIONS.md PROJECT_STATE.md PREDICTIONS.md superpowers/
  results/   (gitignored)
```

## 11. Out of scope for v1

Real market data, any AI/LLM component, a strategy DSL, regime-switching markets, intraday data, and
effective-N clustering for DSR.

## 12. Changes made during the build (logged in `docs/DECISIONS.md`)

- **True cost: 10 bps → 2 bps (D5).** At 10 bps, honest TSMOM(60) in a random walk loses about 0.4
  Sharpe to costs, because the 60-day return keeps flipping sign. The honest-null and window-picker
  researchers then almost never claim (about 0.05% of runs), which would need about 600k runs for 300
  claims.
- **Reversal θ: -0.05 → -0.02 (D6).** This keeps the cost ignorer's edge real before costs (true SR
  +0.54) but negative after them (-0.13) at the new cost.
- **Trend `s` = 0.000125759 (D7)**, fitted with 256 oracle paths: the true SR is 0.700.
- **SPA studentisation (D8).** Each trial's sample s.d. is used instead of the bootstrap long-run s.d.
  The bootstrap estimate was noisy enough to oversize the test (11.7% at α = 5%, K = 20, T = 500). With
  the sample s.d. it measured 6.3%, which is within Monte Carlo error.
