"""Writes matrix.csv, auc.csv and a self-contained report.html for a run folder."""

from __future__ import annotations

import csv
import json
import math
from html import escape
from pathlib import Path

import numpy as np

from qrt.matrix import AUDIT_NAMES, build_auc, build_matrix, load_cases, row_order, write_csv

ROWS = {
    "honest_null": ("Honest, no edge",
                    "Pre-registers one momentum rule (TSMOM-60) and backtests it once, correctly. The market has "
                    "no edge, so every claim here is pure luck."),
    "honest_trend": ("Honest, real edge",
                     "Same rule, same method, in a market with a genuine hidden trend. These claims are mostly "
                     "REAL, so a rejection here is a false alarm."),
    "miner_null": ("Parameter miner",
                   "Tries 120 rule variants and reports the best one. No edge exists."),
    "miner_trend": ("Parameter miner, real edge",
                    "Tries 120 variants in the trending market. Some picks are genuinely good, some just lucky; "
                    "the oracle decides each one."),
    "lookahead": ("Look-ahead bug",
                  "Uses today's closing price to decide a trade filled at today's open: information it could "
                  "not have had."),
    "normaliser": ("Full-sample normaliser",
                   "Bets on prices returning to the average of the WHOLE sample, future included."),
    "cost_ignorer": ("Cost ignorer",
                     "A high-turnover reversal rule backtested with zero trading costs. The gross edge is real; "
                     "after costs it loses money."),
    "survivor": ("Survivorship bias",
                 "'Buy the dip' tested only on stocks still listed today. The ones that crashed and were "
                 "delisted are missing from its data."),
    "window_picker": ("Window picker",
                      "Tries 11 start dates and reports the period that looks best (\"since 2019 it made...\")."),
    "asset_picker": ("Asset picker",
                     "Runs one rule on 20 assets separately and reports the one where it worked."),
}

AUDITS = {
    "psr": ("PSR", "Probabilistic Sharpe: is the Sharpe significantly above zero, allowing for fat tails and skew?"),
    "dsr_assumed": ("DSR(100)", "Deflated Sharpe assuming 100 trials: raises the bar to the best Sharpe 100 "
                               "worthless strategies would produce by luck."),
    "dsr": ("DSR", "Deflated Sharpe with the real number of trials and their spread."),
    "pbo": ("PBO", "Probability of Backtest Overfitting: across 12,870 ways of splitting history in half, how "
                   "often does the in-sample winner finish in the bottom half out-of-sample?"),
    "bonferroni": ("Bonf", "Bonferroni: multiply the p-value by the number of things tried."),
    "reality_check": ("RC", "White's Reality Check: bootstrap the best of all trials and ask whether 'the best' "
                            "beats zero by more than luck allows."),
    "spa": ("SPA", "Hansen's SPA: a sharper Reality Check that stops obviously bad trials diluting the test."),
    "placebo": ("Placebo", "Re-run the whole research process on 49 copies of its data with every return's "
                           "sign randomised, so no edge is possible. If it 'finds' as much there, the finding "
                           "is worthless."),
    "delay": ("Delay", "Re-run with every trade one day later."),
    "cost_stress": ("Cost×2", "Re-run at double the real trading cost."),
    "pit_universe": ("PIT", "Re-run with the delisted names put back (point-in-time universe)."),
    "holdout": ("Holdout", "Let the process see only the first 70% of history, then test its pick on the last "
                           "30%."),
    "forward_1y": ("Fwd 1y", "Paper-trade the rule honestly on one year of brand-new data."),
    "forward_3y": ("Fwd 3y", "Paper-trade the rule honestly on three years of brand-new data."),
}

TIERS = {1: "Returns only", 2: "All trials disclosed", 3: "Re-run access"}
MIN_N = 10   # cells with fewer claims than this are shown greyed


def _pct(x: float) -> str:
    return "–" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{100 * x:.0f}%"


