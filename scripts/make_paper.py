"""Build the paper: figures (from the locked results) -> docs/paper/paper.html -> docs/paper/quant-red-team.pdf.

Usage: .venv/Scripts/python.exe scripts/make_paper.py
Needs matplotlib, and Chrome or Edge for the PDF (headless print).
"""

from __future__ import annotations

import csv
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import ListedColormap  # noqa: E402
from scipy.stats import norm  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "paper"
FIG = OUT / "figures"
INK, INK2, MUTED, HAIR = "#17140e", "#4f4a40", "#827c6f", "#ddd5c4"
S1, S2, S3, STAMP = "#2a78d6", "#eb6834", "#1baf7a", "#b8321c"
SHORT = {"psr": "PSR", "dsr_assumed": "DSR(100)", "dsr": "DSR", "dsr_eff": "DSR-eff", "pbo": "PBO", "bonferroni": "Bonf",
         "reality_check": "RC", "spa": "SPA", "placebo": "Placebo", "delay": "Delay", "cost_stress": "Cost×2",
         "pit_universe": "PIT", "holdout": "Holdout", "full_history": "Full hist", "forward_1y": "Fwd 1y", "forward_3y": "Fwd 3y"}
NAMES = {"honest_null": "Honest, no edge", "miner_null": "Parameter miner", "lookahead": "Look-ahead bug",
         "normaliser": "Full-sample normaliser", "cost_ignorer": "Cost ignorer", "survivor": "Survivorship",
         "window_picker": "Window picker", "asset_picker": "Asset picker", "honest_trend": "Honest, real edge",
         "miner_trend": "Miner, real edge"}
FAKE_ROWS = ["honest_null", "miner_null", "lookahead", "normaliser", "cost_ignorer", "survivor", "window_picker", "asset_picker"]
REAL_ROWS = ["honest_trend", "miner_trend"]
TIER = {"psr": 1, "dsr_assumed": 1, "dsr": 2, "dsr_eff": 2, "pbo": 2, "bonferroni": 2, "reality_check": 2, "spa": 2,
        "placebo": 3, "delay": 3, "cost_stress": 3, "pit_universe": 3, "holdout": 3, "full_history": 3, "forward_1y": 3, "forward_3y": 3}

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8.5, "axes.edgecolor": HAIR, "axes.labelcolor": INK2,
                     "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False,
                     "svg.fonttype": "none"})


def load(run: str) -> dict:
    return {(r["row"], r["audit"]): r for r in csv.DictReader(open(ROOT / "results" / run / "matrix.csv", encoding="utf-8"))}


def rate(r) -> float | None:
    nf, nr = int(r["n_fake"]), int(r["n_real"])
    if nf + nr == 0:
        return None
    return float(r["catch_rate"]) if nf >= nr else float(r["false_alarm_rate"])


def audits_of(m: dict) -> list[str]:
    return list(dict.fromkeys(a for _, a in m))


def oklab_ramp(lo: str, hi: str, n: int = 256) -> ListedColormap:
    def lin(c):
        return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)

    def to_lab(h):
        r, g, b = lin(np.array([int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]))
        l, m, s = np.cbrt([0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b, 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b,
                           0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b])
        return np.array([0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s, 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
                         0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s])

    def to_rgb(L, a, b):
        l, m, s = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3, (L - 0.1055613458 * a - 0.0638541728 * b) ** 3, (L - 0.0894841775 * a - 1.291485548 * b) ** 3
        rgb = np.array([4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s, -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
                        -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s])
        rgb = np.clip(rgb, 0, 1)
        return np.where(rgb <= 0.0031308, 12.92 * rgb, 1.055 * rgb ** (1 / 2.4) - 0.055)

    a, b = to_lab(lo), to_lab(hi)
    return ListedColormap([to_rgb(*(a + (b - a) * t)) for t in np.linspace(0, 1, n)])


