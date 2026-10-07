# Quant Red Team v2: pre-registration

Written 2026-10-07, **before** any v2 run. v1 (`results/final`) is locked and is not touched.

## What v2 adds

v1 exposed three failures. Two new audits target them, designed after seeing v1 and labelled that way
everywhere. They are tested on **fresh data**, a new seed, so they cannot be tuned to v1's specific
claims.

| New audit | Tier | Targets v1 failure | Rule (REJECT when…) |
|---|---|---|---|
| `dsr_eff`: Deflated Sharpe, effective-N | 2 | v1's DSR rejected 100% of genuine mined edges | DSR < 0.95, where the bar is the expected maximum Sharpe of **N_eff independent zero-edge trials** with the **null** Sharpe variance 1/T. N_eff = (Σλ)² / Σλ², the participation ratio of the eigenvalues of the trials' correlation matrix. K = 1 reduces to the PSR. |
| `full_history` | 3 | Window picking was caught ≤ 36% by any usable audit | The claimed rule, re-run through the researcher's own pipeline from the **earliest date the data allows** (`start = warmup`), has t < 1.645 |

**Why `dsr_eff` should help.** v1's DSR estimated the bar from the cross-trial *spread* of Sharpe ratios.
When trials genuinely differ, that spread is mostly real signal, so the bar becomes too high. Under the
null hypothesis every trial's true Sharpe is 0, so the right variance is the *estimation* variance, about
1/T. Correlated trials are not independent tries, so their count is reduced to an effective number.

## Run

`configs/v2.toml` is `configs/final.toml` with exactly one change: **seed 271828182**. It has the same
markets, researchers, thresholds and sample sizes, plus the 16 audits (14 from v1 + 2 new). It runs
once with `--final`, which writes `results/final-v2/` with a LOCK.

## Hypotheses (decided now, scored after the run)

- **H1, replication.** v1's matrix replicates on a fresh seed: in at least 90% of applicable
  (researcher × v1-audit) cells, the v2 rate is within 10 percentage points of v1. (With 300 claims per
  cell, the standard error of a difference is ≤ 4 points.)
- **H2, `dsr_eff` fixes the DSR.** It catches ≥ 80% of fakes from both `miner_null` and `asset_picker`,
  and its pooled false-alarm rate on REAL claims is ≤ 20%.
- **H3, `full_history` catches window picking.** It catches ≥ 80% of `window_picker` fakes, with a
  pooled false-alarm rate on REAL claims ≤ 5%.

Each hypothesis is reported as pass or fail, whatever the result. Nothing in v2 is re-run or re-tuned
after its results are seen.

## Real-market case study (separate, illustrative)

The same researchers and audits are run on **real daily data for 20 liquid US ETFs**: 2005–2018 is the
"research" window and 2019 to the latest date is the "future". There is no oracle, so the "truth"
is each claimed rule's honest performance in the future window. That is n = 1 per researcher, so it is
reported as a case study, not as statistics.
- The forward tests are replaced by the real future.
- The survivorship researcher is not applicable, because the ETF list has no delistings.
- Raw Yahoo data is not redistributed; only derived results are published.
