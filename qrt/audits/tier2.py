"""Tier 2: the auditor also sees every trial the researcher ran (an honest paper that discloses its
search). Trials are a (T, K) matrix of daily returns aligned on the evaluation window."""

from __future__ import annotations

from functools import lru_cache
from itertools import combinations

import numpy as np

from qrt.stats import expected_max_sr, moments, p_one_sided, psr, sharpe, t_stat


def _result(**kw):
    from qrt.audits import AuditResult
    return AuditResult(**kw)


def dsr(view, cfg):
    """Deflated Sharpe Ratio (Bailey & Lopez de Prado 2014) with the disclosed number of trials K and
    the observed spread of their Sharpe ratios. With K = 1 there is nothing to deflate: it is the PSR."""
    r = view.returns
    K = view.trials.shape[1]
    bar = 0.0
    if K > 1:
        srs = np.array([sharpe(view.trials[:, k]) for k in range(K)])
        bar = expected_max_sr(K, float(np.var(srs, ddof=1)))
    skew, kurt = moments(r)
    d = psr(sharpe(r), len(r), skew, kurt, sr_star=bar)
    return _result(score=d, reject=d < cfg.audits.dsr_threshold, value=d)


def effective_trials(trials: np.ndarray) -> float:
    """How many independent tries the trials amount to: the participation ratio (sum lambda)^2 / sum lambda^2
    of their correlation matrix's eigenvalues. K uncorrelated trials give ~K; K identical trials give 1."""
    X = trials[:, np.std(trials, axis=0) > 0]
    if X.shape[1] <= 1:
        return 1.0
    lam = np.clip(np.linalg.eigvalsh(np.corrcoef(X, rowvar=False)), 0.0, None)
    return float(lam.sum() ** 2 / (lam ** 2).sum())


def dsr_eff(view, cfg):
    """v2 (designed after v1): Deflated Sharpe whose bar is the best Sharpe expected from N_eff independent
    ZERO-edge trials, using the null estimation variance 1/T. v1's DSR used the observed spread of trial
    Sharpes, which counts genuine differences between strategies as luck."""
    r = view.returns
    n = len(r)
    n_eff = effective_trials(view.trials)
    bar = max(0.0, expected_max_sr(n_eff, 1.0 / n)) if n_eff > 1 else 0.0
    skew, kurt = moments(r)
    d = psr(sharpe(r), n, skew, kurt, sr_star=bar)
    return _result(score=d, reject=d < cfg.audits.dsr_threshold, value=d)


@lru_cache(maxsize=4)
def _cscv_splits(S: int) -> np.ndarray:
    """All ways to choose half of S blocks as the in-sample set: a (C(S, S/2), S) 0/1 matrix."""
    rows = [[1.0 if b in c else 0.0 for b in range(S)] for c in combinations(range(S), S // 2)]
    return np.array(rows)


def _sr_from_sums(total, sq, n):
    mean = total / n
    var = np.maximum(sq / n - mean * mean, 0.0) * n / (n - 1)
    sd = np.sqrt(var)
    return np.divide(mean, sd, out=np.zeros_like(mean), where=sd > 1e-15)


def pbo_value(trials: np.ndarray, S: int) -> float:
    """Probability of Backtest Overfitting via CSCV (Bailey, Borwein, Lopez de Prado & Zhu 2017): over
    every split of the history into in-sample and out-of-sample halves, how often does the in-sample
    winner land in the bottom half out-of-sample?"""
    T, K = trials.shape
    per = T // S
    X = trials[T - per * S:].reshape(S, per, K)
    bsum, bsq = X.sum(axis=1), (X * X).sum(axis=1)
    M = _cscv_splits(S)
    n_half = per * S // 2
    is_sr = _sr_from_sums(M @ bsum, M @ bsq, n_half)
    oos_sr = _sr_from_sums((1 - M) @ bsum, (1 - M) @ bsq, n_half)
    best = np.argmax(is_sr, axis=1)
    chosen = oos_sr[np.arange(len(best)), best][:, None]
    below = (oos_sr < chosen).sum(axis=1)
    ties = (oos_sr == chosen).sum(axis=1) - 1
    rank = below + 1 + 0.5 * ties                     # 1 = worst out-of-sample, K = best
    w = rank / (K + 1)
    logit = np.log(w / (1 - w))
    return float(np.mean(logit <= 0))


def pbo(view, cfg):
    if view.trials.shape[1] < 2:
        return _result(score=None, reject=None, value=None)
    p = pbo_value(view.trials, cfg.audits.pbo_blocks)
    return _result(score=1 - p, reject=p > cfg.audits.pbo_threshold, value=p)


def bonferroni(view, cfg):
    """Multiply the selected strategy's p-value by the number of trials (Harvey, Liu & Zhu 2016 use
    this family of corrections). Ignores correlation between trials, so it is conservative."""
    r = view.returns
    K = view.trials.shape[1]
    adj = min(1.0, K * p_one_sided(t_stat(r), len(r)))
    return _result(score=-adj, reject=adj >= cfg.alpha, value=adj)


def _boot_means(view):
    X = view.trials
    n = X.shape[0]
    return X.mean(axis=0), view.boot_counts @ X / n, n


def reality_check_p(view) -> float:
    """White (2000): is the best of the K strategies better than zero, once we account for having
    picked the best? Bootstrap distribution of the max, recentred on the observed means."""
    means, mstar, n = _boot_means(view)
    v = np.sqrt(n) * means.max()
    vstar = np.sqrt(n) * (mstar - means).max(axis=1)
    return float(np.mean(vstar >= v))


def spa_p(view) -> float:
    """Hansen (2005) consistent SPA: studentised, and poor strategies (clearly negative means) are
    recentred so they cannot inflate the null distribution of the max.

    Studentised with each strategy's sample standard deviation. Daily strategy returns are serially
    uncorrelated in these markets, so this is a consistent long-run variance estimate - and far less
    noisy than the block-bootstrap estimate, which oversized the test (11.7% at alpha = 5%, T = 500)."""
    means, mstar, n = _boot_means(view)
    omega = np.std(view.trials, axis=0, ddof=1)
    ok = omega > 1e-15
    if not ok.any():
        return 1.0
    means, mstar, omega = means[ok], mstar[:, ok], omega[ok]
    t = np.sqrt(n) * means / omega
    observed = max(t.max(), 0.0)
    keep_negative = t <= -np.sqrt(2 * np.log(np.log(n)))
    mu_c = np.where(keep_negative, means, 0.0)
    z = np.sqrt(n) * (mstar - means + mu_c) / omega
    tstar = np.maximum(z.max(axis=1), 0.0)
    return float(np.mean(tstar >= observed))


def reality_check(view, cfg):
    p = reality_check_p(view)
    return _result(score=-p, reject=p >= cfg.alpha, value=p)


def spa(view, cfg):
    p = spa_p(view)
    return _result(score=-p, reject=p >= cfg.alpha, value=p)
