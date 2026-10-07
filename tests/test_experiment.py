import json
from dataclasses import replace
from pathlib import Path

import pytest

from qrt.config import RunParams, load_config
from qrt.experiment import run_case, run_experiment
from qrt.oracle import build_oracle_table
from qrt.workflows import build_researchers

CFG = load_config(Path(__file__).parent.parent / "configs" / "dev.toml")
TINY = replace(CFG, researchers=("lookahead", "asset_picker"), oracle_paths=8,
               run=RunParams(target_claims=3, max_runs=60, batch=8))


@pytest.fixture(scope="module")
def oracle():
    return build_oracle_table(TINY, build_researchers(TINY))


def test_run_case_is_deterministic_and_complete(oracle):
    a = run_case(TINY, "lookahead", 0, oracle)
    b = run_case(TINY, "lookahead", 0, oracle)
    assert a == b and a["label"] in ("FAKE", "REAL", "MARGINAL") and len(a["audits"]) == 16
    assert a["lag"] == 0 and a["t"] >= TINY.claim_t


def test_run_case_returns_none_without_a_claim(oracle):
    results = [run_case(TINY, "asset_picker", i, oracle) for i in range(12)]
    assert any(r is None for r in results)
    assert all(r is None or r["t"] >= TINY.claim_t for r in results)


def _read(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_experiment_is_identical_for_one_and_two_workers(tmp_path):
    one = run_experiment(TINY, "tiny", tmp_path / "w1", workers=1, log=lambda *_: None)
    two = run_experiment(TINY, "tiny", tmp_path / "w2", workers=2, log=lambda *_: None)
    for rid in TINY.researchers:
        a, b = _read(one / f"cases_{rid}.jsonl"), _read(two / f"cases_{rid}.jsonl")
        assert len(a) == 3 and a == b
    manifest = json.loads((one / "manifest.json").read_text())
    assert manifest["rows"]["lookahead"]["claims"] == 3


def test_final_run_locks(tmp_path):
    out = run_experiment(TINY, "tiny", tmp_path / "final", workers=1, final=True, log=lambda *_: None)
    assert (out / "LOCK").exists()
    with pytest.raises(RuntimeError, match="locked"):
        run_experiment(TINY, "tiny", out, workers=1, final=True, log=lambda *_: None)
