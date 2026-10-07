"""Real market data -> the same Market object the simulator produces, so every researcher and audit runs
unchanged on it. Files are data/real/<TICKER>.csv with columns date, open, close (adjusted)."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from qrt.markets import Market

# 20 liquid US ETFs with daily history from 2005: equity indices, regions, bonds, gold, sectors.
REAL_TICKERS = ["SPY", "QQQ", "IWM", "DIA", "EFA", "EEM", "TLT", "IEF", "SHY", "LQD",
                "GLD", "XLE", "XLF", "XLK", "XLV", "XLU", "XLP", "XLY", "XLI", "XLB"]


def load_real_market(folder: str | Path, tickers: list[str], start: str, end: str) -> tuple[Market, list[str]]:
    """Daily overnight/intraday returns for `tickers` on the dates every ticker has, within [start, end].
    Day 0's overnight return is 0 (no previous close inside the window)."""
    series = {}
    for t in tickers:
        with open(Path(folder) / f"{t}.csv", newline="", encoding="utf-8") as fh:
            series[t] = {r["date"]: (float(r["open"]), float(r["close"])) for r in csv.DictReader(fh)
                         if start <= r["date"] <= end}
    dates = sorted(set.intersection(*(set(s) for s in series.values())))
    opens = np.array([[series[t][d][0] for t in tickers] for d in dates])
    closes = np.array([[series[t][d][1] for t in tickers] for d in dates])
    r_on = np.zeros_like(opens)
    r_on[1:] = opens[1:] / closes[:-1] - 1
    r_id = closes / opens - 1
    return Market(r_on, r_id, np.ones(opens.shape, dtype=bool)), dates
