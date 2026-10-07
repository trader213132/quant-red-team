# Project state (handoff)

**Read this first in any new session or on another device.** The newest status is at the top. The
decision log is `docs/DECISIONS.md`.

## Latest: 2026-10-07 (session 1, end)

**Status: v1 is complete. The final run is done and locked in `results/final/`, and the findings are
written up in `docs/RESULTS.md`.**

- 84 tests pass (fast + slow). The dev run is in `results/dev-1/` and must not be quoted.
- The final run took 9 minutes on 16 cores: 3,000 audited claims from 30,799 simulated markets.
- The report is `results/final/report.html` (self-contained, so it opens in any browser).
- After the run, the report gained a 20% false-alarm cap in its access table (D12, presentation only).

Possible next steps (v2; each needs a new config and a DECISIONS entry, and must never touch `final`):
1. **Real data:** run the re-run attacks (delay, cost×2, placebo) on real ETF data with known-bad and
   known-good strategies. There's no oracle there, so it becomes a case study.
2. **Attack a real trading bot:** treat an existing bot as a researcher and run tier-3 attacks on it.
   RESULTS finding 8 already says a year of paper trading can't validate it.
3. **Fix the DSR finding:** use effective-N / clustered trials and see whether it stops false-alarming on
   real mined edges.
4. **Window picker:** find an audit that catches it (for example, a start-date placebo).
5. **Write-up:** a 4–6 page paper (CREST Gold-style) from RESULTS.md, plus figures from matrix.csv and
   auc.csv.

## Rules for working on this project

- **Ownership:** Claude writes all the code (D2). Keep the docs and report educational, because the user
  must be able to explain every result.
- **No git commits** unless the user asks. The repo is initialised but has no commits.
- **Never re-run the final, and never tune anything after seeing final results.** Any change after the
  final run means a new versioned config and a new run, both logged in DECISIONS.
- **Environment:** Python 3.14 venv with `--system-site-packages`, which needs numpy, scipy and pytest
  in the system Python. On Windows, run the CLI from the project root.
- **Syncing:** if the folder syncs between machines, use one machine at a time.
