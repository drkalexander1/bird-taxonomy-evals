# bird-taxonomy-evals

LLM calibration benchmark: do models hold coherent beliefs about taxonomic hierarchies?

Round 3 of an independent calibration benchmark program asking whether LLMs can represent their own uncertainty. Round 1 ([michigan-bird-evals](https://github.com/drkalexander1/michigan-bird-evals)) and Round 2 ([florida-weather-evals](https://github.com/drkalexander1/florida-weather-evals)) tested calibration of probabilistic forecasts against ground truth. This round tests **internal consistency across hierarchical levels** — whether a model's independent beliefs about genus, family, and order species counts are mutually coherent.

## The question

A calibrated model should assign species counts that nest correctly: genus ≤ family ≤ order, and the ratios should be plausible. These answers are elicited in **separate prompts** — the model doesn't know it's being consistency-checked. Incoherence here isn't a reasoning failure under pressure; it's evidence that the model's independent beliefs about different levels of the same hierarchy don't cohere.

## Design

## Ground truth

- **Primary target (p50):** IOC World Bird List v15.2 species counts
- **Reference span (p10/p90):** min/max counts across IOC, AviList, Clements, HBW/BirdLife, and Howard & Moore, derived from the comparison spreadsheet
- **Dispute blocks:** each scenario cell tagged `undisputed` or `disputed` from genus/family authority spread — supports comparing model calibration on stable vs taxonomically contested taxa

Download both files from [IOC Master Lists](https://www.worldbirdnames.org/ioc-lists/master-list-2/):

```
data/ioc_v15.2.xlsx              Life List+ or Master list
data/ioc_v15.2_comparison.xlsx   Comparison with other world lists
python scripts/derive_ioc_counts.py --update-scenarios
```
- **Scenarios:** 14 bird families × 2 genera each (1 well-known + 1 obscure) = 28 cells
- **Unique prompts:** 54 API calls — 28 genus + 14 family + 12 order
- **Prompts:** Single template in `prompts/taxonomy.txt` with `{taxonomic_unit}` filled per level (e.g. `the genus Corvus`)
- **Elicitation:** (p10, p50, p90) quantile intervals + confidence, structured JSON output
- **Models:** claude-haiku-4-5, claude-sonnet-4-6, claude-sonnet-5, claude-opus-4-8, gpt-4o-mini, gpt-4o (6 models; claude-fable-5 excluded — it refuses ~100% of these prompts on safety category `bio`, see Limitations)
- **Full run:** 54 prompts × 6 models = 324 API calls
- **Hierarchy scoring:** joins the 54 stored predictions across 28 cells for consistency checks
- **Harness:** runs on [Inspect AI](https://inspect.aisi.org.uk/) — `python -m src.run_inspect --models <comma list> --log-dir logs/latest`, then `python -m src.ingest_inspect --log-dir logs/latest --out results/latest_inspect` to score. The original custom harness (`run_eval.py`/`score.py --run`) still works and produced `results/latest/` (5 models, 46 prompts, no sonnet-5) — kept as a separate, earlier round rather than overwritten. `results/latest_inspect/` is the current 6-model/54-prompt round.

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

Pre-registered assumptions (before the 24→28 cell expansion), used to size the scenario count:

| Comparison | Effect size | Required n | Status at n=24 |
|---|---|---|---|
| Level difficulty gradient (genus vs. order) | d=0.5 (assumed) | ~25 scenarios | Adequately powered |
| Haiku vs. top tier | d~0.4 (from florida) | ~52 scenarios | Underpowered — directional only |
| Adjacent tiers (sonnet vs. opus) | d~0.1 | ~1000 scenarios | Do not claim |
| Strict violations | — | qualitative | Report with Clopper-Pearson CI |

**Actual per-pair numbers at n=54** (computed from the live 6-model round, `results/latest_inspect/summary.json` → `power_analysis`, not assumed): effect sizes vary a lot by pair, so no single "haiku vs. top tier" figure holds — e.g. haiku vs. gpt-4o is adequately powered (needs ~47, have 54), but haiku vs. opus-4.8 and haiku vs. sonnet-5 are still short (~63-64 needed). sonnet-5 vs. sonnet-4.6 needs ~123; sonnet-5 vs. opus-4.8 needs ~3,577 (the two are statistically indistinguishable on this task so far — more underpowered than the original sonnet-vs-opus assumption, not less). Check `power_analysis.pairs` in the summary for the full per-pair table before making any adjacent-tier claim.

n=28 cells is sufficient for structural/hierarchy findings. Model-ranking claims are limited to tier-level differences and should be checked per-pair against the real numbers above, same caveat as florida-weather-evals.

## Limitations

- Ground truth is IOC World Bird List (single authority for p50); cross-authority spans from the IOC comparison file inform reference p10/p90 bounds
- n=28 cells supports level-difficulty and structural claims and some tier-level comparisons; many adjacent model-tier pairs are still not resolvable — check the real per-pair power numbers, not the pre-registered assumptions, before claiming a difference
- Separate-prompt design measures coherence of independent beliefs, not reasoning under explicit hierarchical constraint
- Point target (single IOC count) rather than empirical distribution — CRPS reduces to quantile pinball loss
- `claude-fable-5` refuses ~100% of this eval's prompts on safety category `bio` (verified: genus/family/order level, multiple taxa) — recovering an answer requires a server-side fallback model, which would mean the "answers" are actually a different model wearing Fable's label. Excluded from the roster rather than reported misleadingly; revisit if Anthropic tunes this.
- IOC's species counts include recently-extinct-but-taxonomically-recognized species by design — this is not a benchmark artifact (see RESULTS.md's Passeriformes note)

## Repo structure

```
prompts/taxonomy.txt      prompt template
data/scenarios.yaml       28 taxonomy cells
scripts/                  IOC derivation, probe runner
src/                      schema, score (shared math), validate
src/run_eval.py           original custom harness (legacy; run_probe.py still depends on src/providers/)
src/providers/            Anthropic/OpenAI provider classes + registry.py (shared get_provider/_require_api_keys)
src/inspect_task.py       Inspect AI Task/Dataset/Scorer definition (current harness)
src/run_inspect.py        Inspect AI run entrypoint (eval_set orchestration)
src/ingest_inspect.py     bridges Inspect .eval logs back into score.py's scoring pipeline
data/                     IOC reference (ioc_*.xlsx gitignored)
logs/latest/              Inspect AI .eval logs (current 6-model/54-prompt round)
results/latest/           original custom-harness round (5 models, 46 prompts, no sonnet-5)
results/latest_inspect/   current Inspect-harness round (6 models, 54 prompts)
```
