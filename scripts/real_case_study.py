"""Real-market case study (v2): the same researchers and audits, run on 20 real ETFs.

  research window  2005-01-03 .. 2018-12-31   (what each researcher sees)
  future window    2019-01-02 .. 2026-10-06   (what actually happened next)

There is no oracle in real markets. The 'truth' for each claim is the claimed rule, implemented honestly,
in the future window: one draw per researcher, so this is a case study, not statistics. The forward tests
need a simulator and are replaced by the real future. Survivorship does not apply (no delistings here).

Outputs: results/real-case/case.json (full) and site/data/real-case.json (derived numbers only).
Usage:   .venv/Scripts/python.exe scripts/real_case_study.py    (after scripts/fetch_real_data.py)
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from qrt.audits import AUDITS, run_audits  # noqa: E402
from qrt.config import load_config  # noqa: E402
from qrt.engine import Dataset, Selection, backtest, honest_implementation  # noqa: E402
from qrt.realdata import REAL_TICKERS, load_real_market  # noqa: E402
from qrt.stats import annual_sharpe, t_stat  # noqa: E402
from qrt.workflows import build_researchers  # noqa: E402

START, SPLIT, END = "2005-01-01", "2019-01-01", "2026-10-06"
CASES = [("honest", "honest_null"), ("miner", "miner_null"), ("lookahead", "lookahead"), ("normaliser", "normaliser"),
         ("cost_ignorer", "cost_ignorer"), ("window_picker", "window_picker"), ("asset_picker", "asset_picker")]
SKIP = {"forward_1y", "forward_3y"}


def r2(x):
    return None if x is None else round(float(x), 3)


def main() -> None:
    cfg = load_config(ROOT / "configs" / "v2.toml")
    market, dates = load_real_market(ROOT / "data" / "real", REAL_TICKERS, START, END)
    split = next(i for i, d in enumerate(dates) if d >= SPLIT)
    research = Dataset.from_market(market.slice_days(0, split))
    full = Dataset.from_market(market)
    researchers = build_researchers(cfg)
    honest = honest_implementation(cfg.true_cost_bps)
    only = tuple(a for a, _, _ in AUDITS if a not in SKIP)

    total = (1 + market.r_on) * (1 + market.r_id) - 1
    ew = total.mean(axis=1)
    out = {"window": {"research": [dates[0], dates[split - 1]], "future": [dates[split], dates[-1]],
                      "research_days": split, "future_days": len(dates) - split},
           "tickers": REAL_TICKERS, "true_cost_bps": cfg.true_cost_bps,
           "benchmark": {"name": "Equal-weight buy and hold of the 20 ETFs",
                         "research_sharpe": r2(annual_sharpe(ew[cfg.warmup:split])), "future_sharpe": r2(annual_sharpe(ew[split:]))},
           "cases": []}
    for k, (label, rid) in enumerate(CASES):
        r = researchers[rid]
        claim = r.run(research)
        audits = run_audits(claim, r, research, cfg, seed=[cfg.seed, 99, k], only=only)
        sel = claim.selection
        fut = backtest(Selection(sel.spec, honest, sel.assets, start=split), full)
        out["cases"].append({
            "id": label, "researcher": rid, "selection": sel.spec.key,
            "assets": None if sel.assets is None else [REAL_TICKERS[i] for i in sel.assets],
            "start": dates[sel.start] if sel.start < split else None,
            "claimed_sharpe": r2(claim.sharpe), "claimed_t": r2(claim.t_stat), "claims": bool(claim.t_stat >= cfg.claim_t),
            "future_sharpe": r2(annual_sharpe(fut)), "future_t": r2(t_stat(fut)),
            "audits": {a: {"reject": None if v.reject is None else bool(v.reject), "value": r2(v.value)} for a, v in audits.items()},
        })
        c = out["cases"][-1]
        rejects = sum(1 for v in c["audits"].values() if v["reject"])
        print(f"{label:13s} {c['selection']:16s} claimed SR {c['claimed_sharpe']:+.2f} (t {c['claimed_t']:+.2f}) "
              f"-> future SR {c['future_sharpe']:+.2f} | rejected by {rejects}/{len(c['audits'])} audits")
    (ROOT / "results" / "real-case").mkdir(parents=True, exist_ok=True)
    (ROOT / "results" / "real-case" / "case.json").write_text(json.dumps(out, indent=1))
    (ROOT / "site" / "data" / "real-case.json").write_text(json.dumps(out, separators=(",", ":")))
    print("benchmark", out["benchmark"])


if __name__ == "__main__":
    main()