def load_predictions(path: Path | None) -> dict[tuple[str, str], float]:
    if path is None or not Path(path).exists():
        return {}
    out = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for rec in csv.DictReader(fh):
            v = (rec.get("predicted_percent") or "").strip()
            if v:
                out[(rec["row"], rec["audit"])] = float(v) / 100
    return out


def write_prediction_template(path: Path, rows: list[str]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["row", "audit", "measures", "predicted_percent"])
        for row in rows:
            measures = "false_alarm_rate" if row == "honest_trend" else "catch_rate"
            for audit in AUDIT_NAMES:
                w.writerow([row, audit, measures, ""])


def _mode(cell: dict) -> str:
    if cell["n_fake"] >= MIN_N and cell["n_real"] >= MIN_N:
        return "mixed"
    return "fake" if cell["n_fake"] >= cell["n_real"] else "real"


def _cell_html(cell: dict, pred: float | None) -> str:
    mode = _mode(cell)
    if cell["n_fake"] + cell["n_real"] == 0:
        return '<td class="na" title="not applicable">–</td>'
    if mode == "fake":
        rate, n, good = cell["catch_rate"], cell["n_fake"], cell["catch_rate"]
        tip = f"caught {cell['caught']}/{n} fake claims (95% CI {_pct(cell['catch_lo'])}–{_pct(cell['catch_hi'])})"
        main = _pct(rate)
    elif mode == "real":
        rate, n, good = cell["false_alarm_rate"], cell["n_real"], 1 - cell["false_alarm_rate"]
        tip = (f"false alarm on {cell['false_alarms']}/{n} real claims "
               f"(95% CI {_pct(cell['fa_lo'])}–{_pct(cell['fa_hi'])})")
        main = f'<span class="fa">FA</span> {_pct(rate)}'
    else:
        n = min(cell["n_fake"], cell["n_real"])
        good = (cell["catch_rate"] + 1 - cell["false_alarm_rate"]) / 2
        tip = (f"caught {cell['caught']}/{cell['n_fake']} fake; false alarm on "
               f"{cell['false_alarms']}/{cell['n_real']} real")
        main = f'{_pct(cell["catch_rate"])}<br><span class="fa">FA</span> {_pct(cell["false_alarm_rate"])}'
    weak = " weak" if n < MIN_N else ""
    p = ""
    if pred is not None:
        p = f'<div class="pred">you: {_pct(pred)}</div>'
        tip += f"; you predicted {_pct(pred)}"
    g = 0.0 if good is None or math.isnan(good) else good
    return (f'<td class="cell{weak}" style="--g:{100 * g:.0f}%" title="{escape(tip)}">'
            f'<div class="v">{main}</div>{p}</td>')


def _matrix_table(matrix, rows, counts, preds) -> str:
    by = {(m["row"], m["audit"]): m for m in matrix}
    head1 = '<tr><th class="rowh" rowspan="2">Researcher</th>' + "".join(
        f'<th class="tier t{t}" colspan="{sum(1 for a in AUDIT_NAMES if by[(rows[0], a)]["tier"] == t)}">'
        f'Tier {t} · {TIERS[t]}</th>' for t in (1, 2, 3)) + "</tr>"
    head2 = "<tr>" + "".join(
        f'<th class="aud" title="{escape(AUDITS[a][1])}">{escape(AUDITS[a][0])}</th>' for a in AUDIT_NAMES) + "</tr>"
    body = []
    for row in rows:
        name, desc = ROWS.get(row, (row, ""))
        c = counts[row]
        truth = f'{c["FAKE"]} fake · {c["REAL"]} real' + (f' · {c["MARGINAL"]} marginal' if c["MARGINAL"] else "")
        cells = "".join(_cell_html(by[(row, a)], preds.get((row, a))) for a in AUDIT_NAMES)
        body.append(f'<tr><th class="rowh" title="{escape(desc)}"><div class="rn">{escape(name)}</div>'
                    f'<div class="rt">{truth}</div></th>{cells}</tr>')
    return f'<div class="scroll"><table class="matrix"><thead>{head1}{head2}</thead><tbody>{"".join(body)}</tbody></table></div>'


