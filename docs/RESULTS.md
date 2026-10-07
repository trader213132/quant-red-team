# Results: Detection Matrix v1, its v2 replication, and a real-market case study

**Run:** `results/final/` (locked).
- Config hash `b39faa28…`, code hash at run time `a8897be1…`, seed 314159265.
- 300 audited claims per researcher, 3,000 in total, from 30,799 simulated 10-year markets. Ground truth
  comes from ~2,300 oracle years per rule.
- Every rate below has a Wilson 95% interval of roughly ±3–6 points. The report (`results/final/report.html`)
  shows all 140 cells with their intervals.

## In one paragraph

Statistical audits that look at returns, or at the full list of trials, catch **selection** (mining
parameters, picking assets), but they are **blind to every implementation flaw**: look-ahead, data
leakage, ignored costs and survivorship each scored 0%. Each of those flaws is caught almost perfectly
(95–100%) by **one cheap re-run attack, and it is a different attack every time**. No single audit catches
everything. Two things are close to uncatchable:
- an honest researcher who simply got lucky;
- a researcher who picked the best start date.

The only thing that exposes honest luck is new data, and new data is weak: **one year of honest paper
trading rejects 79% of genuine edges** with a true Sharpe of 0.7, and three years still rejects 62%.

## The findings

**1. Returns alone tell you almost nothing.** The Probabilistic Sharpe Ratio caught 0% of fakes, because
every claim already cleared t ≥ 2. The Deflated Sharpe with an *assumed* 100 trials "caught" 96–100% of
most flaws. It did this by raising the bar so high that it also rejected **91% of genuine honest edges**
and 75% of genuine mined ones. And it caught **0% of look-ahead**, because look-ahead produces spectacular
backtests (mean claimed Sharpe 3.48, true Sharpe -0.04) that clear any bar.

**2. Disclosing every trial fixes selection bias, and only selection bias.**
- On the 120-rule parameter miner: Bonferroni 96%, White's Reality Check 90%, Hansen's SPA 89%.
- On the asset picker: about 90%.
- Every tier-2 audit scored **0%** on look-ahead, the full-sample normaliser, the cost ignorer and
  survivorship. Those researchers each ran one test, so there is no multiplicity to correct.

**3. PBO cannot tell you whether a particular claim is fake.** The Probability of Backtest Overfitting
caught 25% of mined fakes and 8% of asset-picked fakes. Its threshold-free AUC was **0.50, a coin flip**.
- **Mechanism:** PBO asks how consistently the in-sample winner wins across 12,870 splits of the history.
  A strategy that was lucky across its whole history looks consistent, so PBO passes it.
- **What it actually measures:** the selection *procedure*, not whether *this* winner is real.

**4. The Deflated Sharpe with the true trial count flagged 100% of genuine mined edges.** In the trend
market, the 120 rules really differ (true Sharpes from -0.84 to +0.84). The DSR treats the spread of the
trial Sharpes as noise, so real differences between strategies push its bar above even genuinely good
strategies.

**5. Each implementation flaw has its own antidote, and none works across the board.**

