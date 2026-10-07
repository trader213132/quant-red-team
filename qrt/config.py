"""Experiment configuration: TOML file -> frozen dataclasses, plus fingerprints for reproducibility."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

PACKAGE_DIR = Path(__file__).parent


@dataclass(frozen=True)
class MarketSpec:
    name: str
    kind: str                      # null | trend | reversal | delisting
    n_assets: int
    n_days: int = 2520             # 10 years
    annual_vol: float = 0.25
    garch_a: float = 0.08
    garch_b: float = 0.90
    t_df: float = 5.0
    overnight_frac: float = 0.3    # share of each day's variance that arrives overnight
    sigma_cap: float = 0.04        # daily volatility ceiling, keeps simple returns above -1
    trend_rho: float = 0.99
    trend_s: float = 0.0
    reversal_theta: float = -0.05
    delist_level: float = 0.30


@dataclass(frozen=True)
class AuditParams:
    psr_threshold: float = 0.95
    dsr_threshold: float = 0.95
    dsr_assumed_n: int = 100
    pbo_blocks: int = 16
    pbo_threshold: float = 0.5
    bootstrap_reps: int = 500
    bootstrap_block: float = 10.0
    placebo_reps: int = 49
    attack_t: float = 1.645
    cost_stress_mult: float = 2.0
    holdout_frac: float = 0.7
    forward_short_days: int = 252
    forward_long_days: int = 756


@dataclass(frozen=True)
class RunParams:
    target_claims: int = 300
    max_runs: int = 20000
    batch: int = 64


@dataclass(frozen=True)
class Config:
    seed: int
    warmup: int
    true_cost_bps: float
    claim_t: float
    alpha: float
    fake_max: float
    real_min: float
    researchers: tuple[str, ...]
    markets: dict[str, MarketSpec] = field(default_factory=dict)
    audits: AuditParams = AuditParams()
    run: RunParams = RunParams()
    oracle_paths: int = 256


def load_config(path: str | Path) -> Config:
    raw = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    markets = {name: MarketSpec(name=name, **spec) for name, spec in raw.pop("markets").items()}
    audits = AuditParams(**raw.pop("audits", {}))
    run = RunParams(**raw.pop("run", {}))
    oracle_paths = raw.pop("oracle", {}).get("paths", 256)
    researchers = tuple(raw.pop("researchers"))
    return Config(markets=markets, audits=audits, run=run, oracle_paths=oracle_paths,
                  researchers=researchers, **raw)


def config_hash(cfg: Config) -> str:
    """SHA-256 of the parsed config, so formatting/comment changes do not count as a new config."""
    canonical = json.dumps(dataclasses.asdict(cfg), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def code_hash() -> str:
    """SHA-256 over every source file in the package: pins exactly which code produced a result.
    Line endings are normalised, so a Windows checkout and a Linux clone hash the same (see D21)."""
    digest = hashlib.sha256()
    for path in sorted(PACKAGE_DIR.rglob("*.py")):
        digest.update(path.relative_to(PACKAGE_DIR).as_posix().encode("utf-8"))
        digest.update(path.read_bytes().replace(b"
", b"
"))
    return digest.hexdigest()
