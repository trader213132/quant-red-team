# Detection Matrix v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use superpowers:executing-plans (inline) to implement this plan
> task by task. Steps use checkbox (`- [ ]`) syntax for tracking. This plan pins down interfaces, behaviours
> and tests. The code is written directly into the files test-first, because the planner is also the
> executor. **No git commits unless the user asks** (standing project rule).

**Goal:** build the experiment described in `docs/superpowers/specs/2026-10-07-detection-matrix-design.md`.
It covers simulated markets, ten researchers (honest and flawed), an oracle, and fourteen audits in three
access tiers. The output is a detection matrix with catch and false-alarm rates.

**Architecture:** this is a pure-numpy simulation pipeline: `markets` → `strategies` → `engine` →
`workflows` → `audits`, with `oracle` providing ground truth. `experiment` fans runs out across 16
processes and streams case records to JSONL. `matrix` and `report` aggregate the records. Tiers are
enforced by construction: each audit receives only a view object for its tier.

**Tech stack:** Python 3.14, numpy 2.4, scipy 1.18, pytest 9.1, `tomllib`, and `multiprocessing`.

Commands use the project venv: `.venv/Scripts/python.exe -m pytest ...`

---

## File map

| File | Responsibility |
|---|---|
| `pyproject.toml`, `.gitignore`, `README.md` | Package metadata (`qrt`), pytest config (marker `slow`); ignore `results/`, `.venv/` |
| `qrt/config.py` | `load_config(path) -> Config` (frozen dataclasses), `config_hash(cfg)`, `code_hash()` |
| `qrt/markets.py` | `MarketSpec`, `Market` (r_on, r_id, alive; `close`, `subset`, `slice_days`, `flip`), `simulate(spec, rng, n_assets=None, n_days=None)` |
| `qrt/strategies.py` | `StrategySpec(family, params, long_only)`, `.key`, `positions(spec, close, scope)`, `rolling_max/min`, `MINING_GRID` (120) |
| `qrt/engine.py` | `Implementation`, `Selection`, `Dataset` (market, survivors), `contributions(...)`, `portfolio(...)`, `backtest(sel, ds) -> returns` |
| `qrt/stats.py` | `sharpe`, `annual_sharpe`, `t_stat`, `p_one_sided`, `moments`, `psr`, `expected_max_sr`, `wilson_ci`, `auc` |
| `qrt/bootstrap.py` | `stationary_counts(T, B, mean_block, rng) -> (B,T)` |
| `qrt/workflows.py` | `Claim`, the `FixedResearcher`, `Miner`, `WindowPicker` and `AssetPicker` classes, `build_researchers(cfg)` |
| `qrt/oracle.py` | `true_sharpe(...)`, `build_oracle_table(cfg, researchers, workers)`, `label(sr, cfg)` |
| `qrt/audits/__init__.py` | `AuditResult`, `Tier1View`, `Tier2View`, `Tier3Context`, the `AUDITS` registry (id → tier, fn), `run_audits(...)` |
| `qrt/audits/tier1.py`, `tier2.py`, `tier3.py` | The audits from spec §6 |
| `qrt/experiment.py` | `run_case(...)`, `run_row(...)`, `run_experiment(cfg, out_dir, workers, final)` |
| `qrt/matrix.py` | `load_cases(dir)`, `build_matrix(cases) -> rows`, `build_auc(cases)`, CSV writers |
| `qrt/report.py` | `write_report(run_dir)` → self-contained `report.html` |
| `qrt/cli.py`, `qrt/__main__.py` | `python -m qrt run|report|oracle` |
| `scripts/calibrate.py` | Fits trend `s` to a true Sharpe of 0.7 and prints the reversal gross/net figures |
| `configs/dev.toml`, `configs/final.toml` | Parameters from spec §2–§7 |
| `docs/DECISIONS.md`, `docs/PROJECT_STATE.md`, `docs/PREDICTIONS.md`, `predictions.csv` | Decision log, handoff, user predictions |

---

### Task 1: Scaffold
- [ ] Create a venv with system site-packages, then add `pyproject.toml` (`[tool.pytest.ini_options]`
  markers = slow, `addopts = "-m 'not slow'"`), `.gitignore`, a README stub and `qrt/__init__.py`.
- [ ] Verify: `.venv/Scripts/python.exe -c "import qrt, numpy, scipy"` exits 0.

### Task 2: Config
- [ ] Test (`tests/test_config.py`):
  - `load_config("configs/dev.toml")` returns `Config` with `.markets["null"].kind == "null"`.
  - `config_hash` is stable across two loads and changes when one value changes (use a tmp TOML).
