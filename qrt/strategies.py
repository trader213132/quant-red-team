"""Trading rules. Each turns a (T, N) close-price panel into positions in {-1, 0, +1} decided at each close.

Every rule is causal (uses closes up to and including t) EXCEPT `level` with scope="full_sample", which
standardises prices with the mean/std of the whole sample - the classic leak this project studies.
Positions are 0 until a rule has enough history.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import maximum_filter1d, minimum_filter1d

LEVEL_MIN_OBS = 60
LEVEL_Z_ENTRY = 0.5
DIP_LOOKBACK = 252


@dataclass(frozen=True)
class StrategySpec:
    family: str                  # tsmom | ma | rev | breakout | level | dip
    params: tuple = ()
    long_only: bool = False

    @property
    def key(self) -> str:
        args = ",".join(f"{p:g}" for p in self.params)
        return f"{self.family}({args})/{'LO' if self.long_only else 'LS'}"


def rolling_max(x: np.ndarray, L: int) -> np.ndarray:
    """Max over the trailing window [t-L+1, t]; shorter (expanding) windows at the start."""
    return maximum_filter1d(x, size=L, axis=0, origin=(L - 1) // 2, mode="nearest")


def rolling_min(x: np.ndarray, L: int) -> np.ndarray:
    return minimum_filter1d(x, size=L, axis=0, origin=(L - 1) // 2, mode="nearest")


def _lookback_return(close: np.ndarray, L: int) -> np.ndarray:
    out = np.zeros_like(close)
    out[L:] = close[L:] / close[:-L] - 1
    return out


def _moving_average(close: np.ndarray, L: int) -> np.ndarray:
    c = np.vstack([np.zeros((1, close.shape[1])), np.cumsum(close, axis=0)])
    out = np.full_like(close, np.nan)
    out[L - 1:] = (c[L:] - c[:-L]) / L
    return out


def _forward_fill_nonzero(raw: np.ndarray) -> np.ndarray:
    """Hold the most recent nonzero signal (rows before any signal stay 0)."""
    T = raw.shape[0]
    idx = np.where(raw != 0, np.arange(T)[:, None], 0)
    idx = np.maximum.accumulate(idx, axis=0)
    return np.take_along_axis(raw, idx, axis=0)


def _level_z(close: np.ndarray, scope: str) -> np.ndarray:
    logp = np.log(close)
    if scope == "full_sample":
        # BUG ON PURPOSE: uses the future to define "normal".
        mean = logp.mean(axis=0, keepdims=True)
        std = logp.std(axis=0, keepdims=True)
        z = (logp - mean) / np.where(std > 0, std, np.inf)
        z[: LEVEL_MIN_OBS - 1] = 0.0
        return z
    if scope != "expanding":
        raise ValueError(f"unknown scope {scope!r}")
    n = np.arange(1, len(logp) + 1)[:, None]
    mean = np.cumsum(logp, axis=0) / n
    var = np.maximum(np.cumsum(logp**2, axis=0) / n - mean**2, 0.0)
    std = np.sqrt(var)
    z = np.zeros_like(logp)
    ok = (n >= LEVEL_MIN_OBS) & (std > 0)
    z[ok] = ((logp - mean)[ok]) / std[ok]
    return z


def positions(spec: StrategySpec, close: np.ndarray, scope: str = "expanding") -> np.ndarray:
    fam, p = spec.family, spec.params
    if fam == "tsmom":
        pos = np.sign(_lookback_return(close, p[0]))
    elif fam == "rev":
        pos = -np.sign(_lookback_return(close, p[0]))
    elif fam == "ma":
        fast, slow = _moving_average(close, p[0]), _moving_average(close, p[1])
        pos = np.nan_to_num(np.sign(fast - slow))
    elif fam == "breakout":
        L = p[0]
        raw = np.where(close == rolling_max(close, L), 1.0, 0.0) - np.where(close == rolling_min(close, L), 1.0, 0.0)
        raw[: L - 1] = 0.0
        pos = _forward_fill_nonzero(raw)
    elif fam == "level":
        z = _level_z(close, scope)
        pos = np.where(np.abs(z) > LEVEL_Z_ENTRY, -np.sign(z), 0.0)
    elif fam == "dip":
        drawdown = close / rolling_max(close, DIP_LOOKBACK) - 1
        pos = np.where(drawdown <= -p[0], 1.0, 0.0)
    else:
        raise ValueError(f"unknown family {fam!r}")
    pos = pos.astype(float)
    if spec.long_only:
        pos = np.maximum(pos, 0.0)
    return pos


def _mining_grid() -> tuple[StrategySpec, ...]:
    base: list[tuple[str, tuple]] = []
    base += [("tsmom", (L,)) for L in (5, 10, 15, 20, 30, 40, 60, 90, 120, 180, 250)]
    base += [("ma", (f, s)) for f in (3, 5, 10, 20, 30, 50) for s in (40, 60, 100, 150, 200, 250) if f < s]
    base += [("rev", (L,)) for L in (1, 2, 3, 4, 5, 7, 10)]
    base += [("breakout", (L,)) for L in (10, 20, 50, 100, 150, 200, 250)]
    return tuple(StrategySpec(fam, params, lo) for lo in (False, True) for fam, params in base)


MINING_GRID = _mining_grid()
