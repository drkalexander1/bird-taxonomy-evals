# Bird Taxonomy Eval — Results

Current round outputs are in [`results/latest_inspect/`](results/latest_inspect/) (`summary.json`, CSVs, chart) — run via the Inspect AI harness, logs in [`logs/latest/`](logs/latest/). The prior 5-model/24-cell round (no sonnet-5, original custom harness) is kept side by side in [`results/latest/`](results/latest/) rather than overwritten. Theropod probe outputs are in [`results/probes/`](results/probes/).

## Setup

Round 3 calibration benchmark: **54 independent prompts** (28 genus + 14 family + 12 order) across **28 scenario cells** (14 families × 2 genera each). Each model answered genus, family, and order in **separate prompts** with no explicit hierarchy constraint. Ground truth: **IOC v15.2** point counts; cross-authority spans for reference intervals.

**Run:** 6 models × 54 prompts = **324 API calls**

- claude-haiku-4-5, claude-sonnet-4-6, **claude-sonnet-5**, claude-opus-4-8, gpt-4o-mini, gpt-4o

---

## Headline

**Sonnet 5 is the new standout, not just an incremental bump.** It leads every model — including Opus — on the coherent-and-right count, and its calibration on undisputed taxa is in a different class from everything else in the roster.

| Model | Coherent & right | Coherent but wrong | Incoherent |
|-------|------------------|--------------------|------------|
| **Sonnet 5** | **22/28** | 6 | 0 |
| Opus | 19/28 | 9 | 0 |
| Sonnet 4.6 | 14/28 | 14 | 0 |
| gpt-4o | 11/28 | 16 | 1 |
| Haiku | 4/28 | 21 | 3 |
| gpt-4o-mini | 3/28 | 24 | 1 |

