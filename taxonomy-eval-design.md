# Taxonomy Eval — Design Doc

Round 3 of the calibration benchmark program. Read alongside the README.

## Research program context

Same overarching question across all three rounds: do models know what they don't know? Rounds 1 and 2 tested probabilistic forecasts against external ground truth (eBird, FAWN). This round shifts focus: instead of "are the model's uncertainty intervals calibrated against reality?", the primary question is "are the model's independent beliefs about different levels of the same hierarchy mutually coherent?"

The consistency check was a secondary finding in florida-weather-evals (seasonal self-consistency, no ground truth needed). Here it is the primary design.

## Framing decision (decide before coding)

**Do not make the headline about pass rate.** Monotonic nesting (genus ≤ family ≤ order) is a low bar — a model can satisfy it and be wildly wrong on every number. The interesting findings are:

1. **Strict violations** (genus_p50 > family_p50, or family_p50 > order_p50) — the impossible-cell analogue from florida; rare but damning
2. **Hierarchy collapse** — genus_p50 ≈ family_p50 ≈ order_p50 (model assigns similar counts to all levels); taxonomic version of florida's answer recycling
3. **Three-way split:** coherent-and-right / coherent-but-wrong / incoherent — same structure that made the florida consistency section work

## Ground truth

**Use IOC World Bird List, not GBIF.**

GBIF counts occurrence records, not described species — the number you get reflects submission history, not taxonomy. Catalogue of Life and ITIS are better but still have cross-authority disagreement. IOC World Bird List is:
- Versioned (cite the version used)
- Downloadable as Excel (worldbirdnames.org)
- Authoritative for family and order counts within Aves
- Stable enough that family/order counts don't shift run-to-run

Derive a CSV from the IOC spreadsheet and commit that; gitignore the raw xlsx.

## Scenario selection

**12 bird families, 2 genera per family.** Within each family:
- 1 genus that is well-known (higher model familiarity, expect lower uncertainty)
- 1 genus that is less-known (expect higher uncertainty or recycling)

This gives a secondary within-family comparison and tests whether models widen intervals for obscure genera — the specificity gradient from florida, applied to taxonomic familiarity.

Candidate families (vary by size and familiarity):
- Corvidae (crows/jays) — large, well-known
- Trochilidae (hummingbirds) — large, specialists know it
- Psittacidae (parrots) — large, popular
- Strigidae (owls) — medium, well-known
- Ramphastidae (toucans) — medium, recognizable
- Pittidae (pittas) — small, obscure
- Accipitridae, Anatidae, Fringillidae, Columbidae, Falconidae, Alcidae (added for n=24)

Final family list: confirm counts from IOC before committing to scenarios.

## Prompt design

**Single template** in `prompts/taxonomy.txt`. Each level uses explicit Latin rank via `{taxonomic_unit}`:

> How many bird species are currently recognized in **the genus Corvus** worldwide?

To adapt for a future eval, edit the template text or add a new file and point `PROMPT_PATH` in `schema.py`.

**Separate prompts for each level.** The model doesn't know it's being consistency-checked.

## Scoring

```
crps_relative = crps(p10, p50, p90, ioc_count) / ioc_count
```

CRPS against a point target (single IOC integer) = sum of pinball losses at each quantile. Normalize by ioc_count so genus (small n) and order (large n) are on the same scale.

**Consistency metrics per scenario × prompt_variant:**
- `strict_violation`: bool — any level where child_p50 > parent_p50
- `compression_ratio`: genus_p50 / family_p50 (reference from IOC actuals; flag if model ratio >> IOC ratio)
- `gap_ratio`: (family_p50 - genus_p50) / family_p50; compare to IOC reference gap

**Three-way classification per scenario × model:**
- Coherent-and-right: no strict violation AND crps_relative within 1 SD of best model
- Coherent-but-wrong: no strict violation BUT systematic bias (e.g., all levels over/underestimated in same direction)
- Incoherent: strict violation OR compression_ratio > threshold (TBD from data)

## Power analysis summary

- **Level difficulty gradient (genus vs. order):** d=0.5 assumed, paired t-test, ~25 scenarios needed → n=24 is borderline adequate
- **Cross-model (haiku vs. top tier):** d~0.4 from florida, ~52 scenarios needed → directional only at n=24
- **Adjacent tiers (sonnet vs. opus):** ~1000 scenarios → do not claim
- **Strict violations:** qualitative; report proportion with Clopper-Pearson 95% CI
- **Pre-register:** level difficulty (genus harder than order), strict violation rate > 0%, gpt-4o confidence decorative

## Pre-registration checklist

Before running any model:
- [ ] IOC version locked (record in manifest)
- [ ] All 24 scenarios written and committed to `prompts/`
- [ ] Scoring code written and unit-tested on synthetic data
- [ ] Hypotheses written down: what direction do you expect each finding to go?

## What not to claim

- Do not rank adjacent Claude tiers (sonnet vs. opus) — underpowered
- Do not claim GBIF counts as ground truth
- Do not interpret strict-violation pass rate as the headline — it's a floor, not the finding
- Do not compare directly to florida crps_relative values — different domain, different target scale