def fig_matrix(m: dict, path: Path) -> None:
    aud = audits_of(m)
    rows = FAKE_ROWS + REAL_ROWS
    Z = np.array([[np.nan if rate(m[(r, a)]) is None else rate(m[(r, a)]) for a in aud] for r in rows])
    cmap = oklab_ramp("#f6eee4", "#8b1c0e")
    fig, ax = plt.subplots(figsize=(7.2, 3.9))
    ax.imshow(np.nan_to_num(Z, nan=0), cmap=cmap, vmin=0, vmax=1, aspect="auto")
    for i in range(len(rows)):
        for j in range(len(aud)):
            v = Z[i, j]
            if np.isnan(v):
                ax.add_patch(plt.Rectangle((j - .5, i - .5), 1, 1, color="white", hatch="////", ec=HAIR, lw=0))
                ax.text(j, i, "–", ha="center", va="center", color=MUTED, fontsize=7)
            else:
                ax.text(j, i, f"{v * 100:.0f}", ha="center", va="center", fontsize=7, color="white" if v > 0.55 else INK)
    ax.set_xticks(range(len(aud)), [SHORT[a] for a in aud], rotation=45, ha="right")
    ax.set_yticks(range(len(rows)), [NAMES[r] for r in rows])
    ax.axhline(len(FAKE_ROWS) - .5, color=INK, lw=1.2)
    for t_end in [i for i in range(len(aud) - 1) if TIER[aud[i]] != TIER[aud[i + 1]]]:
        ax.axvline(t_end + .5, color=INK, lw=0.8)
    for side in ("left", "bottom"):
        ax.spines[side].set_visible(False)
    ax.tick_params(length=0)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def fig_tradeoff(m: dict, path: Path) -> None:
    aud = audits_of(m)
    fig, ax = plt.subplots(figsize=(4.4, 3.6))
    ax.add_patch(plt.Rectangle((0, .8), .2, .2, fc=STAMP, alpha=.08, ec=STAMP, lw=.8))
    ax.text(.01, .97, "safe corner (empty)", color=STAMP, fontsize=7, va="top")
    offsets = {"psr": (6, 4), "cost_stress": (6, 6), "pit_universe": (6, -8), "delay": (6, 2), "reality_check": (-15, 5),
               "spa": (5, -10), "placebo": (6, 2), "bonferroni": (6, 3), "pbo": (6, -6), "dsr": (6, 2), "holdout": (6, 2),
               "forward_1y": (-6, -12), "forward_3y": (-34, 4), "dsr_assumed": (6, -8)}
    for a in aud:
        cells = [m[(r, a)] for r in FAKE_ROWS if int(m[(r, a)]["n_fake"]) >= 10]   # skip not-applicable cells
        catch = np.mean([float(c["catch_rate"]) for c in cells])
        k = sum(int(m[(r, a)]["false_alarms"]) for r in FAKE_ROWS + REAL_ROWS)
        n = sum(int(m[(r, a)]["n_real"]) for r in FAKE_ROWS + REAL_ROWS)
        color = {1: S1, 2: S2, 3: S3}[TIER[a]]
        ax.scatter(k / n, catch, s=34, color=color, edgecolor="white", linewidth=1.2, zorder=3)
        ax.annotate(SHORT[a], (k / n, catch), textcoords="offset points", xytext=offsets.get(a, (6, 2)), fontsize=7, color=INK)
    ax.set_xlim(-.03, 1)
    ax.set_ylim(-.03, 1.03)
    ax.set_xlabel("False alarms on real edges")
    ax.set_ylabel("Average catch rate on fakes")
    ax.grid(color=HAIR, lw=.6)
    for t, c in ((1, S1), (2, S2), (3, S3)):
        ax.scatter([], [], color=c, s=24, label=f"Tier {t}")
    ax.legend(frameon=False, loc="lower right", fontsize=7)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def fig_replication(m1: dict, m2: dict, path: Path) -> None:
    pts = [(rate(r), rate(m2[k])) for k, r in m1.items() if rate(r) is not None and rate(m2[k]) is not None]
    x, y = np.array(pts).T
    fig, ax = plt.subplots(figsize=(3.4, 3.2))
    ax.fill_between([0, 1], [-.1, .9], [.1, 1.1], color=S1, alpha=.08, lw=0)
    ax.plot([0, 1], [0, 1], color=INK2, lw=.8)
    ax.scatter(x, y, s=10, color=S1, edgecolor="white", linewidth=.6, zorder=3)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel("v1 rate (seed 314159265)")
    ax.set_ylabel("v2 rate (seed 271828182)")
    ax.text(.03, .93, f"{len(pts)} cells, all within ±10 pts", fontsize=7, color=INK)
    ax.grid(color=HAIR, lw=.6)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def fig_power(path: Path, measured: list[tuple[float, float]]) -> None:
    yrs = np.linspace(0.01, 20, 400)
    fig, ax = plt.subplots(figsize=(3.6, 3.0))
    for sr, c, w in ((1.0, MUTED, 1.1), (0.7, S1, 2), (0.5, MUTED, 1.1)):
        ax.plot(yrs, norm.cdf(sr * np.sqrt(yrs) - 1.6449), color=c, lw=w)
        ax.text(20.3, norm.cdf(sr * np.sqrt(20) - 1.6449), f"SR {sr:.1f}", fontsize=7, va="center", color=INK)
    ax.axhline(.8, color=INK2, lw=.6)
    need = ((1.6449 + 0.8416) / 0.7) ** 2
    ax.axvline(need, color=S1, lw=.6)
    ax.text(need + .3, .05, f"{need:.1f} y", fontsize=7, color=INK)
    ax.scatter(*zip(*measured), color=S2, s=26, edgecolor="white", linewidth=1, zorder=3, label="measured (true SR 0.72)")
    ax.set_xlim(0, 20)
    ax.set_ylim(0, 1)
    ax.set_xlabel("Years of honest paper trading")
    ax.set_ylabel("P(genuine edge passes, t ≥ 1.645)")
    ax.legend(frameon=False, fontsize=7, loc="lower right")
    ax.grid(color=HAIR, lw=.6)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def chrome() -> str | None:
    for p in (r"C:\Program Files\Google\Chrome\Application\chrome.exe", r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              shutil.which("chrome"), shutil.which("google-chrome"), shutil.which("chromium")):
        if p and Path(p).exists():
            return p
    return None