def _audit_summary(matrix, auc_rows, rows, counts) -> str:
    fake_rows = [r for r in rows if counts[r]["FAKE"] >= MIN_N]
    lines = []
    for a in AUDIT_NAMES:
        cells = [m for m in matrix if m["audit"] == a]
        catches = [m["catch_rate"] for m in cells if m["row"] in fake_rows and m["n_fake"] >= MIN_N]
        fa_k = sum(m["false_alarms"] for m in cells)
        fa_n = sum(m["n_real"] for m in cells)
        aucs = [x["auc"] for x in auc_rows if x["audit"] == a and x["n_fake"] >= MIN_N and not math.isnan(x["auc"])]
        lines.append(
            f'<tr><td><b>{escape(AUDITS[a][0])}</b><div class="small">{escape(AUDITS[a][1])}</div></td>'
            f'<td class="num">{cells[0]["tier"]}</td>'
            f'<td class="num">{_pct(float(np.mean(catches))) if catches else "–"}</td>'
            f'<td class="num">{_pct(fa_k / fa_n) if fa_n else "–"}</td>'
            f'<td class="num">{f"{np.median(aucs):.2f}" if aucs else "–"}</td></tr>')
    return ('<table class="plain"><thead><tr><th>Audit</th><th>Tier</th><th>Average catch rate<br>(fake rows)</th>'
            '<th>False alarms<br>(all real claims)</th><th>Median AUC</th></tr></thead><tbody>'
            + "".join(lines) + "</tbody></table>")


FA_CAP = 0.20   # an audit that wrongly rejects more than 1 in 5 genuine edges is not usable (D12)


def pooled_false_alarms(matrix) -> dict[str, tuple[int, int]]:
    out = {}
    for a in AUDIT_NAMES:
        cells = [m for m in matrix if m["audit"] == a]
        out[a] = (sum(m["false_alarms"] for m in cells), sum(m["n_real"] for m in cells))
    return out


def _access_table(matrix, rows, counts) -> str:
    fa = pooled_false_alarms(matrix)
    usable = {a for a, (k, n) in fa.items() if n == 0 or k / n <= FA_CAP}
    excluded = [f"{AUDITS[a][0]} ({100 * fa[a][0] / fa[a][1]:.1f}%)" for a in AUDIT_NAMES if a not in usable]
    lines = []
    for row in rows:
        if counts[row]["FAKE"] < MIN_N:
            continue
        best = {}
        for t in (1, 2, 3):
            cells = [m for m in matrix if m["row"] == row and m["tier"] == t and m["n_fake"] >= MIN_N
                     and m["audit"] in usable]
            best[t] = max(cells, key=lambda m: m["catch_rate"]) if cells else None
        needed = next((t for t in (1, 2, 3) if best[t] and best[t]["catch_rate"] >= 0.8), None)
        tds = "".join(
            f'<td class="num{" hit" if t == needed else ""}">'
            + (f'{_pct(best[t]["catch_rate"])}<div class="small">{escape(AUDITS[best[t]["audit"]][0])}</div>'
               if best[t] else "–") + "</td>" for t in (1, 2, 3))
        verdict = f"Tier {needed}" if needed else "No usable audit catches 80%"
        lines.append(f'<tr><td><b>{escape(ROWS.get(row, (row,))[0])}</b></td>{tds}<td>{verdict}</td></tr>')
    note = (f'<p class="small">Only audits that wrongly reject at most {_pct(FA_CAP)} of genuine edges (pooled over '
            f'all REAL claims) count here. Excluded: {escape(", ".join(excluded)) or "none"}. They can "catch" '
            f'fakes only by rejecting almost everything. (Presentation choice made after the final run: '
            f'decision D12.)</p>')
    return (note + '<table class="plain"><thead><tr><th>Flaw</th><th>Best usable tier-1 audit</th>'
            '<th>Best usable tier-2 audit</th><th>Best usable tier-3 audit</th><th>Access needed to catch ≥80%'
            '</th></tr></thead><tbody>' + "".join(lines) + "</tbody></table>")


