# Decision log

Every decision that shapes the results, who made it, and why. Never edit old entries. Add new ones.

| # | Date | Who | Decision | Why |
|---|---|---|---|---|
| D1 | 2026-10-06 | User (Claude recommended) | The flagship is **Quant Red Team**; ARGUS and LedgerProof are shelved | Pure maths/statistics/CS, costs £0, needs no hardware. Origin story: a trading-bot project where 134k backtested trades felt like proof - the question was why it isn't. |
| D2 | 2026-10-06 | User | **Claude writes all the code** (the user chose this over writing it themselves, reference-then-rebuild, or teach-as-we-go) | It's the user's call. Consequence: the reports and docs are written to teach, so the results can be explained without reading the code. |
| D3 | 2026-10-07 | User | v1 = **detection matrix** (not a red-team tool first, and not attacking the trader first) | It's the core research result and needs no real data. |
| D4 | 2026-10-07 | Claude (delegated: "do whats needed") | Approach A: audit **whole workflows** with tiered auditor access. Full design in `superpowers/specs/2026-10-07-detection-matrix-design.md`. Fixed before any run: α = 0.05, claim bar t ≥ 2, PBO rejects at > 0.5, re-run attacks reject at t < 1.645, and the oracle labels FAKE ≤ 0.05 and REAL ≥ 0.20 | Flaws such as look-ahead, survivorship and ignored costs live in the process, not the returns, so only a workflow-level design can represent them. |
| D5 | 2026-10-07 | Claude | True cost **10 → 2 bps** per unit of turnover | At 10 bps, honest TSMOM(60) loses about 0.4 Sharpe in a random walk because the 60-day sign keeps flipping. The honest-null and window-picker researchers would then claim in about 0.05% of runs, needing ~600k runs for 300 claims. 2 bps is realistic for a liquid futures-style universe. |
| D6 | 2026-10-07 | Claude | Reversal θ **-0.05 → -0.02** | At 2 bps, θ = -0.05 would make the cost ignorer's edge genuinely profitable. With θ = -0.02 the oracle gives a gross SR of +0.54 and a net SR of -0.13, so it is FAKE after costs, as designed. |
| D7 | 2026-10-07 | Claude | Trend market `trend_s = 0.000125759` | Fitted by `scripts/calibrate.py` with 256 oracle paths: honest TSMOM(60) has a true SR of 0.700. A 128-path fit was off by 0.07, so 256 paths are used. |
| D8 | 2026-10-07 | Claude | **SPA** is studentised by each trial's sample s.d. | The block-bootstrap long-run s.d. oversized SPA (11.7% at α = 5%, K = 20, T = 500). With the sample s.d. it measured 6.3%, within Monte Carlo error. Daily strategy returns are serially uncorrelated here, so the sample s.d. is consistent. RC measured 6.0%. |
| D9 | 2026-10-07 | Claude | The final seed (314159265) **differs from the dev seed** (20261007) | With the same seed, the dev claims would be the first claims of the final run, so dev peeking would leak into the final sample. |
| D10 | 2026-10-07 | Claude | No change: the placebo audit's ~95% catch rate on look-ahead is **correct behaviour, not a bug** | Look-ahead leaks just as much on sign-flipped data, so the placebo p-value is uniform (measured over 64 seeds: mean p 0.46, rejection rate 95.3%). |
| D11 | 2026-10-07 | Claude | **Froze the final run** before launching it: `configs/final.toml` has config hash `b39faa28bb08e7b6…` (file SHA-256 `be0460481fed4a95…`) and code hash `a8897be10c6d0ab2…`, with all 84 tests passing. Dev run `results/dev-1` reviewed for bugs only; none found, and no thresholds were changed | Pre-commitment: anything changed after this point needs a new versioned config and run. |
| D12 | 2026-10-07 | Claude | **After** the final run, the report's access table counts only audits whose pooled false-alarm rate on REAL claims is ≤ 20%. Excluded: DSR(100) 83.0%, DSR 50.0%, PBO 26.0%, Bonferroni 20.2%, holdout 59.5%, forward 1y 78.7%, forward 3y 64.7%. Only `qrt/report.py` changed; locked cases are untouched, and the code hash now differs from the run's | Without the cap, the table credited DSR(100) and the forward tests with catching nearly everything, when they do it only by rejecting almost everything, real edges included. This is labelled post-hoc everywhere it appears. |
| D13 | 2026-10-07 | Claude | Before the public GitHub release, the wording of D1/D2 and a few docs was neutralised to remove personal context. The substance of every decision is unchanged | Privacy: the repository is public. |

## Calibration facts (dev config, `scripts/calibrate.py`, 2026-10-07)

| Quantity | Value |
|---|---|
| Honest TSMOM(60) in the null market | gross SR -0.03 (≈0, the martingale check passes), net -0.11 |
| `rev(1)` in the reversal market | gross +0.54, net -0.13 |
| `dip(30%)` on the point-in-time delisting universe | gross -0.03, net -0.07 |
| Claim rates (t ≥ 2) | honest_null 1.3% · honest_trend 60% · miner_null 25% · miner_trend 96% · lookahead 100% · normaliser 97% · cost_ignorer 38% · survivor 72% · window_picker 4% · asset_picker 35% |
