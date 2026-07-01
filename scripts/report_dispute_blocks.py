"""Report undisputed vs disputed blocks after derive_ioc_counts.py."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.schema import SCENARIOS_PATH


def _load_derive_module():
    path = Path(__file__).resolve().parent / "derive_ioc_counts.py"
    spec = importlib.util.spec_from_file_location("derive_ioc_counts", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize authority dispute blocks in scenarios")
    parser.add_argument("--scenarios", type=Path, default=SCENARIOS_PATH)
    args = parser.parse_args(argv)

    derive = _load_derive_module()
    derive.inspect_scenarios(args.scenarios)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
