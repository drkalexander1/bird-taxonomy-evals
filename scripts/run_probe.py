"""Run optional taxonomy probes (no IOC ground truth, not part of main eval)."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv

from src.run_eval import ENV_PATH, _require_api_keys, get_provider
from src.schema import ROOT, PredictionRecord

PROBE_PROMPT_PATH = ROOT / "prompts" / "taxonomy_extinct.txt"
DEFAULT_PROBES = ROOT / "data" / "probes" / "theropod.yaml"
RESULTS_DIR = ROOT / "results" / "probes"


def load_probes(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    probes = raw.get("probes", [])
    if not isinstance(probes, list) or not probes:
        raise ValueError(f"No probes found in {path}")
    return probes


def build_probe_prompt(taxonomic_unit: str) -> str:
    template = PROBE_PROMPT_PATH.read_text(encoding="utf-8")
    return template.format(taxonomic_unit=taxonomic_unit)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    load_dotenv(ENV_PATH)
    parser = argparse.ArgumentParser(
        description="Run extinct-species taxonomy probes (theropod sanity check)"
    )
    parser.add_argument("--probes", type=Path, default=DEFAULT_PROBES)
    parser.add_argument("--output", type=Path, default=RESULTS_DIR)
    parser.add_argument("--models", default="gpt-4o-mini", help="Comma-separated model ids")
    args = parser.parse_args(argv)

    if not PROBE_PROMPT_PATH.exists():
        print(f"Missing prompt template: {PROBE_PROMPT_PATH}", file=sys.stderr)
        return 1

    probes = load_probes(args.probes)
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    _require_api_keys(models)

    args.output.mkdir(parents=True, exist_ok=True)
    out_path = args.output / "predictions.jsonl"
    manifest_path = args.output / "manifest.json"

    records: list[dict] = []
    for model_name in models:
        provider = get_provider(model_name)
        for probe in probes:
            prompt_key = probe["id"]
            prompt = build_probe_prompt(probe["taxonomic_unit"])
            print(f"\n--- {prompt_key} / {model_name} ---")
            print(prompt[:280] + "...\n")
            try:
                pred, latency_ms = provider.complete_structured(prompt)
            except Exception as exc:
                print(f"Failed [{model_name}] {prompt_key}: {exc!r}", file=sys.stderr)
                return 1
            record = PredictionRecord(
                prompt_key=prompt_key,
                model=model_name,
                provider=provider.__class__.__name__,
                prediction=pred,
                latency_ms=latency_ms,
            )
            records.append(record.model_dump())
            print(
                f"p10={pred.p10:.0f}  p50={pred.p50:.0f}  p90={pred.p90:.0f}  "
                f"width={pred.p90 - pred.p10:.0f}  confidence={pred.confidence:.2f}"
            )
            print(f"reasoning: {pred.reasoning}")
            time.sleep(0.2)

    with out_path.open("w", encoding="utf-8") as f:
        for row in records:
            f.write(json.dumps(row) + "\n")

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "probe_file": str(args.probes.name),
        "prompt_template": PROBE_PROMPT_PATH.name,
        "models": models,
        "probes": probes,
        "note": "No ground truth — qualitative sanity check only",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nWrote {len(records)} predictions to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
