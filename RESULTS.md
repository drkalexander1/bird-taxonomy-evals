# Bird Taxonomy Eval — Results

Live run outputs are in [`results/latest/`](results/latest/) (`predictions.jsonl`, `summary.json`, CSVs, chart). Theropod probe outputs are in [`results/probes/`](results/probes/).

## Setup

Round 3 calibration benchmark: **46 independent prompts** (24 genus + 12 family + 10 order) across **24 scenario cells** (12 families × 2 genera each). Each model answered genus, family, and order in **separate prompts** with no explicit hierarchy constraint. Ground truth: **IOC v15.2** point counts; cross-authority spans for reference intervals.

**Run:** 5 models × 46 prompts = **230 API calls**

- claude-haiku-4-5, claude-sonnet-4-6, claude-opus-4-8, gpt-4o-mini, gpt-4o

---

## Headline

**Most models nest correctly most of the time.** The interesting signal is not catastrophic reasoning failure — it is whether independent beliefs at different taxonomic levels **cohere and track reality**.

| Model | Coherent & right | Coherent but wrong | Incoherent |
|-------|------------------|--------------------|------------|
| Opus | **20/24** | 4 | 0 |
| Sonnet | 12 | 12 | 0 |
| gpt-4o | 10 | 14 | 0 |
| Haiku | 5 | 16 | 3 |
| gpt-4o-mini | 4 | 17 | 3 |

**Opus stands out:** best calibration (CRPS relative **0.058**) and zero hierarchy failures. Weaker models mostly fail by being **systematically wrong while still nesting** — shared wrong priors at family/order level rather than impossible geometry.

---

## Hierarchy consistency

**Strict violations** (genus p50 > family p50, or family p50 > order p50): **5 total**, all from smaller models, on **different taxa**:

| Model | Cell | Issue |
|-------|------|-------|
| gpt-4o-mini | Corvus / Corvidae | genus 45 > family **40** |
| gpt-4o-mini | Archilochus & Chaetocercus / Trochilidae | family **350** > order **120** (same wrong pair reused) |
| claude-haiku-4-5 | Falco & Microhierax / Falconidae | family **67** > order **65** |
| claude-haiku-4-5 | Pitta / Pittidae | genus = family = **32** (hierarchy collapse, not strict) |

Sonnet, Opus, and gpt-4o: **zero** strict violations across all 24 cells.

**Soft incoherence:** only one case without a strict violation — Haiku treating Pitta genus and Pittidae family as identical size. Mini's Corvus cell also triggered compression-exceeds-IOC (genus/family ratio wildly off IOC).

A cell is labeled **incoherent** if any of these fire: strict violation, hierarchy collapse (genus/family ratio > 0.9), or compression ratio far above IOC.

---

## Calibration summary

| Model | CRPS rel | Strict violations | Confidence pattern |
|-------|----------|-------------------|-------------------|
| Opus | **0.058** | 0 | Varies appropriately (0.40–0.95) |
| gpt-4o | 0.101 | 0 | Uniform ~0.8 (4 distinct values) |
| Sonnet | 0.108 | 0 | Varies moderately (13 distinct values) |
| Haiku | 0.139 | 2 | Locked ~0.72 (5 distinct values) |
| gpt-4o-mini | 0.163 | 3 | Locked ~0.85 (3 distinct values) |

**Statistically defensible at n=46:** Opus vs mini. **Not defensible:** Sonnet vs Opus, Sonnet vs gpt-4o, Haiku vs mini — treat as directional only.

**Error concentrates at higher levels:** order prompts have the largest absolute errors (mean ~73 species off); genus prompts are much tighter (~3.7 off). Order estimates also cluster **below** IOC Passeriformes (see flags below).

---

## Three diagnostic patterns

### 1. Confidence as a calibration signal

Weaker models produce **uniform confidence scores regardless of taxon** — a template, not calibration.

- **Haiku** reports confidence **0.72** on Accipitridae family (p50 240) and **0.72** on Corvus genus (p50 45), with only **5 distinct confidence values** across all 46 prompts (range 0.55–0.85). Even monotypic *Fratercula* (IOC: 3 species) gets 0.85.
- **gpt-4o-mini** sits at **0.85** on most prompts (3 distinct values, range 0.80–0.90) — including order-level answers it gets badly wrong.

**Opus varies meaningfully:** confidence **0.95** on monotypic genera (*Xenoglaux*, *Urotriorchis*), dropping to **0.40** on *Accipiter* where it correctly flags ongoing generic splits. Confidence variance is itself a calibration signal — the model knows when it knows.

Sonnet occupies the middle ground (13 distinct confidence values, 0.45–0.97). gpt-4o is flatter than Sonnet or Opus (~0.8 on most prompts) but not as locked as Haiku or mini.

### 2. Template reuse in weaker models

**gpt-4o-mini** reuses identical family and order counts across unrelated cells — the same shared prompts return fixed values whether the cell is Archilochus or Chaetocercus, Corvus or Nucifraga:

| Shared prompt | mini p50 | IOC |
|---------------|----------|-----|
| family_corvidae | 40 | 138 |
| family_trochilidae | 350 | 366 |
| family_fringillidae | 50 | 238 |
| family_ramphastidae | 15 | 38 |
| order_apodiformes | **120** | **478** |
| order_piciformes | 75 | 444 |

