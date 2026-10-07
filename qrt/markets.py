"""Simulated markets with a known truth.

Every day d has an overnight simple return r_on[d] (close d-1 -> open d) and an intraday one r_id[d]
(open d -> close d). Noise is GARCH(1,1) with Student-t shocks, so tests cannot get lucky by assuming
tidy normal returns. Each market kind plants (or deliberately does not plant) a specific edge:

- null:      prices are martingales -> every causal strategy has zero expected gross return.
- trend:     a hidden, slowly drifting mean -> momentum has a real edge.
- reversal:  a tiny one-day reversal -> real gross edge that trading costs destroy.
- delisting: null, but assets that fall below a price level are removed (the survivorship trap).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property

import numpy as np
from scipy.signal import lfilter

from qrt import TRADING_DAYS
from qrt.config import MarketSpec

SHOCK_CLIP = 20.0  # symmetric clip on standardised shocks: keeps the mean exactly zero


@dataclass
class Market:
    r_on: np.ndarray   # (T, N) overnight simple returns
    r_id: np.ndarray   # (T, N) intraday simple returns
    alive: np.ndarray  # (T, N) bool: listed at the open of day d (tradable on day d)

    @property
    def n_days(self) -> int:
        return self.r_on.shape[0]

    @property
    def n_assets(self) -> int:
        return self.r_on.shape[1]

    @cached_property
    def close(self) -> np.ndarray:
        return np.cumprod((1 + self.r_on) * (1 + self.r_id), axis=0)

    @cached_property
    def open(self) -> np.ndarray:
        prev = np.vstack([np.ones((1, self.n_assets)), self.close[:-1]])
        return prev * (1 + self.r_on)

    def subset(self, cols) -> Market:
        cols = np.asarray(cols)
        return Market(self.r_on[:, cols], self.r_id[:, cols], self.alive[:, cols])

    def slice_days(self, start: int, stop: int) -> Market:
        return Market(self.r_on[start:stop], self.r_id[start:stop], self.alive[start:stop])

    def flip(self, rng: np.random.Generator) -> Market:
        """Placebo copy: random independent signs on every return. Keeps the size of every move (so
        volatility clustering survives) but destroys any predictable direction -> exactly zero edge."""
        s_on = rng.integers(0, 2, self.r_on.shape) * 2 - 1
        s_id = rng.integers(0, 2, self.r_id.shape) * 2 - 1
        return Market(self.r_on * s_on, self.r_id * s_id, self.alive.copy())


def _standard_t(rng: np.random.Generator, df: float, shape) -> np.ndarray:
    z = rng.standard_t(df, shape) / np.sqrt(df / (df - 2))  # unit variance
    return np.clip(z, -SHOCK_CLIP, SHOCK_CLIP)


def _garch_noise(spec: MarketSpec, rng: np.random.Generator, T: int, N: int):
    var_d = spec.annual_vol**2 / TRADING_DAYS
    a, b = spec.garch_a, spec.garch_b
    omega = var_d * (1 - a - b)
    z_on = _standard_t(rng, spec.t_df, (T, N))
    z_id = _standard_t(rng, spec.t_df, (T, N))
    f_on, f_id = np.sqrt(spec.overnight_frac), np.sqrt(1 - spec.overnight_frac)
    e_on = np.empty((T, N))
    e_id = np.empty((T, N))
    sigma2 = np.full(N, var_d)
    for d in range(T):
        sigma = np.minimum(np.sqrt(sigma2), spec.sigma_cap)
        e_on[d] = f_on * sigma * z_on[d]
        e_id[d] = f_id * sigma * z_id[d]
        e = e_on[d] + e_id[d]
        sigma2 = omega + a * e * e + b * sigma * sigma
    return e_on, e_id


def simulate(spec: MarketSpec, rng: np.random.Generator, n_assets: int | None = None,
             n_days: int | None = None) -> Market:
    T = n_days or spec.n_days
    N = n_assets or spec.n_assets
    e_on, e_id = _garch_noise(spec, rng, T, N)
    f = spec.overnight_frac

    if spec.kind in ("null", "delisting"):
        r_on, r_id = e_on, e_id
    elif spec.kind == "trend":
        # Hidden drift mu[d] = rho * mu[d-1] + eta[d], started from its stationary distribution.
        rho, s = spec.trend_rho, spec.trend_s
        eta = rng.normal(0.0, s, (T, N))
        eta[0] = rng.normal(0.0, s / np.sqrt(1 - rho**2), N)
        mu = lfilter([1.0], [1.0, -rho], eta, axis=0)
        r_on, r_id = e_on + f * mu, e_id + (1 - f) * mu
    elif spec.kind == "reversal":
        # R[d] = e[d] + theta * e[d-1]: yesterday's shock partly reverses today.
        m = np.zeros((T, N))
        m[1:] = spec.reversal_theta * (e_on[:-1] + e_id[:-1])
        r_on, r_id = e_on + f * m, e_id + (1 - f) * m
    else:
        raise ValueError(f"unknown market kind {spec.kind!r}")

    alive = np.ones((T, N), dtype=bool)
    if spec.kind == "delisting":
        close = np.cumprod((1 + r_on) * (1 + r_id), axis=0)
        below = close < spec.delist_level
        has = below.any(axis=0)
        first = np.where(has, below.argmax(axis=0), T)       # day of the first close below the level
        dead = np.arange(T)[:, None] > first[None, :]         # delisted from the next day on
        r_on = np.where(dead, 0.0, r_on)
        r_id = np.where(dead, 0.0, r_id)
        alive = ~dead
    return Market(r_on, r_id, alive)
