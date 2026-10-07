import numpy as np
import pytest
from scipy import stats as sps

from qrt.bootstrap import stationary_counts, stationary_indices
from qrt.stats import (annual_sharpe, auc, expected_max_sr, moments, p_one_sided, psr, sharpe,
                       t_stat, wilson_ci)


def test_t_stat_matches_scipy():
    r = np.random.default_rng(0).normal(0.001, 0.01, 500)
    assert t_stat(r) == pytest.approx(sps.ttest_1samp(r, 0).statistic)
    assert p_one_sided(t_stat(r), len(r)) == pytest.approx(sps.ttest_1samp(r, 0, alternative="greater").pvalue)
    assert annual_sharpe(r) == pytest.approx(sharpe(r) * np.sqrt(252))
    assert sharpe(np.zeros(10)) == 0.0 and t_stat(np.zeros(10)) == 0.0


def test_psr_is_close_to_normal_cdf_of_t_for_gaussian_returns():
    r = np.random.default_rng(1).normal(0.0005, 0.01, 2000)
    skew, kurt = moments(r)
    assert psr(sharpe(r), len(r), skew, kurt) == pytest.approx(sps.norm.cdf(t_stat(r)), abs=0.01)


def test_psr_penalises_negative_skew_and_fat_tails():
    sr, n = 0.05, 1000
    assert psr(sr, n, -1.0, 10.0) < psr(sr, n, 0.0, 3.0)


def test_expected_max_sr_against_monte_carlo():
    assert expected_max_sr(1, 0.01) == 0.0
    mc = np.random.default_rng(2).standard_normal((20000, 100)).max(axis=1).mean()
    assert expected_max_sr(100, 1.0) == pytest.approx(mc, rel=0.05)
    assert expected_max_sr(100, 4.0) == pytest.approx(2 * expected_max_sr(100, 1.0))


def test_wilson_ci_known_values():
    lo, hi = wilson_ci(0, 10)
    assert lo == pytest.approx(0.0, abs=1e-12) and hi == pytest.approx(0.2775, abs=1e-3)
    lo, hi = wilson_ci(5, 10)
    assert lo == pytest.approx(0.2366, abs=1e-3) and hi == pytest.approx(0.7634, abs=1e-3)
    assert all(np.isnan(wilson_ci(0, 0)))


def test_auc():
    assert auc([3, 4, 5], [0, 1, 2]) == 1.0
    assert auc([0, 1, 2], [3, 4, 5]) == 0.0
    assert auc([1, 1], [1, 1]) == 0.5


def test_stationary_bootstrap_counts():
    rng = np.random.default_rng(3)
    counts = stationary_counts(300, 200, 10.0, rng)
    assert counts.shape == (200, 300)
    assert (counts.sum(axis=1) == 300).all()
    assert counts.mean() == pytest.approx(1.0)
    again = stationary_counts(300, 200, 10.0, np.random.default_rng(3))
    assert np.array_equal(counts, again)


def test_stationary_bootstrap_mean_block_length():
    idx = stationary_indices(5000, 50, 10.0, np.random.default_rng(4))
    continues = (idx[:, 1:] == (idx[:, :-1] + 1) % 5000)
    mean_run = idx.size / (idx.shape[0] + (~continues).sum())
    assert mean_run == pytest.approx(10.0, abs=1.0)