| Flaw | What catches it | What misses it |
|---|---|---|
| Look-ahead | placebo 98%, delay 96% | holdout 0% (the leak is still there in the holdout) |
| Full-sample normaliser | placebo 95% | delay 0% (the leak is not about timing) |
| Ignored costs | cost × 2: 100%; delay 95% (a one-day edge dies with any lag) | placebo 8% (the gross edge is real, so randomised data doesn't reproduce it) |
| Survivorship | point-in-time universe 96% | placebo 4% (the bias is in the data, and the placebo copies the data) |

These attacks almost never false-alarm: delay 2%, cost stress and point-in-time 0%.

**6. The placebo (falsification) audit is the best all-rounder, but it has blind spots.** It caught
85–90% of selection flaws and 95–98% of leakage flaws. It is structurally blind to:
- data flaws (survivorship, 4%);
- economic flaws (costs, 8%);
- honest luck (4%).

It also wrongly rejected 22% of genuine mined edges.

**7. Window picking was the hardest selection flaw.** Choosing the best of 11 start dates turned zero
edge into a claimed Sharpe of 1.05. The usable audits caught at most 36% (Reality Check 36%, placebo 33%,
SPA 18%). Bonferroni caught 77%, but it sits on the false-alarm limit (20.2%). The 11 windows are near-
copies of one strategy, so the bootstrap tests see little multiplicity, yet the selection still inflates
the result.

**8. Honest luck is invisible without new data, and new data is slow.**
- About 1.6% of honest single tests in the no-edge market cleared t ≥ 2. No usable audit catches those
  (the best is delay at 24%).
- Forward testing catches 95%, but it cannot tell real from fake: one year of honest paper trading
  rejected **79%** of genuine Sharpe-0.7 edges, three years **62%**, and the 30% holdout 51%.
- **For any bot being paper-traded today**, this means a year of paper trading will not be able to
  confirm or refute it.

**9. The winner's curse hits real edges too.** Genuine mined edges were claimed at a Sharpe of 1.22
against a true 0.69. Honest real edges were claimed at 1.02 against a true 0.72, just from being filtered
through t ≥ 2.

## How much access does an auditor need?

The table counts only audits that wrongly reject at most 20% of genuine edges (decision D12).

| Flaw | Best usable audit | Access needed to catch ≥80% |
|---|---|---|
| Parameter miner | Reality Check 90% | Tier 2: trials disclosed |
| Asset picker | Reality Check 90% | Tier 2 |
| Look-ahead | Placebo 98% | Tier 3: re-run |
| Full-sample normaliser | Placebo 95% | Tier 3 |
| Cost ignorer | Cost × 2: 100% | Tier 3 |
| Survivorship | Point-in-time universe 96% | Tier 3 (needs better data, not better statistics) |
| Window picker | Reality Check 36% | Not reliably caught |
| Honest luck | Delay 24% | Not caught; only new data helps |

**Practical rule:** ask for every trial, and also re-run the pipeline with a delay, double costs, the
delisted names restored, and placebo data. Statistics on the returns alone will not save you.

## Caveats (what this does and doesn't show)

- **Simulated markets.** The ground truth is exact *for these markets*: GARCH + Student-t noise, one
  kind of planted edge each, and 2 bps costs. Real markets have regimes, crowding and structural breaks
  that v1 doesn't model.
- **The thresholds are the conventional ones, fixed before any run:** α = 5%, PBO > 0.5, DSR < 0.95, and
  attacks rejecting at t < 1.645. Other thresholds move the trade-off between catches and false alarms.
  The AUC table in the report compares the audits without thresholds.
- **One family of simple rules** (momentum, moving averages, reversal, breakout), with 300 claims per
  researcher.
- **Placebo uses 49 copies,** so its p-value is coarse, which makes it slightly conservative. It was
  validated: when there is truly no edge, it rejects ≤ 8% of the time.
- **The 20% false-alarm cap** in the access table was chosen after seeing the results (D12). It changes
  only the presentation, not any measurement.
- **Two versions of the code exist.** The report-rendering code was edited after the run (D12), so the
  current code hash differs from the run's hash. Simulations, audits and case records are untouched.

## Reproduce

```bash
.venv/Scripts/python.exe -m pytest -m "slow or not slow"     # 84 tests
.venv/Scripts/python.exe -m qrt report results/final         # rebuild matrix/report from locked cases
```


---

# v2: pre-registered follow-up (final run, 2026-10-07)

**Run:** `results/final-v2/` (locked).
- Config hash `d35a77ab…`, code hash `be2b188f…`, **fresh seed 271828182**.
- 3,000 new claims from 35,312 new simulated markets.
- The two new audits were designed after seeing v1. The hypotheses were written down before the run, in
  `superpowers/specs/2026-10-07-v2-preregistration.md`.

| Pre-registered hypothesis | Result | Verdict |
|---|---|---|
| **H1.** v1 replicates: ≥ 90% of cells within 10 points on a fresh seed | **134 / 134** cells within 10 points (largest gap 8) | **PASS** |
| **H2.** `dsr_eff` catches ≥ 80% of `miner_null` and `asset_picker` fakes, with ≤ 20% false alarms | asset picker **99.3%**, miner **70.3%** (95% CI 65–75%); false alarms **7.3%** pooled | **FAIL** (miner below the bar) |
| **H3.** `full_history` catches ≥ 80% of `window_picker` fakes, with ≤ 5% false alarms | **50.0%** caught (CI 44–56%); **0%** false alarms | **FAIL** |

**What v2 adds to the story**

1. **The v1 matrix is not a fluke of one seed.** Every cell replicated within sampling error.
2. **The Deflated Sharpe can be fixed, mostly.** v1's DSR rejected 100% of genuine mined edges because it
   read real differences between strategies as luck. Using the null variance 1/T, with correlated trials
   counted as an *effective* number (the participation ratio of the correlation eigenvalues):
   - false alarms on real mined edges fall from **100% to 15%**;
   - it still catches 99% of asset-pickers and 70% of parameter-miners.

   That makes it a *usable* audit, but on miners it is weaker than White's Reality Check (87%), so the
   hypothesis fails.
3. **Window picking is still the hardest flaw.** Re-running from the earliest date never wrongly rejects a
   real edge (0%), but it catches only half the window-pickers. The best start usually covers most of
   the history, so the lucky stretch is still inside the full-history backtest. No audit at a usable
   false-alarm rate reaches 80% on this flaw.

---

# Real-market case study (illustrative)

The same researchers and audits were run on **20 liquid US ETFs** (equity indices, regions, bonds, gold,
sectors), with Yahoo Finance daily data adjusted for splits and dividends, and 2 bps costs.
- **Research window:** 2005-01 → 2018-12 (3,523 days).
- **"Future":** 2019-01 → 2026-10 (1,951 days).

There is no oracle in real markets. Each claim's "truth" is its rule run honestly in the future: one draw
per researcher, so this is a story, not statistics. Equal-weight buy-and-hold of the 20 ETFs had a
Sharpe of 0.59 in the research window and 0.90 in the future.

| Researcher | Rule picked | Claimed Sharpe (t) | Clears t ≥ 2? | Audits rejecting | Future Sharpe |
|---|---|---|---|---|---|
| Look-ahead bug | TSMOM(60) with lag 0 | **1.33** (4.78) | yes | **2 / 14**: only placebo and delay | **−0.15** |
| Parameter miner | MA(30, 250) long-only | 0.81 (2.94) | yes | 6 / 14 | **0.70** |
| Asset picker | TSMOM(60) on LQD | 0.47 (1.69) | no | 10 / 14 | −0.14 |
| Cost ignorer | rev(1) at 0 bps | 0.33 (1.18) | no | 13 / 14 | 0.13 |
| Normaliser | full-sample level | 0.29 (1.05) | no | 13 / 14 | −0.95 |
| Window picker | TSMOM(60) | 0.15 (0.45) | no | 14 / 14 | −0.15 |
| Honest | TSMOM(60) | 0.10 (0.34) | no | 13 / 14 | −0.15 |

- **Look-ahead behaves exactly as the simulation predicts.** It produces the best-looking backtest in the
  study. Every returns-only and trials-disclosed audit passes it, only the two re-run attacks (placebo,
  delay) reject it, and it lost money afterwards.
- **The miner's pick was "real", but mostly market exposure.** A long-only trend filter really did keep
  working (0.70), yet it trailed simply holding all 20 ETFs (0.90). The audits split 8 to 6. The placebo
  rejects it because sign-randomised data has no upward drift, which is exactly the part of its return
  that came from the market rather than from timing.
- Most flawed researchers never even reach a publishable claim on real data at 2 bps. Real markets are
  harder to fool yourself in than they look, but look-ahead fools you every time.
