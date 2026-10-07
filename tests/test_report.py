import csv
from dataclasses import replace
from pathlib import Path

from qrt.config import RunParams, load_config
from qrt.experiment import run_experiment
from qrt.matrix import AUDIT_NAMES
from qrt.report import AUDITS, ROWS, load_predictions, write_prediction_template, write_report

CFG = load_config(Path(__file__).parent.parent / "configs" / "dev.toml")
TINY = replace(CFG, researchers=("lookahead", "honest_trend"), oracle_paths=8,
               run=RunParams(target_claims=3, max_runs=60, batch=8))


def test_report_and_predictions(tmp_path):
    run = run_experiment(TINY, "tiny", tmp_path / "run", workers=2, log=lambda *_: None)
    preds = tmp_path / "predictions.csv"
    write_prediction_template(preds, list(ROWS))
    with open(preds, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == len(ROWS) * len(AUDIT_NAMES)
    rows[0 + len(AUDIT_NAMES) * 4]["predicted_percent"] = "70"   # lookahead, psr
    with open(preds, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    assert load_predictions(preds) == {("lookahead", "psr"): 0.7}

    html = write_report(run, preds).read_text(encoding="utf-8")
    for rid in TINY.researchers:
        assert ROWS[rid][0] in html
    for audit in AUDIT_NAMES:
        assert AUDITS[audit][0] in html
    assert "you: 70%" in html and "DEV" in html
    assert (run / "matrix.csv").exists() and (run / "auc.csv").exists()


def test_report_without_predictions(tmp_path):
    run = run_experiment(TINY, "tiny", tmp_path / "run", workers=1, log=lambda *_: None)
    assert "No predictions found" in write_report(run, None).read_text(encoding="utf-8")
