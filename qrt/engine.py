"""Backtest engine: positions -> daily portfolio returns, with timing, costs and the investable universe.

Timing. A position w[t] is decided at the close of day t and filled at the open of day t+lag:
  - lag=1 is honest (decide tonight, trade at tomorrow's open);
  - lag=0 is the look-ahead bug (trade at today's open on a signal that used today's close);
  - lag=2 is the delay attack.
Day d therefore earns  w[d-lag-1] * r_on[d]  (held overnight)  +  w[d-lag] * r_id[d]  (held intraday)
minus cost * |w[d-lag] - w[d-lag-1]|  (the trade at the open). The portfolio return is the average over
assets listed that day. Delisted assets hold nothing and their forced exit is free.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from qrt.markets import Market
from qrt.strategies import StrategySpec, positions


@dataclass(frozen=True)
class Implementation:
    lag: int = 1
    cost_bps: float = 10.0
    universe: str = "pit"          # pit (everything that existed) | survivors (still listed at the end)
    scope: str = "expanding"       # how the `level` rule normalises: expanding (honest) | full_sample (leak)


def honest_implementation(true_cost_bps: float) -> Implementation:
    return Implementation(lag=1, cost_bps=true_cost_bps, universe="pit", scope="expanding")


@dataclass(frozen=True)
class Selection:
    """Exactly what a researcher claims: this rule, implemented this way, on these assets, from this day."""
    spec: StrategySpec
    impl: Implementation
    assets: tuple[int, ...] | None = None   # columns of the universe view; None = all
    start: int = 250                        # first day of the evaluation window


@dataclass
class Dataset:
    """What a data vendor hands a researcher: the full history plus the vendor's 'still listed' flags."""
    market: Market
    survivors: np.ndarray  # (N,) bool, listed at the end of the vendor's full history

    @classmethod
    def from_market(cls, market: Market) -> Dataset:
        return cls(market, market.alive[-1].copy())

    def view(self, universe: str) -> Market:
        if universe == "pit":
            return self.market
        if universe == "survivors":
            return self.market.subset(np.flatnonzero(self.survivors))
        raise ValueError(f"unknown universe {universe!r}")

    def slice_days(self, start: int, stop: int) -> Dataset:
        return Dataset(self.market.slice_days(start, stop), self.survivors.copy())

    @property
    def n_days(self) -> int:
        return self.market.n_days


def _shift(w: np.ndarray, k: int) -> np.ndarray:
    out = np.zeros_like(w)
    if k < len(w):
        out[k:] = w[: len(w) - k]
    return out


def held_positions(w: np.ndarray, alive: np.ndarray, lag: int) -> tuple[np.ndarray, np.ndarray]:
    """(overnight, intraday) positions actually held on each day."""
    return _shift(w, lag + 1) * alive, _shift(w, lag) * alive


def contributions(w: np.ndarray, market: Market, lag: int, cost_bps: float) -> np.ndarray:
    """Per-asset daily P&L (T, N) of decided positions w."""
    w_on, w_id = held_positions(w, market.alive, lag)
    cost = cost_bps / 1e4
    return w_on * market.r_on + w_id * market.r_id - cost * np.abs(w_id - w_on)


def portfolio(contrib: np.ndarray, alive: np.ndarray, group: int | None = None) -> np.ndarray:
    """Equal-weight average over listed assets. With `group`, columns are split into consecutive
    groups of that size (independent oracle paths) and a (T, n_groups) array is returned."""
    if group is None:
        return contrib.sum(axis=1) / np.maximum(alive.sum(axis=1), 1)
    T = contrib.shape[0]
    c = contrib.reshape(T, -1, group).sum(axis=2)
    n = alive.reshape(T, -1, group).sum(axis=2)
    return c / np.maximum(n, 1)


def _decided_positions(sel: Selection, market: Market) -> np.ndarray:
    w = positions(sel.spec, market.close, scope=sel.impl.scope)
    w[: max(0, sel.start - 1)] = 0.0   # nothing is held before the evaluation window opens
    return w


def _universe(sel: Selection, ds: Dataset) -> Market:
    m = ds.view(sel.impl.universe)
    return m if sel.assets is None else m.subset(list(sel.assets))


def effective_positions(sel: Selection, ds: Dataset) -> tuple[np.ndarray, np.ndarray]:
    m = _universe(sel, ds)
    return held_positions(_decided_positions(sel, m), m.alive, sel.impl.lag)


def backtest(sel: Selection, ds: Dataset, group: int | None = None) -> np.ndarray:
    """Daily portfolio returns over [start, T) as the selection's own implementation computes them.
    With `group`, the universe is treated as independent portfolios of that many assets (oracle)."""
    m = _universe(sel, ds)
    contrib = contributions(_decided_positions(sel, m), m, sel.impl.lag, sel.impl.cost_bps)
    return portfolio(contrib, m.alive, group)[sel.start:]
