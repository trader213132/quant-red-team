import numpy as np
import pytest

from qrt.strategies import MINING_GRID, StrategySpec, positions, rolling_max, rolling_min


def naive_roll(x, L, fn):
    out = np.empty_like(x)
    for t in range(len(x)):
        out[t] = fn(x[max(0, t - L + 1): t + 1], axis=0)
    return out


@pytest.mark.parametrize("L", [1, 2, 3, 10])
def test_rolling_max_min_match_naive(L):
    x = np.random.default_rng(0).normal(size=(50, 3))
    assert np.allclose(rolling_max(x, L), naive_roll(x, L, np.max))
    assert np.allclose(rolling_min(x, L), naive_roll(x, L, np.min))


def col(*values):
    return np.array(values, dtype=float)[:, None]


def test_tsmom_and_rev():
    close = col(1, 2, 1.5, 1.6, 1.0)
    pos = positions(StrategySpec("tsmom", (2,)), close)
    assert pos[:, 0].tolist() == [0, 0, 1, -1, -1]   # 1.5/1 up, 1.6/2 down, 1.0/1.5 down
    assert positions(StrategySpec("rev", (2,)), close)[:, 0].tolist() == [0, 0, -1, 1, 1]


def test_ma_crossover():
    close = col(1, 2, 3, 2, 1, 1)
    pos = positions(StrategySpec("ma", (2, 3)), close)[:, 0]
    # t=2: MA2=2.5, MA3=2 -> +1; t=3: 2.5 vs 2.333 -> +1; t=4: 1.5 vs 2 -> -1; t=5: 1 vs 1.333 -> -1
    assert pos.tolist() == [0, 0, 1, 1, -1, -1]


def test_breakout_holds_last_signal():
    close = col(1, 2, 3, 2.5, 2.6, 1, 1.5)
    pos = positions(StrategySpec("breakout", (3,)), close)[:, 0]
    # t=2: 3 is the 3-day high -> +1; t=3,4 hold; t=5: 1 is the 3-day low -> -1; t=6 hold
    assert pos.tolist() == [0, 0, 1, 1, 1, -1, -1]


def test_level_full_sample_differs_from_expanding():
    close = np.exp(np.cumsum(np.random.default_rng(1).normal(0, 0.02, (400, 2)), axis=0))
    honest = positions(StrategySpec("level"), close, scope="expanding")
    leaky = positions(StrategySpec("level"), close, scope="full_sample")
    assert set(np.unique(honest)) <= {-1.0, 0.0, 1.0}
    assert (honest[:59] == 0).all()                     # needs 60 observations
    assert not np.array_equal(honest, leaky)


def test_dip_long_only_on_drawdown():
    close = col(1, 1.2, 0.9, 0.8, 1.0)
    pos = positions(StrategySpec("dip", (0.3,), long_only=True), close)[:, 0]
    # drawdown from running high 1.2: 0.9 -> -25%, 0.8 -> -33%, 1.0 -> -17%
    assert pos.tolist() == [0, 0, 0, 1, 0]


def test_long_only_clips():
    close = col(1, 2, 1.5, 1.6, 1.0)
    pos = positions(StrategySpec("tsmom", (2,), long_only=True), close)[:, 0]
    assert pos.tolist() == [0, 0, 1, 0, 0]


def test_mining_grid():
    assert len(MINING_GRID) == 120
    assert len({s.key for s in MINING_GRID}) == 120
    assert StrategySpec("tsmom", (60,)).key == "tsmom(60)/LS"
    assert StrategySpec("ma", (5, 40), long_only=True).key == "ma(5,40)/LO"
