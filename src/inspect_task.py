"""Inspect AI task for the taxonomy calibration eval.

Owns per-sample generation and per-sample scoring (CRPS against the IOC point
target). Cross-sample analysis (hierarchy consistency, cell classification,
cross-model power analysis) is NOT done here — Inspect's metric system only
reduces scores within one model's one log to a scalar, so those stay in
score.py, fed from Inspect's .eval logs via ingest_inspect.py instead.
"""

from __future__ import annotations

import json
from pathlib import Path

from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.model import GenerateConfig, ResponseSchema
from inspect_ai.scorer import Score, Scorer, Target, mean, scorer, stderr
from inspect_ai.solver import TaskState, generate
from inspect_ai.util import json_schema
from pydantic import ValidationError

from src.schema import EXPECTED_UNIQUE_PROMPTS, Prediction, build_prompt, load_scenarios, parse_prediction
from src.score import crps_point_target

# Anthropic models from claude-opus-4-6 onward (and claude-sonnet-5) reject an
# explicit `temperature` param outright (confirmed live: 400 "temperature is
# deprecated for this model"). Older Anthropic families and OpenAI's non-reasoning
# models still accept temperature=0. Ported from
# anthropic_provider._anthropic_supports_temperature / openai_provider._openai_supports_temperature.
_ANTHROPIC_TEMPERATURE_OK_PREFIXES = ("claude-haiku-", "claude-sonnet-4", "claude-3-")
_OPENAI_NO_TEMPERATURE_PREFIXES = ("gpt-5", "o3", "o4")


def temp_for(model_name: str) -> float | None:
    """Return the temperature to request for this model, or None to omit the param."""
    if model_name.startswith("claude"):
        return 0.0 if model_name.startswith(_ANTHROPIC_TEMPERATURE_OK_PREFIXES) else None
    return None if model_name.startswith(_OPENAI_NO_TEMPERATURE_PREFIXES) else 0.0


def inspect_model_id(model_name: str) -> str:
    """Bare model name (e.g. 'claude-sonnet-5') -> Inspect provider/model role string."""
    provider = "anthropic" if model_name.startswith("claude") else "openai"
    return f"{provider}/{model_name}"


def taxonomy_dataset(scenarios_path: Path | None = None) -> MemoryDataset:
    scenarios = load_scenarios(scenarios_path)
    samples = [
        Sample(
            input=build_prompt(scenario),
            target=str(scenario.ioc_count),
            id=scenario.prompt_key,
            metadata=scenario.model_dump(),
        )
        for scenario in scenarios
    ]
    # load_scenarios() already dedups shared family/order prompts to the 46
    # unique elicitations. Looping over load_scenario_cells()+expand_cell()
    # instead would silently reintroduce 72 samples with duplicate ids.
    assert len(samples) == EXPECTED_UNIQUE_PROMPTS, (
        f"Expected {EXPECTED_UNIQUE_PROMPTS} unique prompts, got {len(samples)}"
    )
    return MemoryDataset(samples, name="taxonomy")


@scorer(metrics=[mean(), stderr()])
def taxonomy_scorer() -> Scorer:
    async def score(state: TaskState, target: Target) -> Score:
        completion = state.output.completion
        try:
            prediction = parse_prediction(json.loads(completion))
        except (json.JSONDecodeError, ValidationError) as exc:
            return Score(
                value=float("nan"),
                answer=completion,
                explanation=f"{type(exc).__name__}: {exc}",
            )

        ioc_count = float(state.metadata["ioc_count"])
        scale = max(ioc_count, 1.0)
        crps = crps_point_target(prediction.p10, prediction.p50, prediction.p90, ioc_count)
        latency_ms = state.output.time * 1000 if state.output.time is not None else None

        return Score(
            value=crps / scale,
            # `answer` is the single source of truth for the Prediction — ingest_inspect.py
            # reconstructs it by calling the same parse_prediction() used here, rather than
            # a second, parallel reconstruction from hand-picked metadata fields.
            answer=json.dumps(prediction.model_dump()),
            metadata={"latency_ms": latency_ms},
        )

    return score


@task
def taxonomy_eval(scenarios_path: str | None = None) -> Task:
    path = Path(scenarios_path) if scenarios_path else None
    return Task(
        dataset=taxonomy_dataset(path),
        solver=[generate()],
        scorer=taxonomy_scorer(),
        config=GenerateConfig(
            response_schema=ResponseSchema(
                name="taxonomy_species_prediction",
                json_schema=json_schema(Prediction),
                strict=True,
            )
        ),
    )
