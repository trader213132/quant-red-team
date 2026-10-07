"""Tests for the two audits added in v2 (dsr_eff, full_history) and for v1/v2 report compatibility."""

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from qrt.audits import Tier1View, Tier2View, Tier3Context, tier1, tier2, tier3
from qrt.bootstrap import stationary_counts
from qrt.config import MarketSpec, load_config
from qrt.engine import Dataset, backtest
from qrt.markets import simulate
from qrt.matrix import AUDIT_NAMES, audits_in, build_matrix
from qrt.stats import sharpe, t_stat
from qrt.workflows import build_researchers

CFG = load_config(Path(__file__).parent.parent / "configs" / "dev.toml")
R = build_researchers(CFG)


def view2(trials):
    idx = int(np.argmax([sharpe(trials[:, k]) for k in range(trials.shape[1])]))
    counts = stationary_counts(trials.shape[0], 50, 10.0, np.random.default_rng(0))
    return Tier2View(trials[:, idx], trials, idx, counts)


def test_effective_trials_counts_independent_tries():
    rng = np.random.default_rng(1)
    base = rng.normal(0, 0.01, (2000, 1))
    assert tier2.effective_trials(np.repeat(base, 30, axis=1)) == pytest.approx(1.0, abs=1e-6)
    indep = tier2.effective_trials(rng.normal(0, 0.01, (2000, 30)))
    assert 0.85 * 30 < indep <= 30
    with_flat = np.column_stack([rng.normal(0, 0.01, (2000, 5)), np.zeros(2000)])
    assert tier2.effective_trials(with_flat) <= 5.0 + 1e-9                  # a flat trial is not a try


def test_dsr_eff_with_one_trial_is_psr():
    r = np.random.default_rng(2).normal(0.001, 0.01, 800)
    assert tier2.dsr_eff(view2(r[:, None]), CFG).value == pytest.approx(tier1.psr_audit(Tier1View(r), CFG).value)


def test_dsr_eff_does_not_punish_genuinely_different_strategies():
    """Strategies with truly different edges: v1's DSR counts that spread as luck, dsr_eff does not."""
    rng = np.random.default_rng(3)
    drifts = np.linspace(-0.0012, 0.0012, 40)                 # true annual Sharpes from about -1.9 to +1.9
    X = rng.normal(0, 0.01, (2270, 40)) + drifts
    v = view2(X)
    assert tier2.dsr(v, CFG).reject                             # v1 rule: the spread pushes the bar too high
    assert not tier2.dsr_eff(v, CFG).reject                     # v2 rule: the best is clearly real


def test_dsr_eff_still_deflates_pure_noise_selection():
    rejects = sum(bool(tier2.dsr_eff(view2(np.random.default_rng(10 + s).normal(0, 0.01, (2270, 120))), CFG).reject)
                  for s in range(20))
    assert rejects >= 18


def test_full_history_reruns_from_the_earliest_date():
    r = R["window_picker"]
    for seed in range(40):
        ds = Dataset.from_market(simulate(CFG.markets["null"], np.random.default_rng(seed)))
        claim = r.run(ds)
        if claim.selection.start > CFG.warmup:
            break
    ctx = Tier3Context(claim, r, ds, CFG, np.random.default_rng(0))
    expected = t_stat(backtest(replace(claim.selection, start=CFG.warmup), ds))
    assert tier3.full_history(ctx).value == pytest.approx(expected)
    assert len(backtest(replace(claim.selection, start=CFG.warmup), ds)) > len(claim.returns)


def test_full_history_changes_nothing_when_already_full():
    r = R["honest_trend"]
    spec = replace(CFG.markets["trend"])
    ds = Dataset.from_market(simulate(spec, np.random.default_rng(5)))
    claim = r.run(ds)
    ctx = Tier3Context(claim, r, ds, CFG, np.random.default_rng(0))
    assert tier3.full_history(ctx).value == pytest.approx(claim.t_stat)


def test_matrix_handles_v1_runs_without_the_new_audits():
    v1_names = [a for a in AUDIT_NAMES if a not in ("dsr_eff", "full_history")]
    case = {"row": "x", "label": "FAKE", "audits": {a: {"reject": True, "score": 0.0, "value": 0.0} for a in v1_names}}
    assert audits_in([case]) == v1_names
    assert {m["audit"] for m in build_matrix([case])} == set(v1_names)
