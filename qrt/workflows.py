"""The researchers: complete research workflows, honest and flawed, that turn a dataset into a Claim.

A workflow is deterministic given its data, so an auditor with re-run access can feed it other data
(placebo markets, a truncated history) and watch what it claims then.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from qrt.config import Config, MarketSpec
from qrt.engine import Dataset, Implementation, Selection, backtest, honest_implementation
from qrt.stats import annual_sharpe, sharpe, t_stat
from qrt.strategies import MINING_GRID, StrategySpec

WINDOW_STEP = 126        # the window picker tries a new start date every six months...
WINDOW_STARTS = 11       # ...eleven of them...
WINDOW_MIN_DAYS = 252    # ...as long as at least a year of backtest remains


@dataclass
class Claim:
    selection: Selection
    returns: np.ndarray      # the reported daily returns
    trials: np.ndarray       # (T_eval, K): every variant tried, aligned on the evaluation window
    trial_index: int         # which column was selected

    @property
    def t_stat(self) -> float:
        return t_stat(self.returns)

    @property
    def sharpe(self) -> float:
        return annual_sharpe(self.returns)

    @property
    def n_trials(self) -> int:
        return self.trials.shape[1]


def _best(columns: list[np.ndarray]) -> int:
    return int(np.argmax([sharpe(c) for c in columns]))


@dataclass(frozen=True)
class FixedResearcher:
    """Backtests one pre-chosen rule once. Honest, unless its implementation carries a bug."""
    id: str
    market: str
    spec: StrategySpec
    impl: Implementation
    warmup: int

    def run(self, ds: Dataset) -> Claim:
        sel = Selection(self.spec, self.impl, None, self.warmup)
        r = backtest(sel, ds)
        return Claim(sel, r, r[:, None], 0)

    def oracle_assets(self, market: MarketSpec) -> int:
        return market.n_assets


@dataclass(frozen=True)
class Miner:
    """Backtests every rule in a grid and reports the best in-sample Sharpe (parameter mining)."""
    id: str
    market: str
    grid: tuple[StrategySpec, ...]
    impl: Implementation
    warmup: int

    def run(self, ds: Dataset) -> Claim:
        sels = [Selection(s, self.impl, None, self.warmup) for s in self.grid]
        cols = [backtest(s, ds) for s in sels]
        k = _best(cols)
        return Claim(sels[k], cols[k], np.column_stack(cols), k)

    def oracle_assets(self, market: MarketSpec) -> int:
        return market.n_assets


@dataclass(frozen=True)
class WindowPicker:
    """Runs one rule from several start dates and reports the period that looks best."""
    id: str
    market: str
    spec: StrategySpec
    impl: Implementation
    warmup: int

    def starts(self, n_days: int) -> list[int]:
        cands = (self.warmup + WINDOW_STEP * k for k in range(WINDOW_STARTS))
        return [s for s in cands if s <= n_days - WINDOW_MIN_DAYS]

    def run(self, ds: Dataset) -> Claim:
        sels = [Selection(self.spec, self.impl, None, s) for s in self.starts(ds.n_days)]
        cols = [backtest(s, ds) for s in sels]
        k = _best(cols)
        width = ds.n_days - self.warmup
        trials = np.column_stack([np.concatenate([np.zeros(width - len(c)), c]) for c in cols])
        return Claim(sels[k], cols[k], trials, k)

    def oracle_assets(self, market: MarketSpec) -> int:
        return market.n_assets


@dataclass(frozen=True)
class AssetPicker:
    """Runs one rule on each asset separately and reports the asset where it worked best."""
    id: str
    market: str
    spec: StrategySpec
    impl: Implementation
    warmup: int

    def run(self, ds: Dataset) -> Claim:
        n = ds.view(self.impl.universe).n_assets
        sels = [Selection(self.spec, self.impl, (k,), self.warmup) for k in range(n)]
        cols = [backtest(s, ds) for s in sels]
        k = _best(cols)
        return Claim(sels[k], cols[k], np.column_stack(cols), k)

    def oracle_assets(self, market: MarketSpec) -> int:
        return 1


Researcher = FixedResearcher | Miner | WindowPicker | AssetPicker


def build_researchers(cfg: Config) -> dict[str, Researcher]:
    honest = honest_implementation(cfg.true_cost_bps)
    w = cfg.warmup
    tsmom60 = StrategySpec("tsmom", (60,))
    every = {
        "honest_null": FixedResearcher("honest_null", "null", tsmom60, honest, w),
        "honest_trend": FixedResearcher("honest_trend", "trend", tsmom60, honest, w),
        "miner_null": Miner("miner_null", "null", MINING_GRID, honest, w),
        "miner_trend": Miner("miner_trend", "trend", MINING_GRID, honest, w),
        "lookahead": FixedResearcher("lookahead", "null", tsmom60, replace(honest, lag=0), w),
        "normaliser": FixedResearcher("normaliser", "null", StrategySpec("level"),
                                      replace(honest, scope="full_sample"), w),
        "cost_ignorer": FixedResearcher("cost_ignorer", "reversal", StrategySpec("rev", (1,)),
                                        replace(honest, cost_bps=0.0), w),
        "survivor": FixedResearcher("survivor", "delisting", StrategySpec("dip", (0.3,), long_only=True),
                                    replace(honest, universe="survivors"), w),
        "window_picker": WindowPicker("window_picker", "null", tsmom60, honest, w),
        "asset_picker": AssetPicker("asset_picker", "null20", tsmom60, honest, w),
    }
    return {rid: every[rid] for rid in cfg.researchers}


def honest_selection(claim: Claim, cfg: Config) -> Selection:
    """What the claim would look like done properly: same rule, honest implementation, every asset."""
    return Selection(claim.selection.spec, honest_implementation(cfg.true_cost_bps), None, cfg.warmup)
