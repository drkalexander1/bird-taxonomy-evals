"""Report undisputed vs disputed blocks after derive_ioc_counts.py."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from src.schema import SCENARIOS_PATH, load_scenario_cells, load_scenarios


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize authority dispute blocks in scenarios")
    parser.add_argument("--scenarios", type=Path, default=SCENARIOS_PATH)
    args = parser.parse_args(argv)

    cells = load_scenario_cells(args.scenarios)
    prompts = load_scenarios(args.scenarios)

    print("=== cells (genus authority span) ===")
    for cell in cells:
        spread = cell.authority_spread_for_level("genus")
        block = cell.dispute_block_for_level("genus")
        print(
            f"{block or 'unknown':10} spread={spread or 0:3}  "
            f"{cell.genus:18} / {cell.family:14}  "
            f"ioc={cell.ioc_genus} [{cell.authority_genus_min}-{cell.authority_genus_max}]"
        )

    print("\n=== unique prompts by level ===")
    for level in ("genus", "family", "order"):
        sub = [p for p in prompts if p.taxonomic_level == level and p.dispute_block]
        counts = Counter(p.dispute_block for p in sub)
        print(f"{level}: {len(sub)} prompts, blocks {dict(counts)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
