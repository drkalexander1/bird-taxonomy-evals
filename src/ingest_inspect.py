"""Bridge Inspect AI .eval logs back into the existing score.py scoring pipeline."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from inspect_ai.log import list_eval_logs, read_eval_log

from src.schema import ROOT, PredictionRecord, load_scenario_cells, load_scenarios, parse_prediction
from src.score import score_predictions

SCORER_NAME = "taxonomy_scorer"
DEFAULT_OUT_DIR = ROOT / "results" / "latest_inspect"


def _provider_for_model(model: str) -> str:
    # Mirrors run_eval.get_provider()'s prefix check, applied to the bare
    # model name (Inspect's log.eval.model strips the "provider/" role prefix
    # by the time it reaches PredictionRecord — see read_predictions_from_logs).
    return "AnthropicProvider" if model.startswith("claude") else "OpenAIProvider"


def read_predictions_from_logs(log_dir: Path) -> list[PredictionRecord]:
    records: list[PredictionRecord] = []
    skipped = 0
    for log_info in list_eval_logs(str(log_dir)):
        log = read_eval_log(log_info)
        model = log.eval.model.split("/", 1)[-1]  # strip "anthropic/"/"openai/" role prefix
        provider = _provider_for_model(model)
        for sample in log.samples or []:
            score = (sample.scores or {}).get(SCORER_NAME)
            if score is None:
                skipped += 1
                continue
            value = score.value
            if isinstance(value, float) and math.isnan(value):
                skipped += 1
                continue
            try:
                # Same parse_prediction() the scorer used to build `answer` in the first
                # place — one parsing path, not a second reconstruction from metadata.
                prediction = parse_prediction(json.loads(score.answer))
            except Exception:
                skipped += 1
                continue
            latency_ms = (score.metadata or {}).get("latency_ms")
            records.append(
                PredictionRecord(
                    prompt_key=str(sample.id),
                    model=model,
                    provider=provider,
                    prediction=prediction,
                    latency_ms=latency_ms,
                    raw_response=sample.output.completion if sample.output else None,
                )
            )
    if skipped:
        print(f"Skipped {skipped} sample(s) with missing/failed scores")
    return records


def score_inspect_run(
    log_dir: Path,
    scenarios_path: Path | None = None,
    out_dir: Path | None = None,
) -> dict:
    cells = load_scenario_cells(scenarios_path)
    prompts = load_scenarios(scenarios_path)
    predictions = read_predictions_from_logs(log_dir)
    if not predictions:
        raise ValueError(f"No scored predictions found under {log_dir}")
    return score_predictions(cells, prompts, predictions, out_dir or DEFAULT_OUT_DIR)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score predictions from Inspect AI eval logs")
    parser.add_argument("--log-dir", type=Path, required=True)
    parser.add_argument("--scenarios", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args(argv)

    summary = score_inspect_run(args.log_dir, scenarios_path=args.scenarios, out_dir=args.out)
    print(summary["overall"])
    print(f"Wrote summary to {args.out / 'summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
