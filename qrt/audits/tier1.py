"""Tier 1: the auditor sees only the reported daily returns (a fund pitch)."""

from __future__ import annotations

from qrt.stats import expected_max_sr, moments, psr, sharpe


def psr_audit(view, cfg):
    from qrt.audits import AuditResult
    r = view.returns
    skew, kurt = moments(r)
    p = psr(sharpe(r), len(r), skew, kurt)
    return AuditResult(score=p, reject=p < cfg.audits.psr_threshold, value=p)


def dsr_assumed(view, cfg):
    """Deflated Sharpe when the number of trials is unknown: assume `dsr_assumed_n` independent
    zero-edge trials, whose Sharpe estimates would each have variance about 1/T."""
    from qrt.audits import AuditResult
    r = view.returns
    n = len(r)
    skew, kurt = moments(r)
    bar = expected_max_sr(cfg.audits.dsr_assumed_n, 1.0 / n)
    d = psr(sharpe(r), n, skew, kurt, sr_star=bar)
    return AuditResult(score=d, reject=d < cfg.audits.dsr_threshold, value=d)

