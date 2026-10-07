from pathlib import Path

import numpy as np
import pytest

from qrt.config import MarketSpec, load_config
from qrt.engine import Dataset, backtest
from qrt.markets import simulate
from qrt.stats import sharpe
from qrt.strategies import MINING_GRID
from qrt.workflows import build_researchers

CFG = load_config(Path(__file__).parent.parent / "configs" / "dev.toml")
R = build_researchers(CFG)


def dataset(kind="null", n_assets=4, n_days=900, seed=0, **kw):
    spec = MarketSpec(name=kind, kind=kind, n_assets=n_assets, **kw)
    return Dataset.from_market(simulate(spec, np.random.default_rng(seed), n_days=n_days))


def test_researchers_in_spec_order():
    assert list(R) == ["honest_null", "honest_trend", "miner_null", "miner_trend", "lookahead",
                       "normaliser", "cost_ignorer", "survivor", "window_picker", "asset_picker"]
    assert R["asset_picker"].market == "null20"


def test_fixed_researcher_trials_are_its_returns():
    c = R["honest_null"].run(dataset())
    assert c.trials.shape == (900 - CFG.warmup, 1)
    assert np.array_equal(c.trials[:, 0], c.returns)
    assert c.selection.impl.lag == 1 and c.selection.impl.cost_bps == CFG.true_cost_bps


def test_miner_picks_best_of_120():
    c = R["miner_null"].run(dataset())
    assert c.trials.shape == (900 - CFG.warmup, 120)
    srs = [sharpe(c.trials[:, k]) for k in range(120)]
    assert c.trial_index == int(np.argmax(srs))
    assert c.selection.spec == MINING_GRID[c.trial_index]
    assert np.array_equal(c.returns, c.trials[:, c.trial_index])


def test_window_picker_reports_from_chosen_start():
    ds = dataset(n_days=2520)
    wp = R["window_picker"]
    c = wp.run(ds)
    assert c.trials.shape == (2520 - CFG.warmup, 11)
    start = c.selection.start
    assert start in wp.starts(2520) and len(c.returns) == 2520 - start
    for k, s in enumerate(wp.starts(2520)):
        assert (c.trials[: s - CFG.warmup, k] == 0).all()
    assert len(wp.starts(1764)) == 11                      # a 70% holdout still fits all 11 starts
    assert len(wp.starts(1500)) == 8                       # shorter history -> fewer start dates
    assert max(wp.starts(1500)) <= 1500 - 252


def test_asset_picker_selects_one_asset():
    c = R["asset_picker"].run(dataset(n_assets=6))
    assert c.trials.shape == (900 - CFG.warmup, 6)
    assert c.selection.assets == (c.trial_index,)
    assert R["asset_picker"].oracle_assets(CFG.markets["null20"]) == 1


def test_survivor_sees_only_survivors():
    ds = dataset("delisting", n_assets=60, n_days=2520, annual_vol=0.6)
    assert (~ds.survivors).sum() > 0
    c = R["survivor"].run(ds)
    survivors_only = backtest(c.selection, Dataset.from_market(ds.view("survivors")))
    assert np.allclose(c.returns, survivors_only)


@pytest.mark.parametrize("rid", ["lookahead", "normaliser", "cost_ignorer"])
def test_flawed_implementations(rid):
    impl = R[rid].impl
    assert (impl.lag, impl.scope, impl.cost_bps) != (1, "expanding", CFG.true_cost_bps)
