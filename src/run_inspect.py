"""Run the taxonomy eval via Inspect AI across multiple models."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from dotenv import load_dotenv
from inspect_ai import eval_set
from inspect_ai.model import GenerateConfig, get_model

from src.inspect_task import inspect_model_id, taxonomy_eval, temp_for
from src.providers.registry import ENV_PATH, _require_api_keys
from src.run_eval import DEFAULT_MODELS
from src.schema import ROOT

DEFAULT_LOG_DIR = ROOT / "logs" / "latest"


def build_models(model_names: list[str]) -> list:
    return [
        get_model(
            inspect_model_id(name),
            config=GenerateConfig(temperature=temp_for(name)),
        )
        for name in model_names
    ]


def main(argv: list[str] | None = None) -> int:
    load_dotenv(ENV_PATH)
    parser = argparse.ArgumentParser(description="Run bird taxonomy eval via Inspect AI")
    parser.add_argument("--scenarios", type=Path, default=None)
    parser.add_argument(
        "--models",
        default=",".join(DEFAULT_MODELS),
        help="Comma-separated model ids",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR)
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Clear --log-dir before running instead of resuming from it",
    )
    args = parser.parse_args(argv)

    model_names = [m.strip() for m in args.models.split(",") if m.strip()]
    _require_api_keys(model_names)

    if args.fresh and args.log_dir.exists():
        shutil.rmtree(args.log_dir)
    args.log_dir.mkdir(parents=True, exist_ok=True)

    models = build_models(model_names)
    scenarios_arg = str(args.scenarios) if args.scenarios else None

    success, logs = eval_set(
        tasks=[taxonomy_eval(scenarios_arg)],
        model=models,
        limit=args.limit,
        log_dir=str(args.log_dir),
    )
    print(f"eval_set success={success}, {len(logs)} log(s) written to {args.log_dir}")
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
