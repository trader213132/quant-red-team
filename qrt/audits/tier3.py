"""Tier 3: the auditor can re-run the researcher's workflow and pipeline (a real due-diligence team).

"Re-run" goes through the researcher's OWN implementation, bugs included - the auditor can turn its
knobs (lag, costs, universe, data) but does not rewrite its code. Only the forward tests use an honest
implementation, because trading live on data that does not exist yet cannot leak the future.
"""

from __future__ import annotations

from dataclasses import replace

from qrt.engine import Dataset, backtest
from qrt.markets import simulate
from qrt.stats import t_stat


def _result(**kw):
    from qrt.audits import AuditResult
    return AuditResult(**kw)


def _attack(ctx, **impl_changes):
    """Re-run the claimed selection with some implementation knobs changed; reject if the edge is no
    longer significant."""
    sel = ctx.claim.selection
    r = backtest(replace(sel, impl=replace(sel.impl, **impl_changes)), ctx.dataset)
    t = t_stat(r)
    return _result(score=t, reject=t < ctx.cfg.audits.attack_t, value=t)


def placebo(ctx):
    """Falsification audit: run the WHOLE workflow on copies of its own data with every return's sign
    randomised (zero edge by construction, same volatility). If the workflow 'finds' edges this good
    in data that has none, its finding is not evidence."""
    own = ctx.dataset.view(ctx.claim.selection.impl.universe)
    observed = ctx.claim.sharpe
    reps = ctx.cfg.audits.placebo_reps
    beaten = sum(ctx.researcher.run(Dataset.from_market(own.flip(ctx.rng))).sharpe >= observed
                 for _ in range(reps))
    p = (1 + beaten) / (reps + 1)
    return _result(score=-p, reject=p > ctx.cfg.alpha, value=p)


def delay(ctx):
    return _attack(ctx, lag=ctx.claim.selection.impl.lag + 1)


def cost_stress(ctx):
    return _attack(ctx, cost_bps=ctx.cfg.true_cost_bps * ctx.cfg.audits.cost_stress_mult)


def pit_universe(ctx):
    return _attack(ctx, universe="pit")


def holdout(ctx):
    """Let the workflow see only the first 70% of the history, then test what it picks on the rest."""
    cut = int(round(ctx.dataset.n_days * ctx.cfg.audits.holdout_frac))
    picked = ctx.researcher.run(ctx.dataset.slice_days(0, cut)).selection
    r = backtest(replace(picked, start=cut), ctx.dataset)
    t = t_stat(r)
    return _result(score=t, reject=t < ctx.cfg.audits.attack_t, value=t)


def _forward(ctx, days: int):
    """Paper-trade the claimed rule honestly on brand-new data from the same market."""
    from qrt.workflows import honest_selection
    mspec = ctx.cfg.markets[ctx.researcher.market]
    n = ctx.researcher.oracle_assets(mspec)
    fresh = simulate(mspec, ctx.rng, n_assets=n, n_days=ctx.cfg.warmup + days)
    r = backtest(honest_selection(ctx.claim, ctx.cfg), Dataset.from_market(fresh))
    t = t_stat(r)
    return _result(score=t, reject=t < ctx.cfg.audits.attack_t, value=t)


def forward_1y(ctx):
    return _forward(ctx, ctx.cfg.audits.forward_short_days)


def forward_3y(ctx):
    return _forward(ctx, ctx.cfg.audits.forward_long_days)
