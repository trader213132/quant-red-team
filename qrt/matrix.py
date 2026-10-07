"""Aggregate case records into the detection matrix.

For each (researcher, audit) cell:
  catch rate      = share of FAKE claims the audit rejected   (higher is better)
  false-alarm rate = share of REAL claims the audit rejected  (lower is better)
MARGINAL claims and audits that do not apply (verdict None) are left out of both. Every rate carries a
Wilson 95% interval.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from qrt.audits import AUDITS, TIER
from qrt.stats import auc, wilson_ci

AUDIT_NAMES = [name for name, _, _ in AUDITS]


def audits_in(cases: list[dict]) -> list[str]:
    """Audits recorded in these cases, in registry order (v1 runs have 14, v2 runs 16)."""
    present = set(cases[0]["audits"]) if cases else set()
    return [a for a in AUDIT_NAMES if a in present]


def load_cases(run_dir: Path) -> list[dict]:
    cases = []
    for path in sorted(Path(run_dir).glob("cases_*.jsonl")):
        cases += [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return cases


def row_order(cases: list[dict], preferred: list[str] | None = None) -> list[str]:
    seen = list(dict.fromkeys(c["row"] for c in cases))
    if preferred:
        return [r for r in preferred if r in seen] + [r for r in seen if r not in preferred]
    return seen


def _rate(verdicts: list[bool]):
    k, n = sum(verdicts), len(verdicts)
    lo, hi = wilson_ci(k, n)
    return n, k, (k / n if n else float("nan")), lo, hi


def build_matrix(cases: list[dict], rows: list[str] | None = None) -> list[dict]:
    out = []
    for row in rows or row_order(cases):
        mine = [c for c in cases if c["row"] == row]
        for audit in audits_in(cases):
            def verdicts(lab):
                return [c["audits"][audit]["reject"] for c in mine
                        if c["label"] == lab and c["audits"][audit]["reject"] is not None]
            nf, kf, rf, lf, hf = _rate(verdicts("FAKE"))
            nr, kr, rr, lr, hr = _rate(verdicts("REAL"))
            out.append({
                "row": row, "audit": audit, "tier": TIER[audit],
                "n_fake": nf, "caught": kf, "catch_rate": rf, "catch_lo": lf, "catch_hi": hf,
                "n_real": nr, "false_alarms": kr, "false_alarm_rate": rr, "fa_lo": lr, "fa_hi": hr,
                "n_marginal": sum(c["label"] == "MARGINAL" for c in mine),
                "n_not_applicable": sum(c["audits"][audit]["reject"] is None for c in mine),
            })
    return out


def build_auc(cases: list[dict], rows: list[str] | None = None) -> list[dict]:
    """Threshold-free comparison: how well each audit's score separates one researcher's FAKE claims
    from all REAL claims (1.0 = perfectly, 0.5 = no better than a coin)."""
    out = []
    for audit in audits_in(cases):
        real = [c["audits"][audit]["score"] for c in cases
                if c["label"] == "REAL" and c["audits"][audit]["score"] is not None]
        for row in rows or row_order(cases):
            fake = [c["audits"][audit]["score"] for c in cases
                    if c["row"] == row and c["label"] == "FAKE" and c["audits"][audit]["score"] is not None]
            out.append({"audit": audit, "tier": TIER[audit], "row": row, "n_fake": len(fake),
                        "n_real": len(real), "auc": auc(real, fake)})
    return out


def write_csv(records: list[dict], path: Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
