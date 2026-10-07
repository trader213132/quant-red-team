"""Runs the experiment: for each researcher, simulate markets until enough backtests claim an edge, then
audit every claim and record it against the oracle's ground truth.

Determinism: run i of researcher r always uses seed [cfg.seed, crc32(r), i], and the claims kept are
the first `target_claims` by run index - so results do not depend on worker count or batching.
"""

from __future__ import annotations

import json
import math
import platform
import time
import zlib
from datetime import datetime, timezone
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import scipy

from qrt.audits import run_audits
from qrt.config import Config, code_hash, config_hash
from qrt.engine import Dataset
from qrt.markets import simulate
from qrt.oracle import build_oracle_table, label, oracle_key
from qrt.workflows import build_researchers

_STATE: dict = {}


def case_seed(cfg: Config, rid: str, i: int) -> list[int]:
    return [cfg.seed, zlib.crc32(rid.encode()), i]


def _f(x):
    return None if x is None else float(x)


def run_case(cfg: Config, rid: str, i: int, oracle: dict[str, float]) -> dict | None:
    researcher = build_researchers(cfg)[rid]
    mspec = cfg.markets[researcher.market]
    seed = case_seed(cfg, rid, i)
    ds = Dataset.from_market(simulate(mspec, np.random.default_rng([*seed, 0])))
    claim = researcher.run(ds)
    if claim.t_stat < cfg.claim_t:
        return None
    sel = claim.selection
    true_sr = oracle[oracle_key(researcher.market, sel.spec, researcher.oracle_assets(mspec))]
    audits = run_audits(claim, researcher, ds, cfg, seed=[*seed, 1])
    return {
        "row": rid, "run": i, "selection": sel.spec.key, "lag": sel.impl.lag,
        "cost_bps": sel.impl.cost_bps, "universe": sel.impl.universe, "scope": sel.impl.scope,
        "assets": None if sel.assets is None else list(sel.assets), "start": sel.start,
        "n_trials": claim.n_trials, "t": float(claim.t_stat), "sharpe": float(claim.sharpe),
        "true_sharpe": true_sr, "label": label(true_sr, cfg),
        "audits": {name: {"reject": None if a.reject is None else bool(a.reject),
                          "score": _f(a.score), "value": _f(a.value)} for name, a in audits.items()},
    }


def _init(cfg: Config, oracle: dict[str, float]) -> None:
    _STATE["cfg"], _STATE["oracle"] = cfg, oracle


def _task(args):
    rid, i = args
    return run_case(_STATE["cfg"], rid, i, _STATE["oracle"])


def run_row(pool: Pool, cfg: Config, rid: str, workers: int, log=print) -> tuple[list[dict], dict]:
    target, cap = cfg.run.target_claims, cfg.run.max_runs
    claims: list[dict] = []
    nxt, rate = 0, None
    t0 = time.perf_counter()
    while len(claims) < target and nxt < cap:
        need = target - len(claims)
        size = workers if rate is None else math.ceil(need / max(rate, 1e-3) * 1.15)
        size = int(min(max(size, workers), cfg.run.batch, cap - nxt))
        batch = [(rid, i) for i in range(nxt, nxt + size)]
        results = pool.map(_task, batch, chunksize=max(1, size // (workers * 4)))
        claims += [r for r in results if r is not None]
        nxt += size
        rate = len(claims) / nxt
        log(f"  {rid}: {len(claims)}/{target} claims after {nxt} runs")
    claims = claims[:target]
    runs = claims[-1]["run"] + 1 if len(claims) == target else nxt
    summary = {"row": rid, "claims": len(claims), "runs": runs,
               "claim_rate": len(claims) / runs if runs else 0.0,
               "seconds": round(time.perf_counter() - t0, 1)}
    return claims, summary


def run_experiment(cfg: Config, config_path: str, out_dir: Path, workers: int = 16,
                   final: bool = False, log=print) -> Path:
    out_dir = Path(out_dir)
    if (out_dir / "LOCK").exists():
        raise RuntimeError(f"{out_dir} is a locked final run; results are frozen and cannot be re-run")
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {
        "config_path": str(config_path), "config_hash": config_hash(cfg), "code_hash": code_hash(),
        "seed": cfg.seed, "final": final, "started": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__,
        "workers": workers, "rows": {},
    }
    if manifest["config_hash"] != config_hash(cfg) or manifest["code_hash"] != code_hash():
        raise RuntimeError("config or code changed since this run started; use a new output folder")

    researchers = build_researchers(cfg)
    oracle_path = out_dir / "oracle.json"
    if oracle_path.exists():
        oracle = json.loads(oracle_path.read_text())
    else:
        log("building oracle table ...")
        oracle = build_oracle_table(cfg, researchers, workers)
        oracle_path.write_text(json.dumps(oracle, indent=1, sort_keys=True))

    with Pool(workers, initializer=_init, initargs=(cfg, oracle)) as pool:
        for rid in cfg.researchers:
            path = out_dir / f"cases_{rid}.jsonl"
            if path.exists():
                log(f"{rid}: already done, skipping")
                continue
            log(f"{rid}:")
            claims, summary = run_row(pool, cfg, rid, workers, log)
            tmp = path.with_suffix(".tmp")
            tmp.write_text("".join(json.dumps(c) + "\n" for c in claims))
            tmp.replace(path)
            manifest["rows"][rid] = summary
            manifest_path.write_text(json.dumps(manifest, indent=1))

    manifest["finished"] = datetime.now(timezone.utc).isoformat()
    manifest_path.write_text(json.dumps(manifest, indent=1))
    if final:
        (out_dir / "LOCK").write_text(f"config {manifest['config_hash']}\ncode {manifest['code_hash']}\n")
    return out_dir
