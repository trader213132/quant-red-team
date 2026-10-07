# Quant Red Team

**Most people who try quant build a bot to find trading edges. This project builds the opposite: a
system that measures which audits catch fake edges.**

**Website: <https://trader213132.github.io/quant-red-team/>.** The interactive detection matrix and every
chart are built from the locked final run.

## Headline results (final run, 3,000 audited claims)

- **Statistical audits miss every coding or data flaw.** Tests on returns, or on all the trials, catch
  selection bias (~90%) but score **0%** on look-ahead, data leakage, ignored costs and survivorship.
- **Each of those flaws has its own cheap antidote:**
  - look-ahead: a one-day delay (96%);
  - leakage: a placebo re-run (95%);
  - costs: double the costs (100%);
  - survivorship: restore the delisted names (96%).
- **Some audits fail badly here.** The Probability of Backtest Overfitting is a coin flip as a verdict
  on one claim (AUC 0.50). The Deflated Sharpe rejects **100%** of genuine edges found by searching.
- **Honest luck is invisible without new data, and paper trading is slow.** One year rejects 79% of
  genuine Sharpe-0.7 edges, and 80% power takes about 12.6 years.

The full write-up is in [`docs/RESULTS.md`](docs/RESULTS.md); every decision is in
[`docs/DECISIONS.md`](docs/DECISIONS.md). The code was written with Claude (Anthropic); the decision log
records who decided what.

A backtest that looks brilliant can be fake in many ways: you tried 120 variants and kept the best,
your code peeked at the future, you forgot trading costs, your data only contains the companies that
survived... Statisticians have invented many tests to catch this: the Deflated Sharpe Ratio, the
Probability of Backtest Overfitting, White's Reality Check, Hansen's SPA, holdouts and placebo re-runs.
But **which test catches which flaw, how often does each wrongly reject a genuine edge, and how much
access does an auditor need?** In real markets nobody knows the true answer, so nobody can score them.

Here the markets are simulated, so the truth is known. Every simulated claim gets a ground-truth label
from an *oracle* that runs the same rule honestly on ~2,300 years of fresh data from the same market.

## The experiment

- **Four markets.** One with no edge (a fair random walk with fat tails and volatility clustering), one
  with a real hidden trend, one with a tiny reversal that costs destroy, and one where crashing stocks
  get delisted.
- **Ten researchers** (the rows), each a complete research process: honest ones, a parameter miner, a
  look-ahead bug, a full-sample normaliser, a cost ignorer, survivorship bias, a window picker and an
  asset picker.
- **Fourteen audits** (the columns), in three access tiers:
  1. **Returns only:** what a fund pitch shows you.
  2. **All trials disclosed:** what an honest paper shows you.
  3. **Re-run access:** a due-diligence team that can re-run the research with knobs turned.
- Only **claims** are audited, meaning backtests with t ≥ 2, because flawed research is only shown when it
  looks good.

The output is the **detection matrix**: the catch rate on fake claims and the false-alarm rate on real
ones for every (flaw, audit) pair, with 95% intervals. The full design is in
`docs/superpowers/specs/2026-10-07-detection-matrix-design.md`, and every decision is logged in
`docs/DECISIONS.md`.

## Running it

```bash
python -m venv --system-site-packages .venv      # needs numpy, scipy and pytest in that Python
.venv/Scripts/python.exe -m pytest               # fast tests (~20 s)
.venv/Scripts/python.exe -m pytest -m slow       # statistical calibration tests
.venv/Scripts/python.exe scripts/calibrate.py    # re-derive the market calibration
.venv/Scripts/python.exe -m qrt run --config configs/dev.toml          # dev run (~minutes)
.venv/Scripts/python.exe -m qrt predictions                            # blank predictions.csv
.venv/Scripts/python.exe -m qrt run --config configs/final.toml --final  # THE final run, once
.venv/Scripts/python.exe -m qrt report results/<run>                   # rebuild a report
```

Each run folder gets `report.html` (open it in a browser), `matrix.csv`, `auc.csv`, `oracle.json`, one
`cases_<researcher>.jsonl` per row and `manifest.json` (config and code hashes, versions, timings).

## Layout

| Path | What it is |
|---|---|
| `qrt/markets.py` | Simulated markets: GARCH + Student-t noise, with planted (or absent) edges |
| `qrt/strategies.py` | Trading rules and the 120-rule mining grid |
| `qrt/engine.py` | Backtests: timing (lag), costs, delistings, universe |
| `qrt/workflows.py` | The ten researchers |
| `qrt/oracle.py` | Ground truth |
| `qrt/audits/` | The fourteen audits, by tier |
| `qrt/experiment.py`, `matrix.py`, `report.py` | Run, aggregate and report |
| `tests/` | 84 tests, including the causality checks that prove the planted bugs are real |
| `site/` | The website (static HTML/JS); data exported by `scripts/export_site_data.py`, deployed by `.github/workflows/pages.yml` |
| `results/final/` | The locked final run: every audited claim, the oracle table, the matrix and the report |
