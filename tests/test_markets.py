import numpy as np
import pytest
from scipy import stats

from qrt.config import MarketSpec
from qrt.markets import Market, simulate


def spec(kind="null", **kw):
    return MarketSpec(name=kind, kind=kind, n_assets=kw.pop("n_assets", 10), **kw)


def rng(seed=0):
    return np.random.default_rng(seed)


def total(m: Market) -> np.ndarray:
    return (1 + m.r_on) * (1 + m.r_id) - 1


def test_shapes_and_prices():
    m = simulate(spec(), rng(), n_days=300)
    assert m.r_on.shape == m.r_id.shape == m.alive.shape == (300, 10)
    assert np.allclose(m.close[0], (1 + m.r_on[0]) * (1 + m.r_id[0]))
    assert np.allclose(m.close[5], m.close[4] * (1 + m.r_on[5]) * (1 + m.r_id[5]))
    assert np.allclose(m.open[5], m.close[4] * (1 + m.r_on[5]))
    assert m.alive.all()


def test_deterministic_for_seed():
    a = simulate(spec("trend", trend_s=1e-4), rng(7))
    b = simulate(spec("trend", trend_s=1e-4), rng(7))
    assert np.array_equal(a.r_on, b.r_on) and np.array_equal(a.r_id, b.r_id)


def test_null_is_mean_zero_fat_tailed_and_clustered():
    m = simulate(spec(n_assets=80), rng(1))
    r = total(m)
    t = r.mean() / r.std(ddof=1) * np.sqrt(r.size)
    assert abs(t) < 4
    assert stats.kurtosis(r.ravel(), fisher=False) > 4
    a = np.abs(r)
    lag1 = np.mean([np.corrcoef(a[1:, i], a[:-1, i])[0, 1] for i in range(r.shape[1])])
    assert lag1 > 0.05


def test_null_daily_vol_matches_annual_target():
    m = simulate(spec(n_assets=80), rng(2))
    daily = total(m).std()
    assert daily * np.sqrt(252) == pytest.approx(0.25, rel=0.1)


def test_trend_makes_momentum_predictive():
    m = simulate(spec("trend", n_assets=50, trend_s=1e-3), rng(3))
    r = total(m)
    past = np.sign(np.log(m.close[60:-1] / m.close[:-61]))
    nxt = r[61:]
    assert np.mean(past * nxt) > 0
    assert np.corrcoef(past.ravel(), nxt.ravel())[0, 1] > 0.02


def test_reversal_autocorrelation_matches_design():
    theta = -0.05
    m = simulate(spec("reversal", n_assets=200, reversal_theta=theta), rng(4))
    r = m.r_on + m.r_id
    ac = np.corrcoef(r[1:].ravel(), r[:-1].ravel())[0, 1]
    assert ac == pytest.approx(theta / (1 + theta**2), abs=0.02)


def test_delisting_removes_assets_after_first_close_below_level():
    m = simulate(spec("delisting", n_assets=200, annual_vol=0.4, delist_level=0.3), rng(5))
    dead_any = ~m.alive[-1]
    assert dead_any.sum() > 10                     # some assets do die
    for col in np.flatnonzero(dead_any)[:20]:
        first_dead = np.argmin(m.alive[:, col])     # first False
        assert m.close[first_dead - 1, col] < 0.3   # previous close crossed the level
        assert (m.close[: first_dead - 1, col] >= 0.3).all()
        assert not m.alive[first_dead:, col].any()  # never comes back
        assert (m.r_on[first_dead:, col] == 0).all() and (m.r_id[first_dead:, col] == 0).all()
    for col in np.flatnonzero(m.alive[-1])[:20]:
        assert (m.close[:, col] >= 0.3).all()


def test_subset_slice_flip():
    m = simulate(spec(), rng(6), n_days=400)
    s = m.subset([1, 3])
    assert s.r_on.shape == (400, 2) and np.array_equal(s.r_id[:, 1], m.r_id[:, 3])
    d = m.slice_days(0, 100)
    assert d.r_on.shape == (100, 10) and np.allclose(d.close, m.close[:100])
    f = m.flip(rng(8))
    assert np.allclose(np.abs(f.r_on), np.abs(m.r_on)) and np.allclose(np.abs(f.r_id), np.abs(m.r_id))
    changed = np.mean(np.sign(f.r_id) != np.sign(m.r_id))
    assert 0.45 < changed < 0.55
    assert np.array_equal(f.alive, m.alive)
