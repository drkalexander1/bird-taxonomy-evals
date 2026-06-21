"""Derive IOC species counts and cross-authority spans from official spreadsheets.

Download IOC v15.2 files from https://www.worldbirdnames.org/ioc-lists/master-list-2/

  data/ioc_v15.2.xlsx              Life List+ or Master list (hierarchical)
  data/ioc_v15.2_comparison.xlsx   Comparison with other world lists

Then run:

  python scripts/derive_ioc_counts.py
  python scripts/derive_ioc_counts.py --update-scenarios
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DEFAULT_XLSX = DATA_DIR / "ioc_v15.2.xlsx"
DEFAULT_COMPARISON = DATA_DIR / "ioc_v15.2_comparison.xlsx"
REFERENCE_CSV = DATA_DIR / "taxonomy_reference.csv"
MANIFEST_PATH = DATA_DIR / "ioc_manifest.json"
SCENARIOS_PATH = DATA_DIR / "scenarios.yaml"

# Primary authorities used for min/max reference spans (p10/p90 calibration).
AUTHORITY_SPECS: tuple[tuple[str, str], ...] = (
    ("ioc", "Family IOC 15.2"),
    ("avilist", "AviList Core Team. 2025. AviList: The Global Avian Checklist, v2025. https://doi.org/10.2173/avilist.v2025"),
    (
        "clements",
        "Clements, J. F., P. C. Rasmussen, T. S. Schulenberg, M. J. Iliff, J. A. Gerbracht, D. Lepage, A. Spencer, S. M. Billerman, B. L. Sullivan, M. Smith, and C. L. Wood. 2025. The eBird/Clements checklist of Birds of the World: v2025. Downloaded from https://www.birds.cornell.edu/clementschecklist/download/",
    ),
    (
        "hbw_birdlife",
        "HBW and BirdLife International (2025). Handbook of the Birds of the World and BirdLife International digital checklist of the birds of the world. Version 10. Available at: https://datazone.birdlife.org/about-our-science/taxonomy#birdlife-s-taxonomic-checklist",
    ),
    (
        "howard_moore",
        "Christidis et al. 2014. The Howard and Moore Complete Checklist of the Birds of the World, version 4.1.",
    ),
)

GENUS_COLS = ("Genus", "genus")
FAMILY_COLS = ("Family", "family")
ORDER_COLS = ("Order", "order")
RANK_COL = "Rank"
IOC_FAMILY_COL = "Family IOC 15.2"


def _find_column(df: pd.DataFrame, candidates: tuple[str, ...]) -> str:
    lower = {c.lower(): c for c in df.columns}
    for name in candidates:
        if name in df.columns:
            return name
        if name.lower() in lower:
            return lower[name.lower()]
    raise KeyError(f"None of {candidates} found in columns: {list(df.columns)[:20]}...")


def _normalize_rank(value: object) -> str:
    return str(value).strip().lower()


def _clean_taxon_name(value: object) -> str:
    text = str(value).strip()
    text = re.sub(r"^(ORDER|Family|Genus)\s+", "", text, flags=re.IGNORECASE)
    return text.strip()


def _species_binomial(value: object) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none"}:
        return None
    parts = text.split()
    if len(parts) < 2:
        return None
    return f"{parts[0]} {parts[1]}"


def parse_hierarchical_ioc(path: Path) -> pd.DataFrame:
    """Parse hierarchical Life List+ / Master list into species rows."""
    df = pd.read_excel(path, sheet_name=0)
    if RANK_COL not in df.columns:
        raise ValueError(f"Expected hierarchical IOC sheet with a {RANK_COL!r} column")

    name_col = "Scientific Name" if "Scientific Name" in df.columns else "Scientific name"
    order = family = genus = None
    rows: list[dict[str, str]] = []

    for _, row in df.iterrows():
        rank = _normalize_rank(row[RANK_COL])
        sci = row.get(name_col)

        if rank == "order":
            order = _clean_taxon_name(sci)
            family = genus = None
        elif rank == "family":
            family = _clean_taxon_name(sci)
            genus = None
        elif rank == "genus":
            genus = _clean_taxon_name(sci)
        elif rank == "species":
            species = _species_binomial(sci)
            if species and genus and family and order:
                rows.append(
                    {
                        "species": species,
                        "genus": genus,
                        "family": family,
                        "order": order,
                    }
                )

    out = pd.DataFrame(rows)
    if out.empty:
        raise ValueError(f"No species rows parsed from {path}")
    return out.drop_duplicates(subset=["species"])


def parse_flat_ioc(path: Path) -> pd.DataFrame:
    """Parse flat IOC export with explicit genus/family/order columns."""
    df = pd.read_excel(path, sheet_name=0)
    genus_col = _find_column(df, GENUS_COLS)
    family_col = _find_column(df, FAMILY_COLS)
    order_col = _find_column(df, ORDER_COLS)
    name_col = None
    for candidate in ("Scientific Name", "Scientific name", "species", "Species"):
        if candidate in df.columns:
            name_col = candidate
            break
    if name_col is None:
        raise KeyError("Could not find species name column in flat IOC sheet")

    out = df[[name_col, genus_col, family_col, order_col]].copy()
    out.columns = ["species_raw", "genus", "family", "order"]
    out = out.dropna(how="any")
    for col in out.columns:
        out[col] = out[col].astype(str).str.strip()
    out["species"] = out["species_raw"].map(_species_binomial)
    out = out.dropna(subset=["species"]).drop(columns=["species_raw"])
    return out.drop_duplicates(subset=["species"])


def load_ioc_species(path: Path) -> pd.DataFrame:
    df_head = pd.read_excel(path, sheet_name=0, nrows=5)
    if RANK_COL in df_head.columns:
        return parse_hierarchical_ioc(path)
    return parse_flat_ioc(path)


def load_comparison_species(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=0)
    if RANK_COL not in df.columns:
        raise ValueError(f"Comparison sheet missing {RANK_COL!r} column")

    ioc_col = df.columns[1]
    species = df[df[RANK_COL].map(_normalize_rank) == "species"].copy()
    species["species"] = species[ioc_col].map(_species_binomial)
    species = species.dropna(subset=["species"])
    species["genus"] = species["species"].str.split().str[0]

    if IOC_FAMILY_COL not in species.columns:
        raise KeyError(f"Comparison sheet missing {IOC_FAMILY_COL!r}")

    species["family"] = species[IOC_FAMILY_COL].astype(str).str.strip()
    return species


def _taxon_key(value: str) -> str:
    return value.strip().lower()


def count_by_level(df: pd.DataFrame, level: str) -> dict[str, int]:
    return {_taxon_key(name): int(count) for name, count in df.groupby(level).size().items()}


def authority_recognized(series: pd.Series) -> pd.Series:
    return series.notna() & series.astype(str).str.strip().ne("") & series.astype(str).str.lower().ne("nan")


def compute_authority_counts(
    comparison: pd.DataFrame,
    taxonomy: pd.DataFrame,
) -> dict[str, dict[str, dict[str, int]]]:
    """Per-authority species counts at genus/family/order level."""
    family_order = {
        _taxon_key(family): order
        for family, order in taxonomy.groupby("family")["order"].agg(lambda s: s.mode().iloc[0]).items()
    }
    merged = comparison.merge(taxonomy[["species", "order"]], on="species", how="left")
    merged["order"] = merged["order"].fillna(merged["family"].astype(str).map(_taxon_key).map(family_order))

    results: dict[str, dict[str, dict[str, int]]] = {}
    for short_name, col in AUTHORITY_SPECS:
        if short_name == "ioc":
            subset = merged
        else:
            if col not in merged.columns:
                continue
            subset = merged[authority_recognized(merged[col])]

        results[short_name] = {
            "genus": count_by_level(subset, "genus"),
            "family": count_by_level(subset, "family"),
            "order": count_by_level(subset.dropna(subset=["order"]), "order"),
        }
    return results


def merge_authority_spans(
    authority_counts: dict[str, dict[str, dict[str, int]]],
) -> dict[str, dict[str, dict[str, int | None]]]:
    """Min/max/spread across authorities for each taxonomic name."""
    spans: dict[str, dict[str, dict[str, int | None]]] = {
        level: {} for level in ("genus", "family", "order")
    }
    names_by_level: dict[str, set[str]] = {level: set() for level in spans}
    for auth_data in authority_counts.values():
        for level, mapping in auth_data.items():
            names_by_level[level].update(mapping.keys())

    for level, names in names_by_level.items():
        for name in names:
            values = [
                auth_data[level][name]
                for auth_data in authority_counts.values()
                if name in auth_data.get(level, {})
            ]
            if not values:
                continue
            min_v, max_v = min(values), max(values)
            spans[level][name] = {
                "authority_min": min_v,
                "authority_max": max_v,
                "authority_spread": max_v - min_v,
            }
    return spans


def display_name_for_key(species: pd.DataFrame, level: str, key: str) -> str:
    col = species[level].astype(str).map(_taxon_key)
    match = species[col == key]
    if match.empty:
        return key
    return str(match.iloc[0][level])


def ioc_counts_from_species(species: pd.DataFrame) -> dict[str, dict[str, int]]:
    return {
        "genus": count_by_level(species, "genus"),
        "family": count_by_level(species, "family"),
        "order": count_by_level(species, "order"),
    }


def build_reference_table(
    ioc_counts: dict[str, dict[str, int]],
    spans: dict[str, dict[str, dict[str, int | None]]],
    species: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for level, mapping in ioc_counts.items():
        for key, ioc_n in sorted(mapping.items()):
            span = spans[level].get(key, {})
            rows.append(
                {
                    "taxonomic_level": level,
                    "name": display_name_for_key(species, level, key),
                    "ioc_species_count": int(ioc_n),
                    "authority_min": span.get("authority_min"),
                    "authority_max": span.get("authority_max"),
                    "authority_spread": span.get("authority_spread", 0),
                }
            )
    return pd.DataFrame(rows)


def lookup_count(counts: dict[str, dict[str, int]], level: str, name: str) -> int | None:
    return counts.get(level, {}).get(_taxon_key(name))


def lookup_span(spans: dict[str, dict[str, dict[str, int | None]]], level: str, name: str) -> dict[str, int | None]:
    return spans[level].get(_taxon_key(name), {})


def update_scenarios_yaml(
    ioc_counts: dict[str, dict[str, int]],
    spans: dict[str, dict[str, dict[str, int | None]]],
    path: Path,
) -> int:
    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    updated = 0
    for cell in raw.get("cells", []):
        genus = cell["genus"]
        family = cell["family"]
        order = cell["order"]

        g = lookup_count(ioc_counts, "genus", genus)
        f = lookup_count(ioc_counts, "family", family)
        o = lookup_count(ioc_counts, "order", order)
        if g is None or f is None or o is None:
            missing = [
                label
                for label, val in (("genus", g), ("family", f), ("order", o))
                if val is None
            ]
            print(f"Warning: missing IOC counts for {genus}/{family}/{order}: {missing}")
            continue

        g_span = lookup_span(spans, "genus", genus)
        f_span = lookup_span(spans, "family", family)
        o_span = lookup_span(spans, "order", order)

        cell["ioc_genus"] = int(g)
        cell["ioc_family"] = int(f)
        cell["ioc_order"] = int(o)
        cell["authority_genus_min"] = int(g_span.get("authority_min", g))
        cell["authority_genus_max"] = int(g_span.get("authority_max", g))
        cell["authority_family_min"] = int(f_span.get("authority_min", f))
        cell["authority_family_max"] = int(f_span.get("authority_max", f))
        cell["authority_order_min"] = int(o_span.get("authority_min", o))
        cell["authority_order_max"] = int(o_span.get("authority_max", o))
        cell.pop("authority_spread", None)
        cell.pop("dispute_block", None)
        cell["notes"] = (
            "IOC v15.2 counts with cross-authority min/max from comparison spreadsheet"
        )
        updated += 1

    raw["ioc_version_note"] = (
        "Counts derived from IOC Life List+ / Master list and cross-authority spans "
        "from IOC v15.2 comparison spreadsheet."
    )

    with path.open("w", encoding="utf-8") as f:
        yaml.dump(raw, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    return updated


def summarize_dispute_blocks(path: Path) -> dict[str, dict[str, int]]:
    from src.schema import load_scenarios

    scenarios = load_scenarios(path)
    summary: dict[str, dict[str, int]] = {}
    for level in ("genus", "family", "order"):
        sub = [s for s in scenarios if s.taxonomic_level == level and s.dispute_block]
        summary[level] = dict(Counter(s.dispute_block for s in sub))
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Derive IOC taxonomy reference counts")
    parser.add_argument("--xlsx", type=Path, default=DEFAULT_XLSX, help="IOC Life List+ / Master list")
    parser.add_argument(
        "--comparison-xlsx",
        type=Path,
        default=DEFAULT_COMPARISON,
        help="IOC comparison with other world lists",
    )
    parser.add_argument("--output-csv", type=Path, default=REFERENCE_CSV)
    parser.add_argument(
        "--update-scenarios",
        action="store_true",
        help="Rewrite ioc_* and authority_* fields in data/scenarios.yaml",
    )
    args = parser.parse_args(argv)

    if not args.xlsx.exists():
        print(
            f"IOC spreadsheet not found at {args.xlsx}\n"
            "Download IOC v15.2 Life List+ or Master list from worldbirdnames.org."
        )
        return 1

    species = load_ioc_species(args.xlsx)
    ioc_counts = ioc_counts_from_species(species)

    spans: dict[str, dict[str, dict[str, int | None]]] = {
        level: {} for level in ("genus", "family", "order")
    }
    authority_counts: dict[str, dict[str, dict[str, int]]] = {}

    if args.comparison_xlsx.exists():
        comparison = load_comparison_species(args.comparison_xlsx)
        authority_counts = compute_authority_counts(comparison, species)
        spans = merge_authority_spans(authority_counts)
        print(f"Loaded comparison species rows: {len(comparison)}")
    else:
        print(
            f"Comparison spreadsheet not found at {args.comparison_xlsx} — "
            "IOC counts only; authority min/max will equal IOC."
        )
        for level, mapping in ioc_counts.items():
            for name, count in mapping.items():
                spans[level][name] = {
                    "authority_min": count,
                    "authority_max": count,
                    "authority_spread": 0,
                }

    ref = build_reference_table(ioc_counts, spans, species)
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    ref.to_csv(args.output_csv, index=False)

    manifest = {
        "ioc_version": "15.2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_file": str(args.xlsx.name),
        "comparison_file": str(args.comparison_xlsx.name) if args.comparison_xlsx.exists() else None,
        "authorities": [name for name, _ in AUTHORITY_SPECS],
        "species_rows": len(species),
        "genera": len(ioc_counts["genus"]),
        "families": len(ioc_counts["family"]),
        "orders": len(ioc_counts["order"]),
    }
    if authority_counts:
        manifest["authority_totals"] = {
            auth: {level: len(counts) for level, counts in data.items()}
            for auth, data in authority_counts.items()
        }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"Wrote {len(ref)} reference rows to {args.output_csv}")
    print(f"Wrote manifest to {MANIFEST_PATH}")

    if args.update_scenarios:
        n = update_scenarios_yaml(ioc_counts, spans, SCENARIOS_PATH)
        print(f"Updated {n} cells in {SCENARIOS_PATH}")
        blocks = summarize_dispute_blocks(SCENARIOS_PATH)
        print(f"Dispute blocks by level: {blocks}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