- [ ] Implement:
  - The dataclasses `MarketSpec`, `AuditParams`, `RunParams` and `Config(seed, warmup, true_cost_bps,
    claim_t, alpha, fake_max, real_min, markets, researchers, audits, run, oracle_paths)`.
  - `config_hash` is the SHA-256 of canonical JSON.
  - `code_hash` is the SHA-256 over the sorted `qrt/**/*.py` bytes.

### Task 3: Markets
- [ ] Tests (`tests/test_markets.py`):
  - Shapes are (T, N). `close[0] = (1+r_on[0])(1+r_id[0])`.
  - The same seed gives identical arrays.
  - Null: the pooled mean of R over 200k asset-days has |t| < 4, the autocorrelation of |R| at lag 1 is
    > 0.05 (clustering), and the kurtosis is > 4.
  - Trend (large `s`): the correlation between the sign of the trailing 60-day return and the next-day
    return is > 0.
  - Reversal: the lag-1 autocorrelation of R is ≈ θ/(1+θ²), within ±0.02, over 500k samples.
  - Delisting: after the first close below 0.3, the returns are 0 and `alive` is False from the next day;
    `alive` never becomes True again.
  - `subset`, `slice_days` and `flip` preserve |returns|; `flip` changes signs ~50% of the time.
- [ ] Implement `simulate` (GARCH loop over days, vectorised over assets, t shocks clipped at ±20, σ cap,
  overnight/intraday split, trend μ AR(1), reversal MA term, delisting post-pass).

### Task 4: Strategies
- [ ] Tests (`tests/test_strategies.py`):
  - `rolling_max` and `rolling_min` equal a naive loop on random data for L ∈ {1, 3, 10}.
  - `tsmom(2)` on a hand-made close series gives the expected signs, with zeros where t < L.
  - `ma(2,3)` equals hand-computed values.
  - `breakout` holds the last signal.
  - `level` with `full_sample` differs from `expanding`.
  - `dip(0.3)` is long exactly when the drawdown is ≥ 30%.
  - `long_only` clips at 0.
  - `len(MINING_GRID) == 120` and the keys are unique.
- [ ] Implement using cumsum moving averages, `scipy.ndimage.maximum_filter1d` and `minimum_filter1d` with
  a trailing origin (verified by the naive test), a breakout ffill via the `maximum.accumulate` index
  trick, and the expanding mean/std via cumsums.

### Task 5: Engine
- [ ] Tests (`tests/test_engine.py`):
  - **Accounting:** for 1 asset and 5 days with given r_on/r_id and given w, the returns equal the hand
    formula `w[d-lag-1]·Ron[d] + w[d-lag]·Rid[d] - c·|Δ|` for lags 0, 1 and 2, including costs.
  - **Warm-up:** positions before `start-1` are ignored, and the returned length is `T - start`.
  - **Delisting:** a dead asset contributes 0, the forced exit costs nothing, and the divisor is
    `n_alive`.
  - **Universe:** `survivors` drops delisted assets; `assets=(k,)` selects one column of the view.
  - **Causality (the key test):** on a null market, for the honest `tsmom(60)` and the honest `level`,
    replacing every r_on/r_id from day d+1 onwards with new noise leaves `backtest(...)[: d+1-start]`
    identical. For `lag=0` the returns *up to* d change, because the intraday return on day d feeds the
    signal; the test asserts that difference. The same applies to `scope=full_sample`.
- [ ] Implement `Implementation(lag=1, cost_bps=10.0, universe="pit", scope="expanding")`,
  `Selection(spec, impl, assets=None, start=250)`, `Dataset(market, survivors)` with `view(universe)`,
  `slice_days` and `flipped(rng)`, `contributions(w, market, lag, cost_bps)`,
  `portfolio(contrib, alive, group)`, and `backtest`.

### Task 6: Stats and bootstrap
- [ ] Tests (`tests/test_stats.py`, `tests/test_bootstrap.py`):
  - `t_stat` equals scipy `ttest_1samp`.
  - `psr` at SR\*=0 for normal data is ≈ Φ(t) within 0.01.
  - `expected_max_sr(N=1)` == 0, and for N=100 it lies within 5% of the Monte Carlo mean of the max of
    100 standard normals × √V.
  - `wilson_ci(0,10)` has lo = 0 and hi ≈ 0.2775; `wilson_ci(5,10)` ≈ (0.2366, 0.7634).
  - `auc` of perfectly separated scores = 1 and of identical scores = 0.5.
  - In the bootstrap, each row's counts sum to T, the mean count is 1, and the counts are deterministic
    for a seed.
  - With mean block 10, the average run length of consecutive indices is ≈ 10 (±2).
- [ ] Implement them.

