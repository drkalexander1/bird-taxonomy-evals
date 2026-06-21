"""Run LLM evaluation over curated taxonomy scenarios."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import yaml
from dotenv import load_dotenv
from openai import AuthenticationError as OpenAIAuthenticationError

from src.providers.anthropic_provider import AnthropicProvider
from src.providers.openai_provider import OpenAIProvider
from src.schema import (
    IOC_VERSION,
    PROMPT_PATH,
    ROOT,
    PredictionRecord,
    Scenario,
    build_prompt,
    load_reference_manifest,
    load_scenarios,
)

DEFAULT_MODELS = [
    "claude-haiku-4-5",
    "claude-sonnet-4-6",
    "claude-opus-4-8",
    "gpt-4o-mini",
    "gpt-4o",
]
RESULTS_DIR = ROOT / "results" / "latest"
ENV_PATH = ROOT / ".env"


def _require_api_keys(models: list[str]) -> None:
    missing: list[str] = []
    needs_openai = any(not m.startswith("claude") for m in models)
    needs_anthropic = any(m.startswith("claude") for m in models)
    if needs_openai and not os.environ.get("OPENAI_API_KEY", "").strip():
        missing.append("OPENAI_API_KEY")
    if needs_anthropic and not os.environ.get("ANTHROPIC_API_KEY", "").strip():
        missing.append("ANTHROPIC_API_KEY")
    if not missing:
        return

    env_hint = (
        f"Create {ENV_PATH} from .env.example and set: {', '.join(missing)}"
        if not ENV_PATH.exists()
        else f"Set in {ENV_PATH}: {', '.join(missing)}"
    )
    print(
        "API key missing. " + env_hint + "\n"
        "For a no-API smoke test: python scripts/generate_demo_predictions.py",
        file=sys.stderr,
    )
    raise SystemExit(1)


def get_provider(model: str, *, thinking: bool = False):
    if model.startswith("claude"):
        return AnthropicProvider(model, thinking=thinking)
    return OpenAIProvider(model)


def report_provider_failure(
    exc: Exception,
    *,
    model: str,
    prompt_key: str,
    predictions_path: Path,
) -> None:
    if isinstance(exc, (OpenAIAuthenticationError, anthropic.AuthenticationError)):
        print(
            f"Authentication failed for {model}. "
            "Check OPENAI_API_KEY / ANTHROPIC_API_KEY in .env.",
            file=sys.stderr,
        )
        return
    saved = sum(1 for line in predictions_path.read_text(encoding="utf-8").splitlines() if line.strip())
    print(f"Failed on [{model}] {prompt_key}: {exc!r}", file=sys.stderr)
    if saved:
        print(
            f"({saved} predictions saved — re-run the same command to resume "
            f"from {predictions_path}.)",
            file=sys.stderr,
        )


def load_completed(path: Path) -> dict[tuple[str, str], PredictionRecord]:
    completed: dict[tuple[str, str], PredictionRecord] = {}
    if not path.exists():
        return completed
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)
            if "prompt_key" not in raw and "scenario_id" in raw:
                raw["prompt_key"] = raw.pop("scenario_id")
            record = PredictionRecord.model_validate(raw)
            completed[(record.prompt_key, record.model)] = record
    return completed


def run(
    prompts: list[Scenario],
    models: list[str],
    output_dir: Path,
    limit: int | None = None,
    *,
    fresh: bool = False,
    thinking: bool = False,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    subset = prompts[:limit] if limit else prompts

    predictions_path = output_dir / "predictions.jsonl"
    completed = {} if fresh else load_completed(predictions_path)
    expected = len(subset) * len(models)
    pending = expected - len(completed)

    if pending <= 0:
        print(f"Already complete: {len(completed)}/{expected} predictions in {predictions_path}")
        return predictions_path

    if completed:
        print(f"Resuming: {len(completed)}/{expected} done, {pending} remaining")
    else:
        print(
            f"Prompts: {len(subset)} "
            f"(genus={sum(1 for s in subset if s.taxonomic_level == 'genus')}, "
            f"family={sum(1 for s in subset if s.taxonomic_level == 'family')}, "
            f"order={sum(1 for s in subset if s.taxonomic_level == 'order')}) "
            f"-> {expected} API calls for {len(models)} models"
        )

    ref_manifest = load_reference_manifest()
    manifest: dict = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "models": models,
        "prompt_count": len(subset),
        "predictions_file": str(predictions_path.name),
        "prompt_template": PROMPT_PATH.name,
        "ioc_version": ref_manifest.get("ioc_version", IOC_VERSION) if ref_manifest else IOC_VERSION,
        "thinking": thinking,
    }
    if completed:
        manifest["resumed_from"] = len(completed)

    with predictions_path.open("a" if completed else "w", encoding="utf-8") as out:
        for model_name in models:
            provider = get_provider(model_name, thinking=thinking)
            for prompt in subset:
                key = (prompt.prompt_key, model_name)
                if key in completed:
                    continue
                text = build_prompt(prompt)
                try:
                    pred, latency_ms = provider.complete_structured(text)
                except Exception as exc:
                    report_provider_failure(
                        exc,
                        model=model_name,
                        prompt_key=prompt.prompt_key,
                        predictions_path=predictions_path,
                    )
                    raise SystemExit(1) from None
                record = PredictionRecord(
                    prompt_key=prompt.prompt_key,
                    model=model_name,
                    provider=provider.__class__.__name__,
                    prediction=pred,
                    latency_ms=latency_ms,
                )
                out.write(record.model_dump_json() + "\n")
                out.flush()
                print(
                    f"[{model_name}] {prompt.prompt_key} -> "
                    f"p50={pred.p50:.0f} (width={pred.p90 - pred.p10:.0f})"
                )
                time.sleep(0.2)

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    prompts_copy = output_dir / "prompts_snapshot.yaml"
    with prompts_copy.open("w", encoding="utf-8") as f:
        yaml.dump(
            [s.model_dump() for s in subset],
            f,
            default_flow_style=False,
            allow_unicode=True,
        )

    return predictions_path


def main(argv: list[str] | None = None) -> int:
    load_dotenv(ENV_PATH)
    parser = argparse.ArgumentParser(description="Run bird taxonomy hierarchy eval against LLMs")
    parser.add_argument("--scenarios", type=Path, default=ROOT / "data" / "scenarios.yaml")
    parser.add_argument("--output", type=Path, default=RESULTS_DIR)
    parser.add_argument(
        "--models",
        default=",".join(DEFAULT_MODELS),
        help="Comma-separated model ids",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Ignore existing predictions.jsonl and start over",
    )
    parser.add_argument(
        "--thinking",
        action="store_true",
        help="Enable extended thinking on Claude models (ignored for OpenAI).",
    )
    args = parser.parse_args(argv)

    prompts = load_scenarios(args.scenarios)
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    _require_api_keys(models)
    path = run(
        prompts,
        models,
        args.output,
        limit=args.limit,
        fresh=args.fresh,
        thinking=args.thinking,
    )
    print(f"Wrote predictions to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
