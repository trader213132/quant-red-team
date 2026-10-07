from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from qrt.audits import Tier3Context, run_audits, tier3
from qrt.config import load_config
from qrt.engine import Dataset
from qrt.markets import simulate
from qrt.stats import t_stat
from qrt.workflows import build_researchers

CFG = load_config(Path(__file__).parent.parent / "configs" / "dev.toml")
R = build_researchers(CFG)


def setup(rid, seed=0, **market_changes):
    r = R[rid]
    mspec = replace(CFG.markets[r.market], **market_changes)
    cfg = replace(CFG, markets={**CFG.markets, r.market: mspec})
    ds = Dataset.from_market(simulate(mspec, np.random.default_rng(seed)))
    claim = r.run(ds)
    return Tier3Context(claim, r, ds, cfg, np.random.default_rng(seed + 1))


def test_delay_catches_lookahead():
    ctx = setup("lookahead")
    assert ctx.claim.t_stat > 2
    res = tier3.delay(ctx)
    assert res.reject and res.value < 1.0


def test_cost_stress_catches_cost_ignorer():
    ctx = setup("cost_ignorer")
    res = tier3.cost_stress(ctx)
    assert res.value < ctx.claim.t_stat and res.reject


def test_pit_universe_changes_nothing_without_delistings():
    ctx = setup("honest_trend")
    assert tier3.pit_universe(ctx).value == pytest.approx(ctx.claim.t_stat)


def test_pit_universe_restores_delisted_names_for_survivor():
    ctx = setup("survivor", seed=2)
    assert (~ctx.dataset.survivors).any()
    assert tier3.pit_universe(ctx).value < ctx.claim.t_stat


def test_holdout_reruns_workflow_on_truncated_history(monkeypatch):
    ctx = setup("miner_null")
    seen = []
    original = ctx.researcher.run

    class Spy:
        market = ctx.researcher.market

        def run(self, ds):
            seen.append(ds.n_days)
            return original(ds)

    res = tier3.holdout(replace(ctx, researcher=Spy()))
    assert seen == [round(2520 * 0.7)]
    assert res.reject is not None


def test_forward_paper_trades_honestly_on_fresh_data(monkeypatch):
    ctx = setup("lookahead")
    calls = []
    real = tier3.backtest

    def spy(sel, ds, group=None):
        calls.append((sel, ds.n_days, ds.market.n_assets))
        return real(sel, ds, group)

    monkeypatch.setattr(tier3, "backtest", spy)
    tier3.forward_1y(ctx)
    tier3.forward_3y(ctx)
    (s1, n1, a1), (s3, n3, a3) = calls
    assert (n1, n3) == (CFG.warmup + 252, CFG.warmup + 756) and a1 == a3 == 10
    assert s1.impl.lag == 1 and s1.impl.cost_bps == CFG.true_cost_bps   # honest, not lag 0


def test_forward_for_asset_picker_trades_one_asset(monkeypatch):
    ctx = setup("asset_picker")
    calls = []
    real = tier3.backtest
    monkeypatch.setattr(tier3, "backtest", lambda sel, ds, group=None: calls.append(ds.market.n_assets)
                        or real(sel, ds, group))
    tier3.forward_1y(ctx)
    assert calls == [1]


def test_placebo_accepts_a_huge_real_edge_and_rejects_lookahead():
    real = setup("honest_trend", trend_s=1e-3)
    assert real.claim.t_stat > 4
    assert tier3.placebo(real).value <= 0.04
    # Look-ahead leaks just as much on placebo data, so its p-value is ~uniform: it rejects ~95% of the
    # time (measured 95.3% over 64 seeds). At that rate, at least 4 of 6 happens 99.8% of the time.
    rejects = sum(bool(tier3.placebo(setup("lookahead", seed=s)).reject) for s in range(6))
    assert rejects >= 4


def test_run_audits_returns_all_fourteen_and_is_deterministic():
    ctx = setup("asset_picker")
    a = run_audits(ctx.claim, ctx.researcher, ctx.dataset, CFG, seed=[1, 2, 3])
    b = run_audits(ctx.claim, ctx.researcher, ctx.dataset, CFG, seed=[1, 2, 3])
    assert len(a) == 16 and a == b
    assert a["pbo"].reject is not None                     # 20 trials -> PBO applies


@pytest.mark.slow
def test_placebo_size_on_honest_null_is_at_most_alpha():
    r = R["honest_null"]
    hits = 0
    draws = 200
    for s in range(draws):
        ds = Dataset.from_market(simulate(CFG.markets["null"], np.random.default_rng(1000 + s)))
        ctx = Tier3Context(r.run(ds), r, ds, CFG, np.random.default_rng(s))
        hits += not tier3.placebo(ctx).reject
    assert hits / draws <= 0.08