**Opus still wins on strict CRPS** (0.058 vs Sonnet 5's 0.068) — it's the more conservative, better-hedged estimator on hard disputed taxa. But Sonnet 5 has the **lowest mean absolute error of any model** (9.0 vs Opus's 9.6) and, notably, is dramatically better calibrated than everyone else on **undisputed** taxa (CRPS-relative 0.020 vs the next-best 0.071 — see the disputed/undisputed section below). Sonnet 4.6 → Sonnet 5 is a real jump: coherent-and-right count nearly doubled (14 → 22) and CRPS-relative improved by ~37% (0.108 → 0.068).

---

## Hierarchy consistency

**Strict violations** (genus p50 > family p50, or family p50 > order p50): **2 total**, both from Haiku, both the *same* family prompt (`family_anatidae` = 160) reused above a lower order answer (`order_anseriformes` = 150), shared across two unrelated genus cells:

| Model | Cell | Issue |
|-------|------|-------|
| claude-haiku-4-5 | Anas / Anatidae | family **160** > order **150** |
| claude-haiku-4-5 | Sarkidiornis / Anatidae | family **160** > order **150** (same shared pair reused) |

Sonnet 4.6, **Sonnet 5**, Opus, gpt-4o, and gpt-4o-mini: **zero** strict violations across all 28 cells.

**Hierarchy collapse** (genus p50 = family p50, ratio > 0.9) still shows up on *Pitta / Pittidae* — and persists across the same three weaker models as the prior round: Haiku (32=32), gpt-4o (35=35), gpt-4o-mini (10=10). Their reasoning text for the genus and family prompts is close to word-for-word identical, suggesting the model answers "how many *Pitta* species" for both. **Sonnet 5, Sonnet 4.6, and Opus all avoid this** — e.g. Sonnet 5 gives genus=15 (via the obscure *Erythropitta* cell) vs family=42, correctly separated.

A cell is labeled **incoherent** if any of these fire: strict violation, hierarchy collapse, or compression ratio far above IOC.

---

## Calibration summary

| Model | CRPS rel | Mean abs error | Strict violations | Confidence pattern |
|-------|----------|----------------|--------------------|--------------------|
| Opus | **0.058** | 9.63 | 0 | Varies widely (10 distinct values, 0.35–0.95) |
| **Sonnet 5** | 0.068 | **9.04** | 0 | Moderate variance (9 distinct values, 0.5–0.97) |
| gpt-4o | 0.092 | 23.07 | 0 | Fairly uniform (5 distinct values, 0.7–0.95) |
| Sonnet 4.6 | 0.108 | 9.91 | 0 | Most granular (15 distinct values, 0.45–0.98) |
| Haiku | 0.133 | 15.91 | 2 | Locked ~0.72 (6 distinct values, 0.55–0.92) |
| gpt-4o-mini | 0.147 | 37.22 | 0 | Locked ~0.85 (3 distinct values, 0.8–0.9) |

Note the **confidence-granularity paradox**: Sonnet 4.6 uses more distinct confidence values (15) than Sonnet 5 (9), yet Sonnet 5 is markedly better calibrated on both CRPS and absolute error. Granular-looking confidence is not itself evidence of better calibration — it has to track actual difficulty, not just vary for variety's sake.

**Statistically defensible at n=54** (per `power_analysis` in `summary.json`): Haiku vs gpt-4o, Opus vs gpt-4o-mini. **Not yet defensible:** Sonnet 5 vs Opus (need ~3,577 scenarios — the two are statistically indistinguishable on this task, more so than the pre-registered sonnet-vs-opus assumption predicted), Sonnet 5 vs Sonnet 4.6 (need ~123), Haiku vs Opus and Haiku vs Sonnet 5 (need ~63–64, have 54, close but short). Treat any adjacent-tier ranking claim as directional only — check `power_analysis.pairs` before asserting a difference.

**Error still concentrates at higher levels:** order prompts have the largest absolute error (mean ~50 species off across all models); genus prompts are much tighter (~3.3 off). Order estimates cluster in a narrow 6000–6500 band across every model, well below IOC Passeriformes (see flags below).

---

## Disputed vs undisputed: Sonnet 5's standout result

| Model | Undisputed CRPS-rel | Disputed CRPS-rel |
|-------|---------------------|--------------------|
| **Sonnet 5** | **0.020** | 0.088 |
| Opus | 0.071 | **0.052** |
| gpt-4o | 0.071 | 0.101 |
| Sonnet 4.6 | 0.124 | 0.101 |
| Haiku | 0.165 | 0.119 |
| gpt-4o-mini | 0.237 | 0.109 |

Sonnet 5 is roughly **3.5x better** than the next-best model (Opus/gpt-4o at 0.071) on undisputed taxa — cells where the count isn't taxonomically contested and there's a single clean IOC answer to converge on. On disputed cells (where authorities genuinely disagree), Opus remains the strongest, most conservative estimator. The split suggests Sonnet 5's gains are concentrated in **precision on settled facts** rather than better handling of genuine taxonomic uncertainty — a useful distinction for anyone using this benchmark to pick a model for a specific task.

---

## Three diagnostic patterns

### 1. Confidence as a calibration signal

Weaker models still produce **uniform confidence scores regardless of taxon** — a template, not calibration. This pattern is unchanged from the prior round.

- **Haiku** reports confidence **0.72** on *Pittidae* family (p50 32) and **0.72** on *Accipiter* genus (p50 52), with only **6 distinct confidence values** across all 54 prompts (range 0.55–0.92).
- **gpt-4o-mini** sits at **0.85** on most prompts (3 distinct values, range 0.80–0.90) — including order-level answers it gets badly wrong.

**Opus varies the most** (10 distinct values, 0.35–0.95): confidence 0.95 on easy monotypic genera, dropping to 0.4 on *Accipiter* where it explicitly flags ongoing generic splits and widens its interval accordingly.

**Sonnet 5 sits close behind Opus** (9 distinct values, 0.5–0.97) but with fewer, coarser steps than Sonnet 4.6 (15 values) — see the granularity paradox above. gpt-4o is flatter (5 values, ~0.7–0.95) but not as locked as Haiku or mini.

### 2. Template reuse in weaker models

**gpt-4o-mini** still reuses near-identical family and order counts across unrelated cells regardless of the specific taxon:

| Shared prompt | mini p50 | IOC |
|---------------|----------|-----|
| family_pittidae | 10 | ~35 |
| order_passeriformes | 6000 | 6758 |
| family_accipitridae | 250 | 254 |

**Haiku and gpt-4o** show the same pattern on *Pitta*: Haiku's genus and family reasoning for Pitta/Pittidae is nearly word-for-word identical ("30-35 recognized species... recent taxonomic revisions have split some former species"), and both land on the exact same p50 for genus and family. This is the same prompt-interference bug flagged in the prior round — it has not been fixed by moving to newer model versions of the same lineage in Sonnet's case (it doesn't reproduce in Sonnet 4.6 or 5), but persists in Haiku, gpt-4o, and gpt-4o-mini.

### 3. Accipiter as a case study in failure modes

**Every model overcounts *Accipiter* species** (IOC: **9**) — including Sonnet 5 — but for different reasons:

| Model | p10 | p50 | p90 | Confidence | Notes |
|-------|-----|-----|-----|------------|-------|
| Opus | 12 | **35** | 52 | 0.40 | Cites 2024 generic splits (Astur, Tachyspiza), acts on them |
| Sonnet 5 | 45 | 50 | 55 | 0.60 | Cites splits/lumps but doesn't discount the estimate much |
| Sonnet 4.6 | 48 | 52 | 58 | 0.65 | No mention of splits, treats ~52 as settled |
| gpt-4o | 40 | 50 | 60 | 0.80 | High-confidence overcount, no split awareness |
| Haiku | 45 | 52 | 60 | 0.72 | High-confidence overcount, no split awareness |
| gpt-4o-mini | 15 | 20 | 25 | 0.80 | Closer to plausible but still 2x IOC, high confidence |

**Opus** is the only model that translates split-awareness into a materially lower median (35, vs 50–52 for the Claude/gpt-4o pack) and a genuinely lower confidence (0.40). **Sonnet 5 knows about the same splits** — its reasoning text explicitly names "Tiny/Gray-throated Sparrowhawks and various island forms" moving out of the genus — but still centers on p50=50 with only moderate confidence reduction (0.6). This is a case where Sonnet 5's overall improvement in coherence and undisputed-taxa precision doesn't carry over to genuinely disputed, actively-revised taxa — Opus's more aggressive epistemic hedging still wins here.

This remains the benchmark working as intended: same ground truth, same prompt, divergent **epistemic behavior** across tiers and even across generations of the same model family.

---

## What "coherent but wrong" looks like

The dominant failure mode beyond the diagnostic patterns above: models answer each prompt in isolation with **stable but incorrect templates** while still nesting correctly.

- Sonnet 5 and Opus mostly get family/order in the right ballpark but still miss on specific disputed taxa (e.g. Accipiter, Amazona/Psittacidae).
- Sonnet 4.6 and gpt-4o are split roughly 50/50 between right and systematically-off.
- Haiku / mini combine template reuse with occasional hierarchy breaks (see above).

This is the round's core claim: **calibration of independent hierarchical beliefs**, not single-shot trivia accuracy.

---

## Items to review in more detail

Worth a closer read in `classification.csv`, `consistency.csv`, `by_prompt.csv`, and the Inspect `.eval` logs in `logs/latest/` (full reasoning text, readable via `inspect_ai.log.read_eval_log`).

### Passeriformes / extinct species (methodology note, resolved)

All six models still estimate Passeriformes at **6000–6900**; IOC ground truth is **6758**, which includes **62 extinct-but-taxonomically-recognized** species — not a benchmark artifact. IOC's species counts include extinct species by definition. Sonnet 5 (p50=6500), Sonnet 4.6 (6500), Haiku (6500), and Opus (6400) cluster close to IOC; gpt-4o and gpt-4o-mini undercount more (6000 each). This gap looks like a genuine order-level estimation shortfall for the weaker two models, not a ground-truth mismatch.

### Anas / Sarkidiornis strict violation (Haiku)

Family **160** > order **150** on two unrelated genus cells sharing the same Anatidae family prompt. Same failure shape as the prior round's Falconidae inversion — a shared family/order prompt pair answered inconsistently relative to each other, not a per-cell reasoning error.

### Haiku / gpt-4o / gpt-4o-mini Pitta collapse

Genus = family (32/35/10 respectively) while order = ~6000–6500. Reasoning text for genus and family prompts is nearly identical across all three models, suggesting the model is answering "how many *Pitta* species" for both prompts. Notably **absent in Sonnet 4.6, Sonnet 5, and Opus** — worth checking whether this is a lineage-specific fix or coincidental given the small n.

### Confidence ECE vs qualitative pattern

Aggregate **ECE** tells a related but distinct story: mini is worst (0.335, overconfident), **Opus is now the highest ECE among all six models except mini (0.245)**, with Sonnet 5 close behind (0.200) — both pulled up by justified high confidence on easy monotypic genera. gpt-4o has by far the *lowest* ECE (0.034) despite mediocre CRPS — its confidence is uniformly moderate (~0.8) and its accuracy is also uniformly moderate, so the two happen to track without the model doing anything sophisticated. **ECE alone is a misleading ranking signal here** — pair it with the qualitative confidence-variance read, not use it standalone.

### Amazona / Psittacidae family

Opus (180), Sonnet 4.6 (200), and Sonnet 5 (180) now cluster close to IOC (181); Haiku (370) and gpt-4o (400) still overcount by ~2x, likely counting parrots globally across outdated lumped taxonomy. Good disputed-block example of the top-tier/bottom-tier split holding steady across the version bump.

### What worked

- **Corvidae / Columbidae / Falconidae / Alcidae** (non-mini): most models coherent and near IOC.
- **Obscure genera** often scored better in absolute terms — models are appropriately uncertain on tiny counts (when they vary confidence at all).
- **Sonnet 5 on 22/28 cells**: the new high-water mark for coherent-and-right, ahead of Opus's 19/28 — driven mostly by precision gains on undisputed taxa rather than better handling of contested ones.

---

## Suggested narrative

1. **Nesting is necessary but not sufficient** — 322/324 predictions pass strict nesting; only ~half the cells across the roster are both coherent and near IOC.
2. **Sonnet 5 is a real step up from Sonnet 4.6** — nearly doubled coherent-and-right count, ~37% CRPS-relative improvement, and it's the new leader by that metric, ahead of Opus.
3. **But the gain is uneven** — Sonnet 5 dominates undisputed taxa (3.5x better than anyone else) while Opus remains stronger on genuinely disputed, actively-revised taxa like Accipiter.
4. **Tier split is still real at the bottom** — mini (and partly Haiku) show locked confidence, template reuse, and occasional impossible nesting.
5. **Separate prompts still reveal belief structure** — confidence flatness and the Pitta collapse are smoking guns for non-conditional beliefs, and they persist unevenly across model generations (fixed in newer Claude, not in gpt-4o or mini).
6. **Confidence granularity ≠ calibration** — Sonnet 4.6 uses more distinct confidence values than Sonnet 5 but is worse calibrated; ECE alone likewise misranks gpt-4o as best-calibrated when its flat confidence just happens to match its flat accuracy.

---

## Caveats

- n=54 prompts / 28 cells: strong on structure, but most adjacent-tier model comparisons (Sonnet 5 vs Opus especially) are still statistically indistinguishable — check `power_analysis.pairs` in `results/latest_inspect/summary.json` before asserting a ranking
- IOC-only point target for p50; authority spans informative but not scored as primary
- Separate-prompt design measures coherence of independent beliefs, not reasoning under explicit hierarchical constraint
- `claude-fable-5` excluded from this round — refuses ~100% of prompts on safety category `bio` (see README Limitations)
