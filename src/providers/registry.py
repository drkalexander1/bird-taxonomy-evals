"""Provider selection and API-key checks shared by run_eval.py and run_probe.py."""

from __future__ import annotations

import os
import sys

from src.providers.anthropic_provider import AnthropicProvider
from src.providers.openai_provider import OpenAIProvider
from src.schema import ROOT

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
        "For a no-API smoke test: pytest -q && python -m src.validate_scenarios",
        file=sys.stderr,
    )
    raise SystemExit(1)


def get_provider(model: str, *, thinking: bool = False):
    if model.startswith("claude"):
        return AnthropicProvider(model, thinking=thinking)
    return OpenAIProvider(model)
