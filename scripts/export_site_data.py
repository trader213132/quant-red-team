"""Export the locked final results into site/data/ for the website.

Reads results/final (never modifies it) and writes:
  site/data/site-data.json  - everything the page renders
  site/data/matrix.csv, site/data/auc.csv - raw tables for download

Usage: .venv/Scripts/python.exe scripts/export_site_data.py
"""

from __future__ import annotations

import json
import math
import shutil
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from qrt.config import MarketSpec, load_config  # noqa: E402
from qrt.engine import Dataset, Implementation, Selection, backtest  # noqa: E402
from qrt.experiment import case_seed  # noqa: E402
from qrt.markets import simulate  # noqa: E402
from qrt.matrix import AUDIT_NAMES, build_auc, build_matrix, load_cases  # noqa: E402
from qrt.report import AUDITS, FA_CAP, MIN_N, ROWS, pooled_false_alarms  # noqa: E402
from qrt.strategies import StrategySpec  # noqa: E402
from qrt.audits import TIER  # noqa: E402
from qrt.workflows import build_researchers  # noqa: E402

FINAL = ROOT / "results" / "final"
OUT = ROOT / "site" / "data"

MARKET_OF = {"honest_null": "null", "honest_trend": "trend", "miner_null": "null", "miner_trend": "trend",
             "lookahead": "null", "normaliser": "null", "cost_ignorer": "reversal", "survivor": "delisting",
             "window_picker": "null", "asset_picker": "null"}
FLAW = {"honest_null": "None - luck", "honest_trend": "None - real edge", "miner_null": "Selection",
        "miner_trend": "Selection (on a real edge)", "lookahead": "Timing leak", "normaliser": "Data leak",
        "cost_ignorer": "Ignored costs", "survivor": "Survivorship", "window_picker": "Selection over time",
        "asset_picker": "Selection over assets"}


def r3(x):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), 4)


def hero_case(cfg, cases):
    """A typical look-ahead claim: its reported equity curve vs the same rule traded honestly."""
    la = [c for c in cases if c["row"] == "lookahead"]
    med = float(np.median([c["sharpe"] for c in la]))
    case = min(la, key=lambda c: abs(c["sharpe"] - med))
    seed = case_seed(cfg, "lookahead", case["run"])
    ds = Dataset.from_market(simulate(cfg.markets["null"], np.random.default_rng([*seed, 0])))
    spec = StrategySpec("tsmom", (60,))
    reported = backtest(Selection(spec, Implementation(lag=0, cost_bps=cfg.true_cost_bps), None, cfg.warmup), ds)
    honest = backtest(Selection(spec, Implementation(lag=1, cost_bps=cfg.true_cost_bps), None, cfg.warmup), ds)
    eq_r, eq_h = np.cumprod(1 + reported), np.cumprod(1 + honest)
    idx = np.unique(np.linspace(0, len(eq_r) - 1, 400).round().astype(int))
    sr = lambda r: float(r.mean() / r.std(ddof=1) * np.sqrt(252))
    return {"run": case["run"], "days": idx.tolist(), "reported": [round(float(v), 4) for v in eq_r[idx]],
            "honest": [round(float(v), 4) for v in eq_h[idx]], "reported_sharpe": round(sr(reported), 2),
            "honest_sharpe": round(sr(honest), 2), "true_sharpe": round(case["true_sharpe"], 2),
            "delay_t": round(case["audits"]["delay"]["value"], 2),
            "placebo_p": round(case["audits"]["placebo"]["value"], 2)}