### Task 7: Workflows
- [ ] Tests (`tests/test_workflows.py`):
  - `FixedResearcher` returns trials with shape (T_eval, 1) equal to the returns.
  - `Miner` picks the argmax Sharpe column, and its trials have shape (T_eval, 120).
  - `WindowPicker`'s reported returns start at the chosen start, its trials are zero before each start,
    and it handles truncated data (only starts ≤ T-252).
  - `AssetPicker`'s trials have shape (T_eval, N) and its selection has `assets=(k,)`.
  - The survivor researcher's view excludes delisted assets.
  - `build_researchers(cfg)` gives 10 ids in the spec order.
- [ ] Implement `Claim(selection, returns, trials, trial_index, t_stat, sharpe)` and the researchers.

### Task 8: Oracle
- [ ] Tests (`tests/test_oracle.py`):
  - Honest `tsmom(60)` in null has a true SR in (-0.15, 0.05).
  - `rev(1)` in reversal with 0 bps is > 0 but < 0 at 10 bps.
  - `dip` on the PIT delisting universe has |SR| < 0.1.
  - `label` thresholds work.
  - The results are deterministic.
- [ ] Implement a wide-panel simulation (paths × n_assets columns) and a grouped portfolio, with the
  table keyed by `market|spec.key|n_assets`.

### Task 9: Calibration script
- [ ] `scripts/calibrate.py`: bisection on trend `s` until the oracle SR of honest TSMOM(60)/LS (N=10)
  is 0.70 ± 0.02. It also reports `rev(1)` gross/net in reversal and the survivor claim rate. Write the
  numbers into both configs and `docs/DECISIONS.md`.

### Task 10: Audits, tiers 1 and 2
- [ ] Tests (`tests/test_audits_tier12.py`):
  - The views expose only their fields: `Tier1View` has no `trials` attribute.
  - `psr` and `dsr_assumed` follow the formulas on fixed data.
  - `dsr` with K=1 equals `psr`.
  - `pbo` is in [0.35, 0.65] on 120 pure-noise trials (averaged over 5 seeds) and < 0.1 when one
    column has a strong drift; it is N/A for K=1.
  - The Bonferroni adjusted p equals min(1, K·p).
  - The `reality_check` and `spa` p-values are uniform-ish: under 40 exact-null draws of 20 noise trials
    the rejection-of-H0 rate is ≤ 0.15. **Slow test:** at 300 draws, size ≤ 0.08.
- [ ] Implement them: the CSCV via the 12,870 × 16 combination matrix with block sums and sums of squares,
  and RC/SPA from shared bootstrap counts.

### Task 11: Audits, tier 3
- [ ] Tests (`tests/test_audits_tier3.py`):
  - `delay` on the look-ahead researcher rejects (t collapses).
  - `cost_stress` on the cost ignorer rejects.
  - `pit_universe` on a non-delisting market returns the same t as reported.
  - `holdout` calls the workflow on truncated data.
  - `forward_*` uses the honest implementation on fresh data of the right length.
  - `placebo` gives p ≤ 0.04 for a planted huge real edge, and gives p large for the look-ahead
    researcher (its placebo SRs are also huge).
  - **Slow test:** the placebo size on unconditional honest_null is ≤ 0.08.
- [ ] Implement them, with determinism from the context rng.

### Task 12: Experiment runner
- [ ] Tests (`tests/test_experiment.py`): `run_case` is deterministic for a seed and returns None when no
  claim is made. A tiny config (2 rows, target 3 claims, 2 workers) writes `cases_<row>.jsonl` with 3
  records each, and gives identical output for 1 worker and 2 workers. `--final` refuses when a LOCK
  exists.
- [ ] Implement: ordered batches through `Pool.imap`, keeping the first `target` claims by run index; the
  manifest; the LOCK.

### Task 13: Matrix and report
- [ ] Tests (`tests/test_matrix.py`, `tests/test_report.py`): synthetic records give the right
  counts/rates/CIs, N/A verdicts are excluded, MARGINAL claims are excluded from rates, and the AUC is
  correct. The report writes HTML containing every row and audit id, and works without predictions.
- [ ] Implement them.

### Task 14: CLI, configs, dev run
- [ ] Add `python -m qrt run --config configs/dev.toml --workers 16`. Check the timings, sanity-read the
  matrix (look-ahead caught by delay and placebo; honest_trend mostly accepted by the PSR), and fix any
  bugs found (each fix gets a regression test).
- [ ] Freeze `configs/final.toml`. Record its hash and the code hash in `docs/DECISIONS.md`.

### Task 15: Docs and handoff
- [ ] Write `docs/PROJECT_STATE.md` (handoff), `docs/DECISIONS.md` (D1…), `docs/PREDICTIONS.md` plus the
  `predictions.csv` template (blank cells), and the README (what it is, how to run, how to read the
  matrix).
- [ ] The final run happens only after the user has had the chance to fill in predictions. It runs once
  with `--final`.
