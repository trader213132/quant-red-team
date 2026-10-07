"""Stationary bootstrap (Politis & Romano 1994): resample a time series in blocks of random
(geometric) length, so short-range dependence such as volatility clustering is kept.

Resampled means are computed as `counts @ X / T`, where counts[b, t] is how often day t appears in
replicate b. This avoids materialising a (B, T, K) array."""

from __future__ import annotations

import numpy as np


def stationary_indices(T: int, B: int, mean_block: float, rng: np.random.Generator) -> np.ndarray:
    restart = rng.random((B, T)) < 1.0 / mean_block
    fresh = rng.integers(0, T, (B, T))
    idx = np.empty((B, T), dtype=np.int64)
    idx[:, 0] = fresh[:, 0]
    for t in range(1, T):
        idx[:, t] = np.where(restart[:, t], fresh[:, t], (idx[:, t - 1] + 1) % T)
    return idx


def stationary_counts(T: int, B: int, mean_block: float, rng: np.random.Generator) -> np.ndarray:
    idx = stationary_indices(T, B, mean_block, rng)
    flat = idx + (np.arange(B) * T)[:, None]
    return np.bincount(flat.ravel(), minlength=B * T).reshape(B, T)
