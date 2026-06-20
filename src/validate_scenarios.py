"""Validate taxonomy scenario dataset structure."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from src.schema import SCENARIOS_PATH, Scenario, load_scenario_cells, load_scenarios

LEVELS = ["genus", "family", "order"]
FAMILIARITIES = {"well_known", "obscure"}
EXPECTED_CELLS = 24
EXPECTED_FAMILIES = 12
EXPECTED_SCENARIOS = EXPECTED_CELLS * len(LEVELS)


def validate_scenarios(scenarios: list[Scenario]) -> list[str]:
    errors: list[str] = []
    if len(scenarios) != EXPECTED_SCENARIOS:
        errors.append(f"scenarios: expected {EXPECTED_SCENARIOS} rows, got {len(scenarios)}")

    ids = [s.id for s in scenarios]
    if len(ids) != len(set(ids)):
        errors.append("scenarios: duplicate id values")

    cells = Counter(s.cell_id for s in scenarios)
    if len(cells) != EXPECTED_CELLS:
        errors.append(f"scenarios: expected {EXPECTED_CELLS} unique cells, got {len(cells)}")

    for cell_id, count in cells.items():
        if count != len(LEVELS):
            errors.append(f"scenarios: cell {cell_id} has {count} levels, expected {len(LEVELS)}")

    for cell_id in cells:
        sub = [s for s in scenarios if s.cell_id == cell_id]
        levels = {s.taxonomic_level for s in sub}
        if levels != set(LEVELS):
            errors.append(f"scenarios: cell {cell_id} missing levels {set(LEVELS) - levels}")

    for cell_id in cells:
        sub = [s for s in scenarios if s.cell_id == cell_id]
        ref = {(s.ioc_genus, s.ioc_family, s.ioc_order) for s in sub}
        if len(ref) > 1:
            errors.append(f"scenarios: cell {cell_id} has mismatched IOC reference counts")
        ioc_g, ioc_f, ioc_o = ref.pop()
        if not (ioc_g <= ioc_f <= ioc_o):
            errors.append(f"scenarios: cell {cell_id} IOC counts do not nest")

    pairs = Counter((s.genus, s.family) for s in scenarios)
    unique_pairs = set(pairs.keys())
    if len(unique_pairs) != EXPECTED_CELLS:
        errors.append(f"scenarios: expected {EXPECTED_CELLS} unique genus/family pairs")

    families = {s.family for s in scenarios}
    if len(families) != EXPECTED_FAMILIES:
        errors.append(f"scenarios: expected {EXPECTED_FAMILIES} families, got {len(families)}")

    fam_familiarity: dict[str, set[str]] = {}
    for s in scenarios:
        if s.taxonomic_level == "genus":
            fam_familiarity.setdefault(s.family, set()).add(s.familiarity)
    for family, fams in fam_familiarity.items():
        if fams != FAMILIARITIES:
            errors.append(
                f"scenarios: family {family} should have one well_known and one obscure genus "
                f"(got {fams})"
            )

    for s in scenarios:
        if s.familiarity not in FAMILIARITIES:
            errors.append(f"scenarios[{s.id}]: invalid familiarity")
        if s.ioc_count <= 0:
            errors.append(f"scenarios[{s.id}]: ioc_count must be positive")

    placeholder_notes = sum(1 for s in scenarios if "PLACEHOLDER" in s.notes)
    if placeholder_notes:
        errors.append(
            f"scenarios: {placeholder_notes} rows still have PLACEHOLDER IOC counts — "
            "run scripts/derive_ioc_counts.py after downloading IOC v15.2 xlsx"
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
    scenarios: list[Scenario] = []

    try:
        cells = load_scenario_cells(args.scenarios)
        scenarios = load_scenarios(args.scenarios)
        errors.extend(validate_scenarios(scenarios))
        if args.allow_placeholders:
            errors = [e for e in errors if "PLACEHOLDER" not in e]
    except Exception as exc:
        errors.append(f"scenarios: {exc}")

    if errors:
        print("Validation FAILED:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    levels = Counter(s.taxonomic_level for s in scenarios)
    familiarity = Counter(s.familiarity for s in scenarios if s.taxonomic_level == "genus")
    print(
        f"Validation OK: {len(cells)} cells -> {len(scenarios)} scenarios, "
        f"levels {dict(levels)}, genus familiarity {dict(familiarity)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
