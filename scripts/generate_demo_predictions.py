"""Generate synthetic predictions for results/demo (no API keys)."""

from __future__ import annotations

import json
from pathlib import Path

from src.schema import Prediction, PredictionRecord, load_scenarios

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results" / "demo"


def synthetic_quantiles(sc, model: str) -> tuple[float, float, float]:
    target = float(sc.ioc_count)
    if "mini" in model:
        half = max(0.2 * target, 2.0)
        p50 = target * 1.1
        return max(p50 - half, 0.0), p50, p50 + half
    if "bad" in model:
        if sc.taxonomic_level == "genus":
            p50 = float(sc.ioc_family) * 1.2
        elif sc.taxonomic_level == "family":
            p50 = float(sc.ioc_family)
        else:
            p50 = float(sc.ioc_order)
        half = max(0.15 * p50, 3.0)
        return max(p50 - half, 0.0), p50, p50 + half
    p50 = target
    half = max(0.25 * target, 5.0)
    return max(p50 - half, 0.0), p50, p50 + half


def main() -> None:
    prompts = load_scenarios()
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "predictions.jsonl"
    models = ["gpt-4o-mini-demo", "gpt-4o-demo", "gpt-4o-bad-demo"]

    with path.open("w", encoding="utf-8") as f:
        for model in models:
            for i, prompt in enumerate(prompts):
                p10, p50, p90 = synthetic_quantiles(prompt, model)
                pred = Prediction(
                    p10=p10,
                    p50=p50,
                    p90=p90,
                    confidence=0.85 if "mini" in model else 0.75,
                    reasoning="Synthetic demo prediction for pipeline test.",
                )
                rec = PredictionRecord(
                    prompt_key=prompt.prompt_key,
                    model=model,
                    provider="DemoProvider",
                    prediction=pred,
                    latency_ms=100.0 + i,
                )
                f.write(rec.model_dump_json() + "\n")

    manifest = {
        "created_at": "demo",
        "models": models,
        "prompt_count": len(prompts),
        "predictions_file": "predictions.jsonl",
        "note": "Synthetic data for scoring smoke test only",
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Wrote {len(prompts) * len(models)} lines to {path}")


if __name__ == "__main__":
    main()
