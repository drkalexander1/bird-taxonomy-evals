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

## Calibration by model

| Model | CRPS rel | Median abs error | Strict violations |
|-------|----------|------------------|-------------------|
| Opus | **0.058** | 8.6 | 0 |
| gpt-4o | 0.101 | 27.0 | 0 |
| Sonnet | 0.108 | 11.5 | 0 |
| Haiku | 0.139 | 18.2 | 2 |
| gpt-4o-mini | 0.163 | 56.9 | 3 |

**Statistically defensible at n=46:** Opus vs mini. **Not defensible:** Sonnet vs Opus, Sonnet vs gpt-4o, Haiku vs mini — treat as directional only.

**Error concentrates at higher levels:** order prompts have the largest absolute errors (mean ~73 species off); genus prompts are much tighter (~3.7 off). Order estimates also cluster **below** IOC Passeriformes (see flags below).

---

## What “coherent but wrong” looks like

The dominant failure mode: models answer each prompt in isolation with **stable but incorrect templates**:

- **gpt-4o-mini** reuses the same family count across unrelated cells (Corvidae → 40; Trochilidae → 350; Fringillidae → 50; Ramphastidae → 15) and pairs Trochilidae with Apodiformes order **120** (IOC: family 366, order 478).
- **Haiku** often overshoots family counts (e.g. Psittacidae **370** vs IOC **181**; Accipitridae genus **52** vs IOC **9**).
- **Top models** mostly get family/order in the right ballpark but still miss on specific disputed taxa.

This is the round's core claim: **calibration of independent hierarchical beliefs**, not single-shot trivia accuracy.

---

## Items to review in more detail

Worth a closer read in `classification.csv`, `consistency.csv`, and `by_prompt.csv`.

### Passeriformes / extinct species (methodology)

All models estimate Passeriformes at **6000–6500**; IOC ground truth is **6758**. IOC includes **163 extinct** species and the prompt says "currently recognized." That gap may partly be a **benchmark bug**, not model error. Fix before publishing headline order-level numbers.

### Accipiter genus — universal overcount

**Every model** grossly overcounts *Accipiter* species (p50 **35–52** vs IOC **9**). This is not a small-model problem — even Opus says 35. Likely confusion with Accipitridae scope or hawks in general. Good case study for prompt ambiguity.

### gpt-4o-mini template collapse

Beyond the three strict violations, mini shows **repeated identical family/order answers** across unrelated cells (Fringillidae 50, Piciformes 75, Apodiformes 120). Suggests the model is not conditioning on the specific taxon.

### Haiku Falconidae inversion

Family 67 > order 65 is a near-miss — the model may be conflating Falconidae with Falconiformes species totals (~65 is plausible for the order). Suggests **rank confusion**, not random noise.

### Haiku Pitta collapse

Genus = family = 32 while order = 6500. The model may be answering "how many Pitta species" for both prompts. Interesting **prompt-interference** pattern without breaking order nesting.

### Opus: best accuracy, high confidence ECE

Opus has the best CRPS but among the highest **confidence ECE (0.28)** on Claude models — accurate but not well-calibrated on stated confidence. Mini is worst (ECE **0.41**, overconfident). gpt-4o has oddly **low** ECE (0.04) despite mediocre accuracy.

### Disputed vs undisputed paradox

Globally, **undisputed genus cells** have worse relative CRPS than disputed family/order cells — mostly a **scale artifact** (tiny genus counts inflate relative error). Per-model, mini is much worse on undisputed (0.25 vs 0.13 CRPS rel). Do not over-interpret the aggregate split without level stratification.

### Amazona / Psittacidae family

Several models (especially Haiku, gpt-4o) give Psittacidae ~**370–400** vs IOC **181** — may be counting parrots globally across outdated lumped taxonomy. Good disputed-block example.

### Piciformes order (mini)

Mini: order p50 **75** vs IOC **444** — one of the worst single prompts (CRPS rel 0.41). Same cell family p50 15 vs 38. Complete miss at order level while still nesting.

### What worked

- **Corvidae / Columbidae / Falconidae** (non-mini): most models coherent and near IOC.
- **Obscure genera** often scored better in absolute terms — models are appropriately uncertain on tiny counts.
- **Opus on 20/24 cells**: unusual for a zero-violation, mostly-accurate run on a hard knowledge task.

---

## Suggested narrative

1. **Nesting is necessary but not sufficient** — 114/120 cells pass strict nesting; only 51/120 are both coherent and near IOC.
2. **Tier split is real at the bottom** — mini (and partly Haiku) show template reuse and occasional impossible nesting; Opus is in a different class.
3. **Middle tiers are messy** — Sonnet ≈ gpt-4o on accuracy; neither separates statistically from Opus at n=46.
4. **Separate prompts reveal belief structure** — the Trochilidae and Corvidae mini cases are smoking guns for non-conditional priors.

---

## Caveats

- n=46 prompts / 24 cells: strong on structure, weak on adjacent model comparisons
- IOC-only point target for p50; authority spans informative but not scored as primary
- Extinct-species mismatch on order counts (fix before final numbers)
- No o3 in this run (5 models only)
