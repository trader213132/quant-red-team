from dataclasses import fields
from pathlib import Path

import numpy as np
import pytest

from qrt.audits import AUDITS, Tier1View, Tier2View, tier1, tier2
from qrt.bootstrap import stationary_counts
from qrt.config import load_config
from qrt.stats import expected_max_sr, moments, p_one_sided, psr, sharpe, t_stat

CFG = load_config(Path(__file__).parent.parent / "configs" / "dev.toml")


def view2(trials, index=None, seed=0, B=300):
    idx = int(np.argmax([sharpe(trials[:, k]) for k in range(trials.shape[1])])) if index is None else index
    counts = stationary_counts(trials.shape[0], B, 10.0, np.random.default_rng(seed))
    return Tier2View(trials[:, idx], trials, idx, counts)


def test_registry_and_tier_views():
    assert [a[0] for a in AUDITS] == ["psr", "dsr_assumed", "dsr", "pbo", "bonferroni", "reality_check",
                                      "spa", "placebo", "delay", "cost_stress", "pit_universe", "holdout",
                                      "forward_1y", "forward_3y"]
    assert [f.name for f in fields(Tier1View)] == ["returns"]          # tier 1 cannot see trials


def test_psr_and_dsr_assumed_follow_formulas():
    r = np.random.default_rng(1).normal(0.001, 0.01, 1500)
    sk, ku = moments(r)
    a = tier1.psr_audit(Tier1View(r), CFG)
    assert a.value == pytest.approx(psr(sharpe(r), 1500, sk, ku))
    d = tier1.dsr_assumed(Tier1View(r), CFG)
    bar = expected_max_sr(CFG.audits.dsr_assumed_n, 1 / 1500)
    assert d.value == pytest.approx(psr(sharpe(r), 1500, sk, ku, sr_star=bar))
    assert d.value < a.value


def test_dsr_with_one_trial_is_psr():
    r = np.random.default_rng(2).normal(0.001, 0.01, 800)
    v = view2(r[:, None])
    assert tier2.dsr(v, CFG).value == pytest.approx(tier1.psr_audit(Tier1View(r), CFG).value)


def test_pbo_noise_is_about_half_and_dominant_strategy_is_near_zero():
    vals = [tier2.pbo_value(np.random.default_rng(s).normal(0, 0.01, (2000, 120)), 16) for s in range(5)]
    assert 0.35 <= np.mean(vals) <= 0.65
    X = np.random.default_rng(9).normal(0, 0.01, (2000, 120))
    X[:, 7] += 0.003
    assert tier2.pbo_value(X, 16) < 0.1
    assert tier2.pbo(view2(X[:, :1]), CFG).reject is None              # one trial: not applicable


def test_bonferroni_multiplies_by_trials():
    X = np.random.default_rng(3).normal(0, 0.01, (900, 25))
    v = view2(X)
    p = p_one_sided(t_stat(v.returns), 900)
    assert tier2.bonferroni(v, CFG).value == pytest.approx(min(1.0, 25 * p))


def test_reality_check_and_spa_have_power_against_a_real_edge():
    X = np.random.default_rng(4).normal(0, 0.01, (1000, 20))
    X[:, 3] += 0.002
    v = view2(X)
    assert tier2.reality_check_p(v) < 0.05 and tier2.spa_p(v) < 0.05


def _size(n_draws, K=20, T=500):
    rc = spa = 0
    for s in range(n_draws):
        v = view2(np.random.default_rng(100 + s).normal(0, 0.01, (T, K)), seed=s)
        rc += tier2.reality_check_p(v) < 0.05
        spa += tier2.spa_p(v) < 0.05
    return rc / n_draws, spa / n_draws


def test_reality_check_and_spa_rarely_find_edges_in_noise():
    rc, spa = _size(40)
    assert rc <= 0.15 and spa <= 0.15


@pytest.mark.slow
def test_reality_check_and_spa_size_is_at_most_alpha():
    rc, spa = _size(300)
    assert rc <= 0.08 and spa <= 0.08
