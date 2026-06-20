"""Derive IOC species counts from the Master List spreadsheet.

Download IOC v15.2 Master list (XLSX) from:
  https://www.worldbirdnames.org/ioc-lists/master-list-2/

Save as data/ioc_v15.2.xlsx (gitignored), then run:

  python scripts/derive_ioc_counts.py
  python scripts/derive_ioc_counts.py --update-scenarios
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DEFAULT_XLSX = DATA_DIR / "ioc_v15.2.xlsx"
REFERENCE_CSV = DATA_DIR / "taxonomy_reference.csv"
MANIFEST_PATH = DATA_DIR / "ioc_manifest.json"
SCENARIOS_PATH = DATA_DIR / "scenarios.yaml"

# Column names vary slightly across IOC releases; try these in order.
GENUS_COLS = ("Genus", "genus")
FAMILY_COLS = ("Family", "family")
ORDER_COLS = ("Order", "order")


def _find_column(df: pd.DataFrame, candidates: tuple[str, ...]) -> str:
    lower = {c.lower(): c for c in df.columns}
    for name in candidates:
        if name in df.columns:
            return name
        if name.lower() in lower:
            return lower[name.lower()]
    raise KeyError(f"None of {candidates} found in columns: {list(df.columns)[:20]}...")


def load_ioc_table(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=0)
    genus_col = _find_column(df, GENUS_COLS)
    family_col = _find_column(df, FAMILY_COLS)
    order_col = _find_column(df, ORDER_COLS)
    out = df[[genus_col, family_col, order_col]].copy()
    out.columns = ["genus", "family", "order"]
    out = out.dropna(how="any")
    for col in out.columns:
        out[col] = out[col].astype(str).str.strip()
    return out


def count_species(df: pd.DataFrame) -> dict[str, dict[str, int]]:
    """Count unique species rows per genus, family, and order."""
    # Each row is one species (subspecies rows may exist in some sheets; dedupe by genus+family+order+species if needed)
    genus_counts = df.groupby("genus").size().to_dict()
    family_counts = df.groupby("family").size().to_dict()
    order_counts = df.groupby("order").size().to_dict()
    return {"genus": genus_counts, "family": family_counts, "order": order_counts}


def build_reference_table(counts: dict[str, dict[str, int]]) -> pd.DataFrame:
    rows = []
    for level, mapping in counts.items():
        for name, n in sorted(mapping.items()):
            rows.append({"taxonomic_level": level, "name": name, "ioc_species_count": int(n)})
    return pd.DataFrame(rows)


def lookup_count(counts: dict[str, dict[str, int]], level: str, name: str) -> int | None:
    return counts.get(level, {}).get(name)


def update_scenarios_yaml(counts: dict[str, dict[str, int]], path: Path) -> int:
    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    updated = 0
    for cell in raw.get("cells", []):
        genus = cell["genus"]
        family = cell["family"]
        order = cell["order"]
        g = lookup_count(counts, "genus", genus)
        f = lookup_count(counts, "family", family)
        o = lookup_count(counts, "order", order)
        if g is None or f is None or o is None:
            missing = [
                label
                for label, val in (("genus", g), ("family", f), ("order", o))
                if val is None
            ]
            print(f"Warning: missing IOC counts for {genus}/{family}/{order}: {missing}")
            continue
        cell["ioc_genus"] = int(g)
        cell["ioc_family"] = int(f)
        cell["ioc_order"] = int(o)
        cell["notes"] = "Counts derived from IOC Master List via derive_ioc_counts.py"
        updated += 1
    with path.open("w", encoding="utf-8") as f:
        yaml.dump(raw, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    return updated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Derive IOC taxonomy reference counts")
    parser.add_argument("--xlsx", type=Path, default=DEFAULT_XLSX)
    parser.add_argument("--output-csv", type=Path, default=REFERENCE_CSV)
    parser.add_argument(
        "--update-scenarios",
        action="store_true",
        help="Rewrite ioc_* fields in data/scenarios.yaml",
    )
    args = parser.parse_args(argv)

    if not args.xlsx.exists():
        print(
            f"IOC spreadsheet not found at {args.xlsx}\n"
            "Download IOC v15.2 Master list from worldbirdnames.org and save there."
        )
        return 1

    df = load_ioc_table(args.xlsx)
    counts = count_species(df)
    ref = build_reference_table(counts)
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    ref.to_csv(args.output_csv, index=False)

    manifest = {
        "ioc_version": "15.2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_file": str(args.xlsx.name),
        "species_rows": len(df),
        "genera": len(counts["genus"]),
        "families": len(counts["family"]),
        "orders": len(counts["order"]),
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"Wrote {len(ref)} reference rows to {args.output_csv}")
    print(f"Wrote manifest to {MANIFEST_PATH}")

    if args.update_scenarios:
        n = update_scenarios_yaml(counts, SCENARIOS_PATH)
        print(f"Updated {n} cells in {SCENARIOS_PATH}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
