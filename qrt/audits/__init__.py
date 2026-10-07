"""The auditors: fourteen ways to decide whether a claimed edge is credible.

Access tiers are enforced by construction. A tier-1 audit is handed only the reported returns, a tier-2
audit also gets every trial the researcher ran, and a tier-3 audit can re-run the researcher's workflow
and pipeline. No audit ever sees the oracle.

Every audit returns an AuditResult:
  reject - True means "this edge is not credible"; None means the audit does not apply (e.g. PBO with
           a single trial).
  score  - higher means "more credible"; used for the threshold-free AUC comparison.
  value  - the audit's natural statistic (a p-value, PBO, PSR, or t-stat) for the report.
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass

import numpy as np

from qrt.bootstrap import stationary_counts
from qrt.config import Config
from qrt.engine import Dataset


@dataclass(frozen=True)
class AuditResult:
    score: float | None
    reject: bool | None
    value: float | None = None

    @staticmethod
    def not_applicable() -> AuditResult:
        return AuditResult(None, None, None)


@dataclass(frozen=True)
class Tier1View:
    returns: np.ndarray


@dataclass(frozen=True)
class Tier2View:
    returns: np.ndarray
    trials: np.ndarray
    trial_index: int
    boot_counts: np.ndarray   # (B, T_trials) stationary-bootstrap resampling counts (randomness only)


@dataclass
class Tier3Context:
    claim: object             # workflows.Claim
    researcher: object        # workflows.Researcher
    dataset: Dataset
    cfg: Config
    rng: np.random.Generator


from qrt.audits import tier1, tier2, tier3  # noqa: E402  (registry below needs the modules)

AUDITS: tuple[tuple[str, int, object], ...] = (
    ("psr", 1, tier1.psr_audit),
    ("dsr_assumed", 1, tier1.dsr_assumed),
    ("dsr", 2, tier2.dsr),
    ("pbo", 2, tier2.pbo),
    ("bonferroni", 2, tier2.bonferroni),
    ("reality_check", 2, tier2.reality_check),
    ("spa", 2, tier2.spa),
    ("placebo", 3, tier3.placebo),
    ("delay", 3, tier3.delay),
    ("cost_stress", 3, tier3.cost_stress),
    ("pit_universe", 3, tier3.pit_universe),
    ("holdout", 3, tier3.holdout),
    ("forward_1y", 3, tier3.forward_1y),
    ("forward_3y", 3, tier3.forward_3y),
)
TIER = {name: tier for name, tier, _ in AUDITS}


def audit_rng(seed, name: str) -> np.random.Generator:
    """Each audit gets its own stream, so adding or removing one never changes another's randomness."""
    return np.random.default_rng([*np.atleast_1d(seed).tolist(), zlib.crc32(name.encode())])


def tier2_view(claim, cfg: Config, rng: np.random.Generator) -> Tier2View:
    T = claim.trials.shape[0]
    counts = stationary_counts(T, cfg.audits.bootstrap_reps, cfg.audits.bootstrap_block, rng)
    return Tier2View(claim.returns, claim.trials, claim.trial_index, counts)


def run_audits(claim, researcher, dataset: Dataset, cfg: Config, seed,
               only: tuple[str, ...] | None = None) -> dict[str, AuditResult]:
    t1 = Tier1View(claim.returns)
    t2 = tier2_view(claim, cfg, audit_rng(seed, "bootstrap"))
    out: dict[str, AuditResult] = {}
    for name, tier, fn in AUDITS:
        if only is not None and name not in only:
            continue
        if tier == 1:
            out[name] = fn(t1, cfg)
        elif tier == 2:
            out[name] = fn(t2, cfg)
        else:
            out[name] = fn(Tier3Context(claim, researcher, dataset, cfg, audit_rng(seed, name)))
    return out