def market_samples(cfg):
    """A few simulated price paths per market type, for the 'how it works' panels."""
    out = {}
    for name in ("null", "trend", "reversal", "delisting"):
        spec: MarketSpec = cfg.markets[name]
        n = 10 if name == "delisting" else 6
        m = simulate(spec, np.random.default_rng([2026, len(name)]), n_assets=n)
        step = 10
        idx = list(range(0, m.n_days, step))
        paths = []
        for k in range(n):
            close = m.close[:, k]
            dead = np.flatnonzero(~m.alive[:, k])
            end = int(dead[0]) if len(dead) else m.n_days
            pts = [round(float(close[i]), 4) for i in idx if i < end]
            paths.append({"points": pts, "delisted_at": (end // step) if len(dead) else None})
        out[name] = {"step_days": step, "paths": paths, "level": spec.delist_level if name == "delisting" else None}
    return out


def main() -> None:
    cfg = load_config(ROOT / "configs" / "final.toml")
    manifest = json.loads((FINAL / "manifest.json").read_text())
    cases = load_cases(FINAL)
    rows = [r for r in ROWS if any(c["row"] == r for c in cases)]
    matrix = build_matrix(cases, rows)
    auc_rows = build_auc(cases, rows)
    fa = pooled_false_alarms(matrix)
    researchers = build_researchers(cfg)

    counts = {r: {lab: sum(1 for c in cases if c["row"] == r and c["label"] == lab)
                  for lab in ("FAKE", "REAL", "MARGINAL")} for r in rows}
    fake_rows = [r for r in rows if counts[r]["FAKE"] >= MIN_N]

    research_out = []
    for i, r in enumerate(rows):
        mine = [c for c in cases if c["row"] == r]
        s = manifest["rows"][r]
        research_out.append({
            "id": r, "case": i + 1, "name": ROWS[r][0], "desc": ROWS[r][1], "market": MARKET_OF[r],
            "flaw": FLAW[r], "claims": s["claims"], "runs": s["runs"], "claim_rate": r3(s["claim_rate"]),
            "fake": counts[r]["FAKE"], "real": counts[r]["REAL"], "marginal": counts[r]["MARGINAL"],
            "mean_claimed": r3(np.mean([c["sharpe"] for c in mine])),
            "mean_true": r3(np.mean([c["true_sharpe"] for c in mine])),
            "claimed": [round(c["sharpe"], 2) for c in mine],
            "trials": researchers[r].grid.__len__() if hasattr(researchers[r], "grid") else mine[0]["n_trials"],
        })

    audits_out = []
    for a in AUDIT_NAMES:
        cells = [m for m in matrix if m["audit"] == a]
        catches = [m["catch_rate"] for m in cells if m["row"] in fake_rows and m["n_fake"] >= MIN_N]
        aucs = [x["auc"] for x in auc_rows if x["audit"] == a and x["n_fake"] >= MIN_N and not math.isnan(x["auc"])]
        k, n = fa[a]
        audits_out.append({
            "id": a, "short": AUDITS[a][0], "desc": AUDITS[a][1], "tier": TIER[a],
            "false_alarm": r3(k / n), "false_alarms": k, "n_real": n, "usable": n == 0 or k / n <= FA_CAP,
            "mean_catch": r3(np.mean(catches)), "auc_median": r3(np.median(aucs)),
            "auc_min": r3(min(aucs)), "auc_max": r3(max(aucs)),
            "auc_by_row": {x["row"]: r3(x["auc"]) for x in auc_rows if x["audit"] == a and x["n_fake"] >= MIN_N},
        })

    usable = {a["id"] for a in audits_out if a["usable"]}
    access = []
    for r in fake_rows:
        best = {}
        for t in (1, 2, 3):
            cand = [m for m in matrix if m["row"] == r and m["tier"] == t and m["n_fake"] >= MIN_N and m["audit"] in usable]
            b = max(cand, key=lambda m: m["catch_rate"]) if cand else None
            best[t] = None if b is None else {"audit": b["audit"], "catch": r3(b["catch_rate"])}
        needed = next((t for t in (1, 2, 3) if best[t] and best[t]["catch"] >= 0.8), None)
        access.append({"row": r, "best": best, "needed": needed})

    started = datetime.fromisoformat(manifest["started"])
    finished = datetime.fromisoformat(manifest["finished"])
    ht = next(m for m in matrix if m["row"] == "honest_trend" and m["audit"] == "forward_1y")
    ht3 = next(m for m in matrix if m["row"] == "honest_trend" and m["audit"] == "forward_3y")
    hto = next(x for x in research_out if x["id"] == "honest_trend")
    data = {
        "meta": {"config_hash": manifest["config_hash"], "code_hash": manifest["code_hash"],
                 "seed": manifest["seed"], "date": started.date().isoformat(),
                 "minutes": round((finished - started).total_seconds() / 60, 1),
                 "claims": sum(x["claims"] for x in research_out),
                 "markets": sum(x["runs"] for x in research_out), "tests": 84, "workers": manifest["workers"],
                 "true_cost_bps": cfg.true_cost_bps, "fa_cap": FA_CAP, "oracle_years": round(cfg.oracle_paths * 9)},
        "researchers": research_out, "audits": audits_out,
        "matrix": [{k: (r3(v) if isinstance(v, float) else v) for k, v in m.items()} for m in matrix],
        "access": access,
        "forward": {"true_sharpe": hto["mean_true"],
                    "measured": [{"years": 1, "pass": r3(1 - ht["false_alarm_rate"]), "n": ht["n_real"]},
                                 {"years": 3, "pass": r3(1 - ht3["false_alarm_rate"]), "n": ht3["n_real"]}]},
        "hero": hero_case(cfg, cases),
        "markets": market_samples(cfg),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "site-data.json").write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    shutil.copy(FINAL / "matrix.csv", OUT / "matrix.csv")
    shutil.copy(FINAL / "auc.csv", OUT / "auc.csv")
    print(f"wrote {OUT / 'site-data.json'} ({(OUT / 'site-data.json').stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
