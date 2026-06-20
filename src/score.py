"""Score predictions: CRPS against IOC point targets and hierarchy consistency."""

from __future__ import annotations

import argparse
import json
import math
from itertools import combinations
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.schema import (
    QUANTILE_LEVELS,
    ROOT,
    PredictionRecord,
    Scenario,
    load_scenarios,
)

RESULTS_DIR = ROOT / "results" / "latest"

# Flag compression when model genus/family ratio exceeds IOC ratio by this factor.
COMPRESSION_THRESHOLD_FACTOR = 3.0


def pinball_loss(y: float, q: float, tau: float) -> float:
    err = y - q
    return float(tau * err if err >= 0 else (tau - 1) * err)


def crps_point_target(q10: float, q50: float, q90: float, target: float) -> float:
    """CRPS against a point target equals mean pinball loss at elicited quantiles."""
    return float(
        np.mean(
            [
                pinball_loss(target, q10, 0.1),
                pinball_loss(target, q50, 0.5),
                pinball_loss(target, q90, 0.9),
            ]
        )
    )


def mean_pinball(y: float, q10: float, q50: float, q90: float) -> float:
    return float(
        np.mean(
            [
                pinball_loss(y, q10, 0.1),
                pinball_loss(y, q50, 0.5),
                pinball_loss(y, q90, 0.9),
            ]
        )
    )


