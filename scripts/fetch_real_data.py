"""Download daily OHLC for 20 liquid US ETFs from Yahoo Finance (via yfinance) into data/real/.

The raw data is NOT redistributed (Yahoo's terms), so data/ is gitignored and only derived results are
published. The prices are adjusted for splits and dividends (auto_adjust), with opens and closes
adjusted by the same factor, so overnight and intraday returns stay consistent.

Requires yfinance:  pip install yfinance
Usage:              python scripts/fetch_real_data.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from qrt.realdata import REAL_TICKERS as TICKERS  # noqa: E402

START = "2005-01-01"
OUT = Path(__file__).resolve().parent.parent / "data" / "real"


def main() -> None:
    try:
        import yfinance as yf
    except ImportError:
        sys.exit("yfinance is not installed: pip install yfinance")
    OUT.mkdir(parents=True, exist_ok=True)
    for t in TICKERS:
        df = yf.Ticker(t).history(start=START, auto_adjust=True, actions=False)
        if df.empty:
            sys.exit(f"no data for {t}")
        with open(OUT / f"{t}.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["date", "open", "close"])
            for ts, row in df.iterrows():
                w.writerow([ts.strftime("%Y-%m-%d"), f"{row['Open']:.6f}", f"{row['Close']:.6f}"])
        print(f"{t}: {len(df)} days, {df.index[0]:%Y-%m-%d} -> {df.index[-1]:%Y-%m-%d}")


if __name__ == "__main__":
    main()
