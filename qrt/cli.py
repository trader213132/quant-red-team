"""Command line: python -m qrt {run,report,predictions}."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from qrt.config import load_config

ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="qrt")
    sub = ap.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="run the experiment and write the report")
    run.add_argument("--config", default=str(ROOT / "configs" / "dev.toml"))
    run.add_argument("--out", default=None, help="output folder (default results/<config>-<timestamp>)")
    run.add_argument("--workers", type=int, default=16)
    run.add_argument("--final", action="store_true",
                     help="a one-time final run: writes to results/final[-<config>] and locks it")

    rep = sub.add_parser("report", help="rebuild matrix.csv, auc.csv and report.html for a run folder")
    rep.add_argument("run_dir")

    sub.add_parser("predictions", help="write a blank predictions.csv template")

    args = ap.parse_args(argv)
    predictions = ROOT / "predictions.csv"

    if args.cmd == "run":
        from qrt.experiment import run_experiment
        from qrt.report import write_report
        cfg = load_config(args.config)
        if args.final:   # configs/final.toml -> results/final (v1); configs/v2.toml -> results/final-v2
            stem = Path(args.config).stem
            out = ROOT / "results" / ("final" if stem == "final" else f"final-{stem}")
        else:
            out = Path(args.out) if args.out else (
                ROOT / "results" / f"{Path(args.config).stem}-{datetime.now():%Y%m%d-%H%M%S}")
        run_experiment(cfg, args.config, out, workers=args.workers, final=args.final)
        print(f"report: {write_report(out, predictions)}")
    elif args.cmd == "report":
        from qrt.report import write_report
        print(f"report: {write_report(Path(args.run_dir), predictions)}")
    elif args.cmd == "predictions":
        from qrt.report import ROWS, write_prediction_template
        if predictions.exists():
            raise SystemExit(f"{predictions} already exists - not overwriting your guesses")
        write_prediction_template(predictions, list(ROWS))
        print(f"wrote {predictions}")


if __name__ == "__main__":
    main()
