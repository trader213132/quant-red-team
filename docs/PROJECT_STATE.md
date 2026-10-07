# Project state (handoff)

**Read this first in any new session or on another device.** The newest status is at the top. The
decision log is `docs/DECISIONS.md`.

## Latest: 2026-10-07 (session 1, end): project complete

**Status: the whole plan is done.** v1, the v2 replication, the real-market case study, the paper and the
website are all finished and published.

| Piece | Where | State |
|---|---|---|
| v1 detection matrix | `results/final/` (LOCK) | 3,000 claims, 14 audits |
| v2 pre-registered follow-up | `results/final-v2/` (LOCK), `superpowers/specs/2026-10-07-v2-preregistration.md` | H1 pass, H2 fail, H3 fail (D17) |
| Real-market case study | `scripts/real_case_study.py`, `site/data/real-case.json` | Done. Raw data in `data/` is local only (D18) |
| Trading-bot red-team | `private/` (gitignored) | Done and **private** (D19) |
| Paper | `docs/paper/quant-red-team.pdf` (also `site/paper/`) | 6 pages (D20) |
| Website | <https://trader213132.github.io/quant-red-team/> | All exhibits A–J, v1/v2 toggle |
| Tests | `pytest -m "slow or not slow"` | 94 pass |
| Reproducibility | `scripts/verify_runs.py` | 60/60 sampled locked claims reproduce exactly (D21) |

**To rebuild after any change:**
1. `scripts/real_case_study.py`
2. `scripts/export_site_data.py`
3. `scripts/make_paper.py`
4. Commit and push; the site redeploys automatically.

**What's left is for the user, not the code.**
- Understand and defend the results: "quiz me".
- Optionally: put a name on the paper's author line; decide whether to publish the trading-bot red-team;
  enter something like CREST Gold with the paper.

Possible future research (each needs a new versioned config and DECISIONS entry, and must never touch
`final` or `final-v2`):
- an audit that reliably catches window picking;
- `dsr_eff` combined with the Reality Check;
- regime-switching markets;
- more strategy families.

## Rules for working on this project

- **Ownership:** Claude writes all the code (D2). Keep the docs and report educational, because the user
  must be able to explain every result.
- **Git:** the repo is public on GitHub. Commit and push only when the user asks, or when it's needed for a task they asked for (like updating the website).
- **Never re-run the final, and never tune anything after seeing final results.** Any change after the
  final run means a new versioned config and a new run, both logged in DECISIONS.
- **Environment:** Python 3.14 venv with `--system-site-packages`, which needs numpy, scipy and pytest
  in the system Python. On Windows, run the CLI from the project root.
- **Syncing:** if the folder syncs between machines, use one machine at a time.
