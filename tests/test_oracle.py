from dataclasses import replace
from pathlib import Path

import pytest

from qrt.config import load_config
from qrt.oracle import _needs, label, oracle_key, oracle_sharpes
from qrt.strategies import StrategySpec
from qrt.workflows import build_researchers

CFG = load_config(Path(__file__).parent.parent / "configs" / "dev.toml")
TSMOM60 = StrategySpec("tsmom", (60,))


def test_honest_momentum_in_null_market_has_no_edge():
    key = oracle_key("null", TSMOM60, 10)
    gross = oracle_sharpes(replace(CFG, true_cost_bps=0.0), "null", 10, [TSMOM60], paths=64)[key]
    net = oracle_sharpes(CFG, "null", 10, [TSMOM60], paths=64)[key]
    assert abs(gross) < 0.13          # martingale: zero edge before costs (about 3 standard errors)
    assert net < gross                # costs only subtract


def test_reversal_edge_is_real_gross_but_negative_net():
    rev1 = StrategySpec("rev", (1,))
    gross = oracle_sharpes(replace(CFG, true_cost_bps=0.0), "reversal", 10, [rev1], paths=64)
    net = oracle_sharpes(CFG, "reversal", 10, [rev1], paths=64)
    assert gross[oracle_key("reversal", rev1, 10)] > 0.3
    assert net[oracle_key("reversal", rev1, 10)] < 0.0


def test_buy_the_dip_has_no_edge_on_the_point_in_time_universe():
    dip = StrategySpec("dip", (0.3,), long_only=True)
    free = replace(CFG, true_cost_bps=0.0)
    sr = oracle_sharpes(free, "delisting", 50, [dip], paths=48)[oracle_key("delisting", dip, 50)]
    assert abs(sr) < 0.15             # zero gross edge once delisted names are counted


def test_deterministic():
    a = oracle_sharpes(CFG, "null", 10, [TSMOM60], paths=8)
    b = oracle_sharpes(CFG, "null", 10, [TSMOM60], paths=8)
    assert a == b


def test_labels():
    assert label(0.0, CFG) == "FAKE" and label(0.05, CFG) == "FAKE"
    assert label(0.1, CFG) == "MARGINAL"
    assert label(0.2, CFG) == "REAL"


def test_needs_cover_every_researcher():
    needs = _needs(CFG, build_researchers(CFG))
    assert len(needs[("null", 10)]) == 120 + 1          # miner grid (incl. tsmom60) + level
    assert needs[("null20", 1)] == [TSMOM60]
    assert ("delisting", 50) in needs and ("reversal", 10) in needs and ("trend", 10) in needs