This suggests the model is not conditioning on the specific taxon but retrieving a cached estimate. The Apodiformes order answer is especially telling: p50 **120** vs IOC **478** — roughly the magnitude of a single large family, as if hummingbirds were largely omitted from the order tally while Trochilidae (350) was answered separately.

Haiku shows a softer version of the same pattern: repeated family-level priors (e.g. Psittacidae **370**, Accipitridae genus **52**) with confidence held near 0.72.

### 3. Accipiter as a case study in failure modes

**Every model overcounts *Accipiter* species** (IOC: **9**), but for different reasons:

| Model | p10 | p50 | p90 | Confidence |
|-------|-----|-----|-----|------------|
| Opus | 12 | 35 | 50 | **0.40** |
| gpt-4o | 40 | 50 | 60 | 0.80 |
| Sonnet | 40 | 50 | 60 | 0.60 |
| Haiku | 45 | 52 | 60 | 0.72 |
| gpt-4o-mini | 10 | 12 | 15 | 0.85 |

**Opus** explicitly notes recent generic splits moving species to *Astur* and *Tachyspiza*, widens the interval (p10=12), and lowers confidence — the right epistemic behavior even though p50=35 is still miscalibrated against IOC.

**Haiku and gpt-4o** give high-confidence overcounts (52 and 50) with no acknowledgment of taxonomic uncertainty; Haiku's reasoning treats "~50–55 species" as settled fact.

**gpt-4o-mini** lands closer on the median (p50=12) but with **0.85 confidence** and reasoning that incorrectly treats the count as well-established — wrong uncertainty shape, not just wrong number.

This is the benchmark working as intended: same ground truth, same prompt, divergent **epistemic behavior** across tiers.

---

## What “coherent but wrong” looks like

The dominant failure mode beyond the diagnostic patterns above: models answer each prompt in isolation with **stable but incorrect templates** while still nesting correctly.

- **Top models** mostly get family/order in the right ballpark but miss on specific disputed taxa.
- **Haiku / mini** combine template reuse with occasional hierarchy breaks (see above).

This is the round's core claim: **calibration of independent hierarchical beliefs**, not single-shot trivia accuracy.

---

## Items to review in more detail

Worth a closer read in `classification.csv`, `consistency.csv`, `by_prompt.csv`, and `predictions.jsonl` (reasoning text).

### Passeriformes / extinct species (methodology)

All models estimate Passeriformes at **6000–6500**; IOC ground truth is **6758**. IOC includes **163 extinct** species and the prompt says "currently recognized." That gap may partly be a **benchmark bug**, not model error. Fix before publishing headline order-level numbers.

### Haiku Falconidae inversion

Family 67 > order 65 is a near-miss — the model may be conflating Falconidae with Falconiformes species totals (~65 is plausible for the order). Suggests **rank confusion**, not random noise.

### Haiku Pitta collapse

Genus = family = 32 while order = 6500. The model may be answering "how many Pitta species" for both prompts. Interesting **prompt-interference** pattern without breaking order nesting.

### Confidence ECE vs qualitative pattern

Aggregate **ECE** tells a related but distinct story: mini is worst (0.41, overconfident), Opus highest among Claude models (0.28) despite qualitatively appropriate confidence *variance* — high confidence on easy monotypic genera pulls ECE up even when that confidence is justified.

### Disputed vs undisputed paradox

Globally, **undisputed genus cells** have worse relative CRPS than disputed family/order cells — mostly a **scale artifact** (tiny genus counts inflate relative error). Per-model, mini is much worse on undisputed (0.25 vs 0.13 CRPS rel). Do not over-interpret the aggregate split without level stratification.

### Amazona / Psittacidae family

Several models (especially Haiku, gpt-4o) give Psittacidae ~**370–400** vs IOC **181** — may be counting parrots globally across outdated lumped taxonomy. Good disputed-block example.

### What worked

- **Corvidae / Columbidae / Falconidae** (non-mini): most models coherent and near IOC.
- **Obscure genera** often scored better in absolute terms — models are appropriately uncertain on tiny counts (when they vary confidence at all).
- **Opus on 20/24 cells**: unusual for a zero-violation, mostly-accurate run on a hard knowledge task.

---

## Suggested narrative

1. **Nesting is necessary but not sufficient** — 114/120 cells pass strict nesting; only 51/120 are both coherent and near IOC.
2. **Tier split is real at the bottom** — mini (and partly Haiku) show locked confidence, template reuse, and occasional impossible nesting; Opus is in a different class.
3. **Middle tiers are messy** — Sonnet ≈ gpt-4o on accuracy; neither separates statistically from Opus at n=46.
4. **Separate prompts reveal belief structure** — confidence flatness and shared family/order priors are smoking guns for non-conditional beliefs.
5. **Accipiter exposes epistemic tiering** — same overcount problem, qualitatively different uncertainty handling.

---

## Caveats

- n=46 prompts / 24 cells: strong on structure, weak on adjacent model comparisons
- IOC-only point target for p50; authority spans informative but not scored as primary
- Extinct-species mismatch on order counts (fix before final numbers)
- No o3 in this run (5 models only)