def wilson_ci(successes: int, n: int, *, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion."""
    if n == 0:
        return float("nan"), float("nan")
    p_hat = successes / n
    denom = 1 + z**2 / n
    centre = p_hat + z**2 / (2 * n)
    margin = z * math.sqrt(p_hat * (1 - p_hat) / n + z**2 / (4 * n**2))
    return float((centre - margin) / denom), float((centre + margin) / denom)


def expected_calibration_error(y_true: np.ndarray, y_score: np.ndarray, n_bins: int = 10) -> float:
    bins = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    n = len(y_true)
    for i in range(n_bins):
        mask = (y_score >= bins[i]) & (
            y_score < bins[i + 1] if i < n_bins - 1 else y_score <= bins[i + 1]
        )
        if not mask.any():
            continue
        acc = y_true[mask].mean()
        conf = y_score[mask].mean()
        ece += mask.sum() / n * abs(acc - conf)
    return float(ece)


def load_predictions(path: Path) -> list[PredictionRecord]:
    records: list[PredictionRecord] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(PredictionRecord.model_validate_json(line))
    return records


def build_frame(
    scenarios: list[Scenario],
    predictions: list[PredictionRecord],
) -> pd.DataFrame:
    scenario_map = {s.id: s for s in scenarios}
    rows = []
    for rec in predictions:
        sc = scenario_map.get(rec.scenario_id)
        if not sc:
            continue
        pred = rec.prediction
        target = float(sc.ioc_count)
        p10, p50, p90 = float(pred.p10), float(pred.p50), float(pred.p90)
        scale = max(target, 1.0)
        crps = crps_point_target(p10, p50, p90, target)
        rows.append(
            {
                "scenario_id": rec.scenario_id,
                "cell_id": sc.cell_id,
                "model": rec.model,
                "taxonomic_level": sc.taxonomic_level,
                "familiarity": sc.familiarity,
                "genus": sc.genus,
                "family": sc.family,
                "order": sc.order,
                "ioc_count": target,
                "ioc_genus": sc.ioc_genus,
                "ioc_family": sc.ioc_family,
                "ioc_order": sc.ioc_order,
                "p10": p10,
                "p50": p50,
                "p90": p90,
                "interval_width": p90 - p10,
                "relative_interval_width": (p90 - p10) / scale,
                "confidence": float(pred.confidence),
                "crps": crps,
                "crps_relative": crps / scale,
                "mean_pinball_loss": mean_pinball(target, p10, p50, p90),
                "median_abs_error": abs(p50 - target),
                "median_abs_error_relative": abs(p50 - target) / scale,
                "signed_error_relative": (p50 - target) / scale,
                "latency_ms": rec.latency_ms,
            }
        )
    return pd.DataFrame(rows)


def compute_metrics(df: pd.DataFrame) -> dict:
    conf = df["confidence"].to_numpy(dtype=float)
    well_calibrated = (df["median_abs_error_relative"] < 0.15).astype(float).to_numpy()
    return {
        "n": int(len(df)),
        "crps": float(df["crps"].mean()),
        "crps_relative": float(df["crps_relative"].mean()),
        "mean_pinball_loss": float(df["mean_pinball_loss"].mean()),
        "mean_interval_width": float(df["interval_width"].mean()),
        "mean_relative_interval_width": float(df["relative_interval_width"].mean()),
        "mean_median_abs_error": float(df["median_abs_error"].mean()),
        "ece_confidence": expected_calibration_error(well_calibrated, conf),
    }


_Z_ALPHA = 1.96
_Z_BETA = 0.84


def pairwise_power_analysis(df: pd.DataFrame) -> dict:
    pairs = []
    for a, b in combinations(sorted(df["model"].unique()), 2):
        da = df[df["model"] == a].set_index("scenario_id")["crps_relative"]
        db = df[df["model"] == b].set_index("scenario_id")["crps_relative"]
        diffs = (da - db).dropna()
        n = len(diffs)
        if n < 2:
            continue
        delta = float(diffs.mean())
        sd = float(diffs.std(ddof=1))
        se = sd / math.sqrt(n)
        pairs.append(
            {
                "model_a": a,
                "model_b": b,
                "n_scenarios": n,
                "delta_crps_relative": delta,
                "sd_of_paired_diffs": sd,
                "t_paired": delta / se if se > 0 else float("inf"),
                "scenarios_needed_80pct_power": (
                    float((_Z_ALPHA + _Z_BETA) ** 2 * (sd / delta) ** 2) if delta != 0 else None
                ),
                "min_detectable_delta_at_n": float((_Z_ALPHA + _Z_BETA) * se),
            }
        )
    return {
        "method": (
            "Paired t on per-scenario crps_relative differences; "
            "alpha=0.05 two-sided, power=0.80."
        ),
        "pairs": pairs,
    }


def hierarchy_consistency(df: pd.DataFrame) -> pd.DataFrame:
    """Join genus/family/order p50s per cell × model; compute consistency metrics."""
    pivot = df.pivot_table(
        index=["cell_id", "model", "familiarity", "genus", "family"],
        columns="taxonomic_level",
        values="p50",
        aggfunc="first",
    )
    ref = df.drop_duplicates("cell_id").set_index("cell_id")[
        ["ioc_genus", "ioc_family", "ioc_order"]
    ]

    rows = []
    for (cell_id, model, familiarity, genus, family), row in pivot.iterrows():
        if not {"genus", "family", "order"} <= set(row.index):
            continue
        g_p50, f_p50, o_p50 = float(row["genus"]), float(row["family"]), float(row["order"])
        ioc = ref.loc[cell_id]
        ioc_g, ioc_f, ioc_o = int(ioc["ioc_genus"]), int(ioc["ioc_family"]), int(ioc["ioc_order"])

        strict_violation = g_p50 > f_p50 or f_p50 > o_p50
        compression_ratio = g_p50 / f_p50 if f_p50 > 0 else float("inf")
        ioc_compression = ioc_g / ioc_f if ioc_f > 0 else 0.0
        gap_ratio = (f_p50 - g_p50) / f_p50 if f_p50 > 0 else float("nan")
        ioc_gap_ratio = (ioc_f - ioc_g) / ioc_f if ioc_f > 0 else float("nan")
        hierarchy_collapse = compression_ratio > 0.9

        rows.append(
            {
                "cell_id": cell_id,
                "model": model,
                "familiarity": familiarity,
                "genus": genus,
                "family": family,
                "genus_p50": g_p50,
                "family_p50": f_p50,
                "order_p50": o_p50,
                "strict_violation": strict_violation,
                "compression_ratio": compression_ratio,
                "ioc_compression_ratio": ioc_compression,
                "compression_exceeds_ioc": compression_ratio
                > max(ioc_compression * COMPRESSION_THRESHOLD_FACTOR, 0.5),
                "gap_ratio": gap_ratio,
                "ioc_gap_ratio": ioc_gap_ratio,
                "hierarchy_collapse": hierarchy_collapse,
            }
        )
    return pd.DataFrame(rows)


def classify_cells(per_level: pd.DataFrame, consistency: pd.DataFrame) -> pd.DataFrame:
    """Three-way split: coherent-and-right / coherent-but-wrong / incoherent."""
    level_crps = per_level.groupby(["cell_id", "model"])["crps_relative"].mean().reset_index()
    best_by_cell = level_crps.groupby("cell_id")["crps_relative"].min().rename("best_crps")
    level_crps = level_crps.merge(best_by_cell, on="cell_id")
    level_crps["within_1sd"] = level_crps["crps_relative"] <= level_crps["best_crps"] * 1.5

    merged = consistency.merge(
        level_crps.groupby(["cell_id", "model"]).agg(
            mean_crps_relative=("crps_relative", "mean"),
            within_1sd=("within_1sd", "all"),
        ),
        on=["cell_id", "model"],
        how="left",
    )
    bias = per_level.groupby(["cell_id", "model"])["signed_error_relative"].mean().reset_index()
    merged = merged.merge(bias, on=["cell_id", "model"], how="left")

    def _classify(row: pd.Series) -> str:
        if row["strict_violation"] or row["compression_exceeds_ioc"] or row["hierarchy_collapse"]:
            return "incoherent"
        if row["within_1sd"] and abs(row["signed_error_relative"]) < 0.25:
            return "coherent_and_right"
        return "coherent_but_wrong"

    merged["classification"] = merged.apply(_classify, axis=1)
    return merged


def summarize_violations(consistency: pd.DataFrame) -> dict:
    per_model: dict = {}
    for model, sub in consistency.groupby("model"):
        n = len(sub)
        violations = int(sub["strict_violation"].sum())
        lo, hi = wilson_ci(violations, n)
        per_model[model] = {
            "n_cells": n,
            "strict_violations": violations,
            "strict_violation_rate": violations / n if n else float("nan"),
            "strict_violation_ci_95": [lo, hi],
            "mean_compression_ratio": float(sub["compression_ratio"].mean()),
            "mean_gap_ratio": float(sub["gap_ratio"].mean()),
            "hierarchy_collapse_rate": float(sub["hierarchy_collapse"].mean()),
        }
    return {
        "method": (
            "strict_violation = genus_p50 > family_p50 OR family_p50 > order_p50; "
            "compression_exceeds_ioc when genus_p50/family_p50 >> IOC genus/family ratio; "
            "hierarchy_collapse when compression_ratio > 0.9."
        ),
        "per_model": per_model,
        "ioc_reference": {
            "mean_compression_ratio": float(consistency["ioc_compression_ratio"].mean()),
            "mean_gap_ratio": float(consistency["ioc_gap_ratio"].mean()),
        },
    }


def plot_interval_width_by_level(df: pd.DataFrame, out_dir: Path) -> None:
    if df.empty:
        return
    levels = ["genus", "family", "order"]
    models = sorted(df["model"].unique())
    bar_w = 0.8 / max(len(models), 1)
    x = np.arange(len(levels))

    fig, ax = plt.subplots(figsize=(8, 4))
    grouped = df.groupby(["model", "taxonomic_level"], as_index=False)["relative_interval_width"].mean()
    for i, model in enumerate(models):
        sub = grouped[grouped["model"] == model].set_index("taxonomic_level")
        ys = [sub.loc[level, "relative_interval_width"] if level in sub.index else np.nan for level in levels]
        ax.bar(x + i * bar_w, ys, width=bar_w, label=model)
    ax.set_xticks(x + bar_w * (len(models) - 1) / 2)
    ax.set_xticklabels(levels)
    ax.set_ylabel("Mean relative interval width")
    ax.set_title("Interval width by taxonomic level")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out_dir / "interval_width_by_level.png", dpi=120)
    plt.close(fig)


def score_run(
    run_dir: Path,
    scenarios_path: Path | None = None,
) -> dict:
    scenarios = load_scenarios(scenarios_path)
    predictions_path = run_dir / "predictions.jsonl"
    if not predictions_path.exists():
        raise FileNotFoundError(f"No predictions at {predictions_path}")

    predictions = load_predictions(predictions_path)
    df = build_frame(scenarios, predictions)
    if df.empty:
        raise ValueError("No matching scenarios for predictions")

    consistency = hierarchy_consistency(df)
    classified = classify_cells(df, consistency)

    summary: dict = {
        "target_source": "ioc_point_count",
        "overall": compute_metrics(df),
        "by_model": {},
        "by_level": {},
        "by_familiarity": {},
    }

    for model, sub in df.groupby("model"):
        summary["by_model"][model] = compute_metrics(sub)
    for level, sub in df.groupby("taxonomic_level"):
        summary["by_level"][level] = compute_metrics(sub)
    for fam, sub in df.groupby("familiarity"):
        summary["by_familiarity"][fam] = compute_metrics(sub)

    if df["model"].nunique() >= 2:
        summary["power_analysis"] = pairwise_power_analysis(df)
    if not consistency.empty:
        summary["hierarchy_consistency"] = summarize_violations(consistency)
        summary["classification_counts"] = (
            classified.groupby(["model", "classification"]).size().unstack(fill_value=0).to_dict()
        )

    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    df.to_csv(run_dir / "by_scenario.csv", index=False)
    consistency.to_csv(run_dir / "consistency.csv", index=False)
    classified.to_csv(run_dir / "classification.csv", index=False)

    agg_spec = dict(
        crps=("crps", "mean"),
        crps_relative=("crps_relative", "mean"),
        mean_pinball_loss=("mean_pinball_loss", "mean"),
        interval_width=("interval_width", "mean"),
        relative_interval_width=("relative_interval_width", "mean"),
        n=("scenario_id", "count"),
    )
    df.groupby(["model", "taxonomic_level", "familiarity"], as_index=False).agg(**agg_spec).to_csv(
        run_dir / "by_level.csv", index=False
    )

    plot_interval_width_by_level(df, run_dir)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score bird taxonomy eval predictions")
    parser.add_argument("--run", type=Path, default=RESULTS_DIR)
    parser.add_argument("--scenarios", type=Path, default=ROOT / "data" / "scenarios.yaml")
    args = parser.parse_args(argv)

    summary = score_run(args.run, scenarios_path=args.scenarios)
    print(json.dumps(summary["overall"], indent=2))
    print(f"Wrote summary to {args.run / 'summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
