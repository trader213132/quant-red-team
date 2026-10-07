"""Re-run a sample of claims from each locked run with the current code and check every recorded number
matches. Stronger than comparing hashes: it shows the code reproduces the results.

Usage: .venv/Scripts/python.exe scripts/verify_runs.py [--per-row 3]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from qrt.config import load_config  # noqa: E402
from qrt.experiment import run_case  # noqa: E402
from qrt.matrix import load_cases  # noqa: E402

RUNS = {"final": "configs/final.toml", "final-v2": "configs/v2.toml"}


def same(a, b) -> bool:
    if isinstance(a, float) or isinstance(b, float):
        return a is not None and b is not None and math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12)
    return a == b


def check(args):
    run, cfg_path, case = args
    cfg = load_config(ROOT / cfg_path)
    oracle = json.loads((ROOT / "results" / run / "oracle.json").read_text())
    fresh = run_case(cfg, case["row"], case["run"], oracle)
    problems = []
    if fresh is None:
        return run, case["row"], case["run"], ["no claim on re-run"]
    for k in ("selection", "lag", "universe", "start", "n_trials", "t", "sharpe", "true_sharpe", "label"):
        if not same(case[k], fresh[k]):
            problems.append(f"{k}: {case[k]} != {fresh[k]}")
    for a, rec in case["audits"].items():          # v1 records hold 14 audits; compare those that were recorded
        for f in ("reject", "value"):
            if not same(rec[f], fresh["audits"][a][f]):
                problems.append(f"{a}.{f}: {rec[f]} != {fresh['audits'][a][f]}")
    return run, case["row"], case["run"], problems


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-row", type=int, default=3)
    args = ap.parse_args()
    jobs = []
    for run, cfg_path in RUNS.items():
        cases = load_cases(ROOT / "results" / run)
        for row in dict.fromkeys(c["row"] for c in cases):
            mine = [c for c in cases if c["row"] == row]
            picks = {0, len(mine) // 2, len(mine) - 1} if args.per_row >= 3 else {0}
            jobs += [(run, cfg_path, mine[i]) for i in sorted(picks)][: args.per_row]
    with Pool(16) as pool:
        results = pool.map(check, jobs)
    bad = [r for r in results if r[3]]
    for run, row, i, probs in bad:
        print(f"MISMATCH {run} {row} run {i}: {probs[:3]}")
    print(f"{len(results) - len(bad)}/{len(results)} re-run claims reproduce every recorded number exactly")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
