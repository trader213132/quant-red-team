import numpy as np
import pytest

from qrt.config import MarketSpec
from qrt.engine import (Dataset, Implementation, Selection, backtest, contributions,
                        effective_positions, portfolio)
from qrt.markets import Market, simulate
from qrt.strategies import StrategySpec


def one_asset_market():
    r_on = np.array([0.01, -0.02, 0.03, 0.00, 0.01])[:, None]
    r_id = np.array([0.02, 0.01, -0.01, 0.02, -0.03])[:, None]
    return Market(r_on, r_id, np.ones((5, 1), dtype=bool))


@pytest.mark.parametrize("lag", [0, 1, 2])
def test_contributions_match_hand_formula(lag):
    m = one_asset_market()
    w = np.array([1.0, 1.0, -1.0, 0.0, 1.0])[:, None]
    c = 0.001  # 10 bps
    got = contributions(w, m, lag=lag, cost_bps=10.0)[:, 0]

    def wv(i):
        return w[i, 0] if i >= 0 else 0.0

    for d in range(5):
        w_on, w_id = wv(d - lag - 1), wv(d - lag)
        expect = w_on * m.r_on[d, 0] + w_id * m.r_id[d, 0] - c * abs(w_id - w_on)
        assert got[d] == pytest.approx(expect)


def test_dead_assets_contribute_nothing_and_divisor_is_alive_count():
    r_on = np.full((4, 2), 0.01)
    r_id = np.full((4, 2), 0.02)
    alive = np.array([[1, 1], [1, 1], [1, 0], [1, 0]], dtype=bool)
    m = Market(r_on, r_id, alive)
    w = np.ones((4, 2))
    contrib = contributions(w, m, lag=1, cost_bps=10.0)
    assert (contrib[2:, 1] == 0).all()                       # dead: no P&L, forced exit free
    port = portfolio(contrib, alive)
    assert port[3] == pytest.approx(contrib[3, 0])           # only one asset alive -> divisor 1
    assert port[1] == pytest.approx(contrib[1].mean())


def null_dataset(seed=0, kind="null", n_assets=5, n_days=600):
    spec = MarketSpec(name=kind, kind=kind, n_assets=n_assets)
    return Dataset.from_market(simulate(spec, np.random.default_rng(seed), n_days=n_days))


def test_backtest_length_and_warmup():
    ds = null_dataset()
    sel = Selection(StrategySpec("tsmom", (20,)), Implementation(), start=250)
    r = backtest(sel, ds)
    assert r.shape == (600 - 250,)
    later = backtest(Selection(sel.spec, sel.impl, start=400), ds)
    assert later.shape == (200,)


def test_universe_and_asset_selection():
    spec = MarketSpec(name="d", kind="delisting", n_assets=60, annual_vol=0.6)
    ds = Dataset.from_market(simulate(spec, np.random.default_rng(1)))
    assert (~ds.survivors).sum() > 0
    assert ds.view("survivors").n_assets == ds.survivors.sum()
    assert ds.view("pit").n_assets == 60
    one = backtest(Selection(StrategySpec("tsmom", (20,)), Implementation(), assets=(3,)), ds)
    m3 = Dataset.from_market(ds.market.subset([3]))
    assert np.allclose(one, backtest(Selection(StrategySpec("tsmom", (20,)), Implementation()), m3))
    sliced = ds.slice_days(0, 1000)
    assert np.array_equal(sliced.survivors, ds.survivors)    # vendor's survivor list is fixed


def perturbed(ds: Dataset, d: int, include_open: bool) -> Dataset:
    """Fresh noise for every return the decision at day d is NOT allowed to know about."""
    rng = np.random.default_rng(99)
    m = ds.market
    r_on, r_id = m.r_on.copy(), m.r_id.copy()
    r_id[d:] = rng.normal(0, 0.02, r_id[d:].shape)
    start_on = d if include_open else d + 1
    r_on[start_on:] = rng.normal(0, 0.02, r_on[start_on:].shape)
    return Dataset(Market(r_on, r_id, m.alive.copy()), ds.survivors.copy())


HONEST = [StrategySpec("tsmom", (60,)), StrategySpec("level"), StrategySpec("ma", (5, 40)),
          StrategySpec("breakout", (20,)), StrategySpec("dip", (0.3,), long_only=True)]


@pytest.mark.parametrize("spec", HONEST, ids=lambda s: s.key)
def test_honest_engine_is_causal(spec):
    ds = null_dataset(seed=3)
    sel = Selection(spec, Implementation(lag=1, scope="expanding"), start=250)
    w_on, w_id = effective_positions(sel, ds)
    for d in (300, 451, 599):
        # The intraday position on day d may know the open of day d, but not the intraday move.
        _, w_id2 = effective_positions(sel, perturbed(ds, d, include_open=False))
        assert np.array_equal(w_id[: d + 1], w_id2[: d + 1])
        # The overnight position on day d may not know the open of day d either.
        w_on2, _ = effective_positions(sel, perturbed(ds, d, include_open=True))
        assert np.array_equal(w_on[: d + 1], w_on2[: d + 1])


def test_lookahead_lag0_is_detected_by_causality_check():
    ds = null_dataset(seed=3)
    sel = Selection(StrategySpec("tsmom", (60,)), Implementation(lag=0), start=250)
    w_id = effective_positions(sel, ds)[1]
    leaks = 0
    for d in range(300, 340):
        w_id2 = effective_positions(sel, perturbed(ds, d, include_open=False))[1]
        leaks += not np.array_equal(w_id[: d + 1], w_id2[: d + 1])
    assert leaks > 0


def test_full_sample_normalisation_is_detected_by_causality_check():
    ds = null_dataset(seed=3)
    sel = Selection(StrategySpec("level"), Implementation(scope="full_sample"), start=250)
    w_id = effective_positions(sel, ds)[1]
    w_id2 = effective_positions(sel, perturbed(ds, 400, include_open=False))[1]
    assert not np.array_equal(w_id[:401], w_id2[:401])
