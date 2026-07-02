"""Validate taxonomy scenario dataset structure."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from src.schema import (
    EXPECTED_CELLS,
    EXPECTED_FAMILY_PROMPTS,
    EXPECTED_GENUS_PROMPTS,
    EXPECTED_ORDER_PROMPTS,
    EXPECTED_UNIQUE_PROMPTS,
    SCENARIOS_PATH,
    Scenario,
    load_scenario_cells,
    load_scenarios,
)

FAMILIARITIES = {"well_known", "obscure"}
EXPECTED_FAMILIES = 14


def validate_cells(cells) -> list[str]:
    errors: list[str] = []
    if len(cells) != EXPECTED_CELLS:
        errors.append(f"cells: expected {EXPECTED_CELLS}, got {len(cells)}")

    pairs = Counter((c.genus, c.family) for c in cells)
    if len(pairs) != EXPECTED_CELLS:
        errors.append(f"cells: expected {EXPECTED_CELLS} unique genus/family pairs")

    families = {c.family for c in cells}
    if len(families) != EXPECTED_FAMILIES:
        errors.append(f"cells: expected {EXPECTED_FAMILIES} families, got {len(families)}")

    fam_familiarity: dict[str, set[str]] = {}
    for cell in cells:
        fam_familiarity.setdefault(cell.family, set()).add(cell.familiarity)
    for family, fams in fam_familiarity.items():
        if fams != FAMILIARITIES:
            errors.append(
                f"cells: family {family} should have one well_known and one obscure genus "
                f"(got {fams})"
            )

    for cell in cells:
        if cell.familiarity not in FAMILIARITIES:
            errors.append(f"cells[{cell.cell_id}]: invalid familiarity")
        if not (cell.ioc_genus <= cell.ioc_family <= cell.ioc_order):
            errors.append(f"cells[{cell.cell_id}]: IOC counts do not nest")
        if "PLACEHOLDER" in cell.notes:
            errors.append(
                f"cells[{cell.cell_id}]: PLACEHOLDER IOC counts — "
                "run scripts/derive_ioc_counts.py"
            )

    return errors


def validate_prompts(prompts: list[Scenario]) -> list[str]:
    errors: list[str] = []
    if len(prompts) != EXPECTED_UNIQUE_PROMPTS:
        errors.append(f"prompts: expected {EXPECTED_UNIQUE_PROMPTS}, got {len(prompts)}")

    ids = [p.id for p in prompts]
    if len(ids) != len(set(ids)):
        errors.append("prompts: duplicate id values")

    levels = Counter(p.taxonomic_level for p in prompts)
    expected_levels = {
        "genus": EXPECTED_GENUS_PROMPTS,
        "family": EXPECTED_FAMILY_PROMPTS,
        "order": EXPECTED_ORDER_PROMPTS,
    }
    for level, count in expected_levels.items():
        if levels.get(level, 0) != count:
            errors.append(f"prompts: expected {count} {level}, got {levels.get(level, 0)}")

    for prompt in prompts:
        if prompt.ioc_count <= 0:
            errors.append(f"prompts[{prompt.id}]: ioc_count must be positive")

    genus_blocks = Counter(p.dispute_block for p in prompts if p.taxonomic_level == "genus")
    if genus_blocks and (
        genus_blocks.get("undisputed", 0) == 0 or genus_blocks.get("disputed", 0) == 0
    ):
        errors.append(
            f"prompts: genus dispute blocks are one-sided {dict(genus_blocks)} — "
            "swap genera to include both undisputed and disputed blocks"
        )

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate bird taxonomy eval dataset")
    parser.add_argument("--scenarios", type=Path, default=SCENARIOS_PATH)
    parser.add_argument(
        "--allow-placeholders",
        action="store_true",
        help="Do not fail on PLACEHOLDER IOC counts (for early scaffolding)",
    )
    args = parser.parse_args(argv)

    errors: list[str] = []
    try:
        cells = load_scenario_cells(args.scenarios)
        prompts = load_scenarios(args.scenarios)
        errors.extend(validate_cells(cells))
        errors.extend(validate_prompts(prompts))
        if args.allow_placeholders:
            errors = [
                e
                for e in errors
                if "PLACEHOLDER" not in e and "dispute blocks are one-sided" not in e
            ]
    except Exception as exc:
        errors.append(f"dataset: {exc}")

    if errors:
        print("Validation FAILED:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    levels = Counter(p.taxonomic_level for p in prompts)
    familiarity = Counter(p.familiarity for p in prompts if p.taxonomic_level == "genus")
    by_level = Counter((p.taxonomic_level, p.dispute_block) for p in prompts if p.dispute_block)
    block_msg = f", dispute blocks {dict(by_level)}" if by_level else ""
    print(
        f"Validation OK: {len(cells)} cells -> {len(prompts)} unique prompts, "
        f"levels {dict(levels)}, genus familiarity {dict(familiarity)}{block_msg}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
