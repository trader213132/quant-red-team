"""Small statistical helpers shared by researchers, audits and the matrix. Sharpe ratios are per day
unless the name says `annual`."""

from __future__ import annotations

import numpy as np
from scipy import stats as sps

from qrt import TRADING_DAYS

EULER_GAMMA = 0.5772156649015329


def sharpe(r: np.ndarray) -> float:
    sd = np.std(r, ddof=1)
    return float(np.mean(r) / sd) if sd > 0 else 0.0


def annual_sharpe(r: np.ndarray) -> float:
    return sharpe(r) * np.sqrt(TRADING_DAYS)


def t_stat(r: np.ndarray) -> float:
    return sharpe(r) * np.sqrt(len(r))


def p_one_sided(t: float, n: int) -> float:
    """P(T >= t) under 'no edge', Student-t with n-1 degrees of freedom."""
    return float(sps.t.sf(t, n - 1))


def moments(r: np.ndarray) -> tuple[float, float]:
    """(skewness, kurtosis) - kurtosis is NOT excess: a normal distribution has 3."""
    if np.std(r) == 0:
        return 0.0, 3.0
    return float(sps.skew(r)), float(sps.kurtosis(r, fisher=False))


def psr(sr: float, n: int, skew: float, kurt: float, sr_star: float = 0.0) -> float:
    """Probabilistic Sharpe Ratio (Bailey & Lopez de Prado 2012): the probability that the true
    per-period Sharpe exceeds sr_star, allowing for skewness and fat tails in the returns."""
    var = 1 - skew * sr + (kurt - 1) / 4 * sr**2
    return float(sps.norm.cdf((sr - sr_star) * np.sqrt(n - 1) / np.sqrt(max(var, 1e-12))))


def expected_max_sr(n_trials: int, var_sr: float) -> float:
    """Expected maximum Sharpe of n_trials zero-edge strategies whose Sharpe estimates have variance
    var_sr (Bailey & Lopez de Prado 2014). This is the bar a selected strategy must clear."""
    if n_trials <= 1:
        return 0.0
    g = EULER_GAMMA
    z = (1 - g) * sps.norm.ppf(1 - 1 / n_trials) + g * sps.norm.ppf(1 - 1 / (n_trials * np.e))
    return float(np.sqrt(var_sr) * z)


def wilson_ci(k: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    """95% Wilson score interval for a proportion k/n (well-behaved at 0% and 100%)."""
    if n == 0:
        return float("nan"), float("nan")
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return float(max(0.0, centre - half)), float(min(1.0, centre + half))


def auc(pos, neg) -> float:
    """P(score of a random positive > score of a random negative), ties count half."""
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    return float(sps.mannwhitneyu(pos, neg).statistic / (len(pos) * len(neg)))