def _prediction_section(matrix, preds) -> str:
    if not preds:
        return ('<p class="small">No predictions found. Fill in <code>predictions.csv</code> (before the final '
                'run!) to see your guesses next to the results.</p>')
    errs = []
    for m in matrix:
        p = preds.get((m["row"], m["audit"]))
        if p is None:
            continue
        actual = m["false_alarm_rate"] if _mode(m) == "real" else m["catch_rate"]
        if not math.isnan(actual):
            errs.append(abs(p - actual))
    if not errs:
        return ""
    return (f'<p>You predicted {len(errs)} cells. Your average miss was <b>{100 * np.mean(errs):.0f} percentage '
            f'points</b>; your biggest was {100 * max(errs):.0f}. Your guesses are shown in each matrix cell.</p>')


CSS = """
:root{--bg:#fbfaf7;--fg:#1d1c1a;--muted:#6b6862;--line:#e3e0d8;--card:#ffffff;--good:#2f9e6b;--bad:#d9534f;
--t1:#e8eef8;--t2:#f3ecdf;--t3:#e6f2ec;--accent:#3b5bdb}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#161615;--fg:#ecebe7;--muted:#a19e96;
--line:#2f2e2b;--card:#1f1e1c;--good:#3fb67f;--bad:#e0645f;--t1:#1f2735;--t2:#2e2a22;--t3:#1d2c25;--accent:#8ea6ff}}
:root[data-theme="dark"]{--bg:#161615;--fg:#ecebe7;--muted:#a19e96;--line:#2f2e2b;--card:#1f1e1c;--good:#3fb67f;
--bad:#e0645f;--t1:#1f2735;--t2:#2e2a22;--t3:#1d2c25;--accent:#8ea6ff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,
"Segoe UI",sans-serif}main{max-width:1240px;margin:0 auto;padding:28px 16px 60px}h1{font-size:28px;margin:0 0 4px}
h2{font-size:19px;margin:36px 0 8px}.lede{color:var(--muted);max-width:820px}.badge{display:inline-block;
padding:2px 8px;border-radius:99px;font-size:12px;font-weight:600;background:var(--bad);color:#fff;margin-left:8px;
vertical-align:middle}.badge.final{background:var(--good)}.scroll{overflow-x:auto;border:1px solid var(--line);
border-radius:10px;background:var(--card)}table{border-collapse:collapse}.matrix{min-width:1100px;width:100%}
.matrix th,.matrix td{border-bottom:1px solid var(--line);padding:6px 4px;text-align:center}.matrix .rowh{
text-align:left;padding-left:12px;min-width:170px;position:sticky;left:0;background:var(--card);z-index:1}
.rn{font-weight:600}.rt{font-size:12px;color:var(--muted);font-weight:400}.tier{font-size:12px;
text-transform:uppercase;letter-spacing:.04em}.t1{background:var(--t1)}.t2{background:var(--t2)}.t3{background:var(--t3)}
.aud{font-size:12px;font-weight:600;cursor:help;white-space:nowrap}.cell{background:color-mix(in oklab,var(--good) var(--g),
var(--bad));color:#fff;font-weight:600;font-variant-numeric:tabular-nums;min-width:64px}.cell.weak{opacity:.45}
.fa{font-size:10px;opacity:.85}.pred{font-size:10px;font-weight:400;opacity:.9}.na{color:var(--muted)}
.plain{width:100%;background:var(--card);border:1px solid var(--line);border-radius:10px}.plain th,.plain td{
padding:8px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}.plain th{font-size:13px}
.num{text-align:right;font-variant-numeric:tabular-nums}.hit{outline:2px solid var(--good);outline-offset:-2px}
.small{font-size:12px;color:var(--muted)}code{font-size:13px}.legend{display:flex;gap:16px;flex-wrap:wrap;
font-size:13px;color:var(--muted);margin:10px 0}.sw{display:inline-block;width:14px;height:14px;border-radius:3px;
vertical-align:-2px;margin-right:4px}footer{margin-top:40px;color:var(--muted);font-size:12px}
dl{display:grid;grid-template-columns:minmax(140px,220px) 1fr;gap:6px 16px}dt{font-weight:600}dd{margin:0}
@media (max-width:640px){dl{grid-template-columns:1fr}h1{font-size:23px}}
"""