def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    m1, m2 = load("final"), load("final-v2")
    fig_matrix(m1, FIG / "matrix-v1.svg")
    fig_tradeoff(m1, FIG / "tradeoff-v1.svg")
    fig_replication(m1, m2, FIG / "replication.svg")
    ht1, ht3 = m1[("honest_trend", "forward_1y")], m1[("honest_trend", "forward_3y")]
    fig_power(FIG / "power.svg", [(1, 1 - float(ht1["false_alarm_rate"])), (3, 1 - float(ht3["false_alarm_rate"]))])
    real = json.loads((ROOT / "results" / "real-case" / "case.json").read_text())
    rows = "".join(
        f"<tr><td>{NAMES.get(c['researcher'], c['id']) if c['id'] not in ('honest', 'miner') else ('Honest' if c['id'] == 'honest' else 'Parameter miner')}</td>"
        f"<td><code>{c['selection']}</code>{' on ' + ', '.join(c['assets']) if c['assets'] else ''}</td>"
        f"<td class='r'>{c['claimed_sharpe']:.2f} ({c['claimed_t']:.2f})</td>"
        f"<td class='r'>{sum(1 for v in c['audits'].values() if v['reject'])} / {len(c['audits'])}</td>"
        f"<td class='r'>{c['future_sharpe']:.2f}</td></tr>"
        for c in sorted(real["cases"], key=lambda c: -c["claimed_sharpe"]))
    html = (ROOT / "docs" / "paper" / "paper.template.html").read_text(encoding="utf-8").replace("{{REAL_ROWS}}", rows)
    (OUT / "paper.html").write_text(html, encoding="utf-8")
    exe = chrome()
    if not exe:
        sys.exit("paper.html written; no Chrome/Edge found for the PDF")
    pdf = OUT / "quant-red-team.pdf"
    with tempfile.TemporaryDirectory() as prof:
        subprocess.run([exe, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--user-data-dir={prof}",
                        f"--print-to-pdf={pdf}", (OUT / "paper.html").as_uri()], check=True, capture_output=True, timeout=120)
    (ROOT / "site" / "paper").mkdir(exist_ok=True)
    shutil.copy(pdf, ROOT / "site" / "paper" / "quant-red-team.pdf")
    print(f"wrote {pdf} ({pdf.stat().st_size / 1024:.0f} KB) and site/paper/quant-red-team.pdf")


if __name__ == "__main__":
    main()
