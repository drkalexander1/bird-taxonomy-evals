# bird-taxonomy-evals

LLM calibration benchmark: do models hold coherent beliefs about taxonomic hierarchies?

Round 3 of an independent calibration benchmark program asking whether LLMs can represent their own uncertainty. Round 1 ([michigan-bird-evals](https://github.com/drkalexander1/michigan-bird-evals)) and Round 2 ([florida-weather-evals](https://github.com/drkalexander1/florida-weather-evals)) tested calibration of probabilistic forecasts against ground truth. This round tests **internal consistency across hierarchical levels** — whether a model's independent beliefs about genus, family, and order species counts are mutually coherent.

## The question

A calibrated model should assign species counts that nest correctly: genus ≤ family ≤ order, and the ratios should be plausible. These answers are elicited in **separate prompts** — the model doesn't know it's being consistency-checked. Incoherence here isn't a reasoning failure under pressure; it's evidence that the model's independent beliefs about different levels of the same hierarchy don't cohere.

## Design

- **Taxonomy:** Birds (Aves), ground truth from [IOC World Bird List](https://www.worldbirdnames.org/)
- **Scenarios:** 12 bird families × 2 genera each (1 well-known + 1 obscure) = 24 cells
- **Levels per cell:** 3 separate prompts — genus, containing family, containing order (72 prompts total)
- **Prompts:** Single template in `prompts/taxonomy.txt` with `{taxonomic_unit}` filled per level (e.g. `the genus Corvus`)
- **Elicitation:** (p10, p50, p90) quantile intervals + confidence, structured JSON output
- **Models:** claude-haiku-4-5, claude-sonnet-4-6, claude-opus-4-8, gpt-4o-mini, gpt-4o (5 models; fable-5 unavailable)
- **n:** 72 prompts × 5 models = 360 individual forecasts

## Scoring

- **Primary metric:** `crps_relative = CRPS / target_median` (scale-normalized quantile score against IOC point target)
- **Consistency check:** `gap_ratio = (family_p50 - genus_p50) / family_p50` per scenario; reference from IOC actuals
- **Strict violations:** genus_p50 > family_p50, or family_p50 > order_p50 — physically impossible, no ground truth needed
- **Compression ratio:** genus_p50 / family_p50 — flags hierarchy collapse (model treats all levels as interchangeable)

## What to look for

Three-way split (porting directly from florida-weather-evals):
1. **Coherent and right** — answers nest correctly and track IOC counts
2. **Coherent but wrong** — answers nest correctly but are systematically biased (e.g., model uses the same prior for all levels)
3. **Incoherent** — strict violations or implausible compression

The headline is around violations and magnitude structure, not the pass rate. Nesting is a low bar — the interesting signal is in the gaps.

## Power analysis

| Comparison | Effect size | Required n | Status at n=24 |
|---|---|---|---|
| Level difficulty gradient (genus vs. order) | d=0.5 (assumed) | ~25 scenarios | Adequately powered |
| Haiku vs. top tier | d~0.4 (from florida) | ~52 scenarios | Underpowered — directional only |
| Adjacent tiers (sonnet vs. opus) | d~0.1 | ~1000 scenarios | Do not claim |
| Strict violations | — | qualitative | Report with Clopper-Pearson CI |

n=24 is sufficient for structural/hierarchy findings. Model-ranking claims are limited to tier-level differences (haiku vs. rest), same caveat as florida-weather-evals.

## Limitations

- Ground truth is IOC World Bird List (single authority); counts differ across taxonomic frameworks
- n=24 supports level-difficulty and structural claims only; adjacent model tiers are not resolvable
- Separate-prompt design measures coherence of independent beliefs, not reasoning under explicit hierarchical constraint
- Point target (single IOC count) rather than empirical distribution — CRPS reduces to quantile pinball loss

## Repo structure

```
prompts/taxonomy.txt   prompt template
data/scenarios.yaml    24 taxonomy cells
scripts/               IOC derivation, demo predictions
src/                   schema, run_eval, score, validate
data/                  IOC reference (ioc_*.xlsx gitignored)
results/               scored output by model
```