def write_report(run_dir: Path, predictions: Path | None = None) -> Path:
    run_dir = Path(run_dir)
    cases = load_cases(run_dir)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    rows = row_order(cases, list(ROWS))
    matrix = build_matrix(cases, rows)
    auc_rows = build_auc(cases, rows)
    write_csv(matrix, run_dir / "matrix.csv")
    write_csv(auc_rows, run_dir / "auc.csv")
    preds = load_predictions(predictions)
    counts = {r: {lab: sum(1 for c in cases if c["row"] == r and c["label"] == lab)
                  for lab in ("FAKE", "REAL", "MARGINAL")} for r in rows}

    final = manifest.get("final")
    badge = '<span class="badge final">FINAL · locked</span>' if final else '<span class="badge">DEV · do not quote</span>'
    rates = " · ".join(f'{escape(ROWS.get(r, (r,))[0])}: {manifest["rows"][r]["claim_rate"]:.1%}'
                       for r in rows if r in manifest.get("rows", {}))
    glossary_rows = "".join(f"<dt>{escape(n)}</dt><dd>{escape(d)}</dd>" for n, d in ROWS.values())
    glossary_audits = "".join(f"<dt>{escape(n)}</dt><dd>{escape(d)}</dd>" for n, d in AUDITS.values())
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Detection Matrix</title>
<style>{CSS}</style></head><body><main>
<h1>Detection Matrix {badge}</h1>
<p class="lede">Of backtests that look publishable (t ≥ 2), which audits correctly reject the fake ones, how
often do they wrongly reject real ones, and how much access does the auditor need? Every claim below was
checked against an oracle that knows the true edge.</p>

<h2>The matrix</h2>
<div class="legend"><span><span class="sw" style="background:var(--good)"></span>good (catches fakes / no false alarm)</span>
<span><span class="sw" style="background:var(--bad)"></span>bad (misses fakes / false alarm)</span>
<span>Plain % = catch rate on FAKE claims · <b>FA</b> = false-alarm rate on REAL claims · faded = fewer than {MIN_N}
claims · hover any cell for counts and 95% intervals, any header for an explanation.</span></div>
{_matrix_table(matrix, rows, counts, preds)}

<h2>How much access does an auditor need?</h2>
<p class="small">For each flaw, the best usable audit at each access tier. The highlighted cell is the
cheapest tier that catches at least 80% of the fakes.</p>
{_access_table(matrix, rows, counts)}

<h2>What each audit is good for</h2>
<p class="small">AUC compares each researcher's fake claims with all real claims using the audit's
continuous score, independent of the pass/fail threshold (1.0 = perfect separation, 0.5 = coin flip).</p>
{_audit_summary(matrix, auc_rows, rows, counts)}

<h2>Your predictions</h2>
{_prediction_section(matrix, preds)}

<h2>Glossary</h2>
<h3>Researchers</h3><dl>{glossary_rows}</dl>
<h3>Audits</h3><dl>{glossary_audits}</dl>

<footer>Config {manifest["config_hash"][:12]} · code {manifest["code_hash"][:12]} · seed {manifest["seed"]} ·
started {escape(manifest.get("started", ""))} · numpy {manifest.get("numpy")} · scipy {manifest.get("scipy")}<br>
Claim rates: {rates}</footer>
</main></body></html>"""
    out = run_dir / "report.html"
    out.write_text(html, encoding="utf-8")
    return out
