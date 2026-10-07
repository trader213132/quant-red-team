"""Calibrate the planted edges and estimate claim rates.

1. Fits the trend market's hidden-drift noise `s` so the honest TSMOM(60) long-short portfolio has a
   true annual Sharpe of 0.70 (after the configured true cost).
2. Prints the oracle for the reversal and delisting markets (gross vs net).
3. Estimates how often each researcher's backtest clears the claim bar (sizes `max_runs`).

Usage: .venv/Scripts/python.exe scripts/calibrate.py [--config configs/dev.toml] [--runs 200]
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from multiprocessing import Pool
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qrt.config import load_config  # noqa: E402
from qrt.engine import Dataset  # noqa: E402
from qrt.markets import simulate  # noqa: E402
from qrt.oracle import oracle_key, oracle_sharpes  # noqa: E402
from qrt.strategies import StrategySpec  # noqa: E402
from qrt.workflows import build_researchers  # noqa: E402

TARGET = 0.70
TSMOM60 = StrategySpec("tsmom", (60,))


def trend_sr(cfg, s: float, paths: int) -> float:
    c = replace(cfg, markets={**cfg.markets, "trend": replace(cfg.markets["trend"], trend_s=s)})
    return oracle_sharpes(c, "trend", 10, [TSMOM60], paths=paths)[oracle_key("trend", TSMOM60, 10)]


def fit_trend(cfg) -> float:
    lo, hi = np.log(1e-5), np.log(3e-3)
    for _ in range(14):
        mid = (lo + hi) / 2
        if trend_sr(cfg, float(np.exp(mid)), paths=cfg.oracle_paths) < TARGET:
            lo = mid
        else:
            hi = mid
    return float(np.exp((lo + hi) / 2))


def claim_rate(args):
    cfg, rid, runs = args
    r = build_researchers(cfg)[rid]
    rng = np.random.default_rng([cfg.seed, 777, len(rid)])
    hits = 0
    for _ in range(runs):
        ds = Dataset.from_market(simulate(cfg.markets[r.market], rng))
        hits += r.run(ds).t_stat >= cfg.claim_t
    return rid, hits / runs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/dev.toml")
    ap.add_argument("--runs", type=int, default=200)
    args = ap.parse_args()
    cfg = load_config(args.config)

    s = fit_trend(cfg)
    print(f"trend_s = {s:.6g}  ->  true SR(TSMOM60) = {trend_sr(cfg, s, paths=cfg.oracle_paths):.3f} "
          f"({cfg.oracle_paths} paths)")
    cfg = replace(cfg, markets={**cfg.markets, "trend": replace(cfg.markets["trend"], trend_s=s)})

    free = replace(cfg, true_cost_bps=0.0)
    rev1 = StrategySpec("rev", (1,))
    dip = StrategySpec("dip", (0.3,), long_only=True)
    for name, n, spec in (("reversal", 10, rev1), ("delisting", 50, dip), ("null", 10, TSMOM60)):
        g = oracle_sharpes(free, name, n, [spec], paths=64)[oracle_key(name, spec, n)]
        net = oracle_sharpes(cfg, name, n, [spec], paths=64)[oracle_key(name, spec, n)]
        print(f"{name:10s} {spec.key:16s} gross {g:+.3f}  net({cfg.true_cost_bps:g}bps) {net:+.3f}")

    with Pool(16) as pool:
        for rid, rate in pool.imap(claim_rate, [(cfg, rid, args.runs) for rid in cfg.researchers]):
            print(f"claim rate {rid:14s} {rate:6.1%}")


if __name__ == "__main__":
    main()
