"""Ground truth. The true annual Sharpe of a claimed rule is what its HONEST implementation earns on a
huge fresh sample from the same market (hundreds of independent 10-year paths, ~2,300 years).

It depends only on (market, rule, number of assets), so it is computed once per run, before any claim
is audited. Audits never see it.
"""

from __future__ import annotations

import zlib
from collections import defaultdict
from multiprocessing import Pool

import numpy as np

from qrt import TRADING_DAYS
from qrt.config import Config
from qrt.engine import Dataset, Selection, backtest, honest_implementation
from qrt.markets import simulate
from qrt.strategies import StrategySpec

MAX_COLUMNS = 2560   # assets simulated at once (memory bound)


def oracle_key(market: str, spec: StrategySpec, n_assets: int) -> str:
    return f"{market}|{spec.key}|{n_assets}"


def label(true_sr: float, cfg: Config) -> str:
    if true_sr <= cfg.fake_max:
        return "FAKE"
    if true_sr >= cfg.real_min:
        return "REAL"
    return "MARGINAL"


def oracle_sharpes(cfg: Config, market: str, n_assets: int, specs: list[StrategySpec],
                   paths: int | None = None) -> dict[str, float]:
    """True annual Sharpe of each rule (honest implementation) in `market` with `n_assets` assets."""
    paths = paths or cfg.oracle_paths
    mspec = cfg.markets[market]
    impl = honest_implementation(cfg.true_cost_bps)
    rng = np.random.default_rng([cfg.seed, zlib.crc32(f"oracle|{market}|{n_assets}".encode())])
    per_chunk = max(1, MAX_COLUMNS // n_assets)
    acc = {s.key: np.zeros(3) for s in specs}       # running count, sum, sum of squares
    done = 0
    while done < paths:
        k = min(per_chunk, paths - done)
        ds = Dataset.from_market(simulate(mspec, rng, n_assets=n_assets * k))
        for s in specs:
            r = backtest(Selection(s, impl, None, cfg.warmup), ds, group=n_assets).ravel()
            acc[s.key] += (r.size, r.sum(), (r * r).sum())
        done += k
    out = {}
    for s in specs:
        n, total, sq = acc[s.key]
        mean = total / n
        sd = np.sqrt(max(sq / n - mean * mean, 0.0) * n / (n - 1))
        out[oracle_key(market, s, n_assets)] = float(mean / sd * np.sqrt(TRADING_DAYS)) if sd > 0 else 0.0
    return out


def _needs(cfg: Config, researchers) -> dict[tuple[str, int], list[StrategySpec]]:
    needs: dict[tuple[str, int], set] = defaultdict(set)
    for r in researchers.values():
        specs = getattr(r, "grid", None) or (r.spec,)
        needs[(r.market, r.oracle_assets(cfg.markets[r.market]))].update(specs)
    return {k: sorted(v, key=lambda s: s.key) for k, v in needs.items()}


def _job(args):
    cfg, market, n, specs = args
    return oracle_sharpes(cfg, market, n, specs)


def build_oracle_table(cfg: Config, researchers, workers: int = 1) -> dict[str, float]:
    jobs = [(cfg, m, n, specs) for (m, n), specs in _needs(cfg, researchers).items()]
    if workers > 1:
        with Pool(min(workers, len(jobs))) as pool:
            parts = pool.map(_job, jobs)
    else:
        parts = [_job(j) for j in jobs]
    table: dict[str, float] = {}
    for p in parts:
        table.update(p)
    return table
