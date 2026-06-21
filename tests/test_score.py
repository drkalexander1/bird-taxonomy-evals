"""Unit tests for taxonomy scoring and prompts."""

from __future__ import annotations

from src.schema import Prediction, PredictionRecord, Scenario, load_scenarios
from src.schema import build_prompt
from src.score import (
    build_frame,
    crps_point_target,
    hierarchy_consistency,
    mean_pinball,
    pinball_loss,
)
from src.schema import ScenarioCell


def _prompt(
    *,
    level: str,
    cell_id: str = "corvus_corvidae",
    ioc_count: int = 45,
) -> Scenario:
    if level == "genus":
        prompt_id = f"{cell_id}_genus"
    elif level == "family":
        prompt_id = "family_corvidae"
    else:
        prompt_id = "order_passeriformes"
    return Scenario(
        id=prompt_id,
        cell_id=cell_id,
        taxonomic_level=level,  # type: ignore[arg-type]
        genus="Corvus",
        family="Corvidae",
        order="Passeriformes",
        familiarity="well_known",
        ioc_count=ioc_count,
        ioc_genus=45,
        ioc_family=135,
        ioc_order=6590,
    )


def test_taxonomic_unit():
    sc = _prompt(level="genus")
    assert sc.taxonomic_unit == "the genus Corvus"
    sc = _prompt(level="family", ioc_count=135)
    assert sc.taxonomic_unit == "the family Corvidae"


def test_build_prompt():
    sc = _prompt(level="genus")
    prompt = build_prompt(sc)
    assert "the genus Corvus" in prompt
    assert "How many bird species are currently recognized" in prompt
    assert '"confidence"' in prompt


def test_pinball_perfect_median():
    assert pinball_loss(10.0, 10.0, 0.5) == 0.0


def test_crps_point_target_at_median():
    crps = crps_point_target(5.0, 10.0, 15.0, 10.0)
    assert crps == mean_pinball(10.0, 5.0, 10.0, 15.0)


def test_hierarchy_strict_violation():
    prompts = [
        _prompt(level="genus", ioc_count=45),
        _prompt(level="family", ioc_count=135),
        _prompt(level="order", ioc_count=6590),
    ]
    records = []
    for prompt in prompts:
        if prompt.taxonomic_level == "genus":
            p10, p50, p90 = 100.0, 200.0, 250.0
        elif prompt.taxonomic_level == "family":
            p10, p50, p90 = 100.0, 150.0, 200.0
        else:
            p10, p50, p90 = 5000.0, 6000.0, 7000.0
        records.append(
            PredictionRecord(
                prompt_key=prompt.prompt_key,
                model="test-model",
                provider="Test",
                prediction=Prediction(
                    p10=p10,
                    p50=p50,
                    p90=p90,
                    confidence=0.5,
                    reasoning="test",
                ),
            )
        )
    df = build_frame(prompts, records)
    cell = ScenarioCell(
        genus="Corvus",
        family="Corvidae",
        order="Passeriformes",
        familiarity="well_known",
        ioc_genus=45,
        ioc_family=135,
        ioc_order=6590,
    )
    cons = hierarchy_consistency([cell], df)
    assert len(cons) == 1
    assert bool(cons.iloc[0]["strict_violation"]) is True


def test_dispute_block_per_level():
    from src.schema import expand_cell

    cell = ScenarioCell(
        genus="Fratercula",
        family="Alcidae",
        order="Charadriiformes",
        familiarity="well_known",
        ioc_genus=3,
        ioc_family=25,
        ioc_order=390,
        authority_genus_min=3,
        authority_genus_max=3,
        authority_family_min=25,
        authority_family_max=25,
        authority_order_min=385,
        authority_order_max=390,
    )
    expanded = expand_cell(cell)
    genus = next(s for s in expanded if s.taxonomic_level == "genus")
    family = next(s for s in expanded if s.taxonomic_level == "family")
    order = next(s for s in expanded if s.taxonomic_level == "order")
    assert genus.dispute_block == "undisputed"
    assert family.dispute_block == "undisputed"
    assert order.dispute_block == "disputed"
    assert family.id == "family_alcidae"
    assert order.id == "order_charadriiformes"


def test_authority_span_coverage():
    prompts = [
        _prompt(level="genus", ioc_count=45).model_copy(
            update={"authority_min": 40, "authority_max": 50, "dispute_block": "disputed"}
        )
    ]
    records = [
        PredictionRecord(
            prompt_key=prompts[0].prompt_key,
            model="test-model",
            provider="Test",
            prediction=Prediction(
                p10=38,
                p50=45,
                p90=52,
                confidence=0.8,
                reasoning="test",
            ),
        )
    ]
    df = build_frame(prompts, records)
    assert bool(df.iloc[0]["covers_authority_span"]) is True
    assert bool(df.iloc[0]["ioc_in_interval"]) is True


def test_unique_prompt_count():
    prompts = load_scenarios()
    assert len(prompts) == 46
    assert len([p for p in prompts if p.taxonomic_level == "genus"]) == 24
    assert len([p for p in prompts if p.taxonomic_level == "family"]) == 12
    assert len([p for p in prompts if p.taxonomic_level == "order"]) == 10


def test_hierarchy_coherent():
    prompts = [
        _prompt(level="genus", ioc_count=45),
        _prompt(level="family", ioc_count=135),
        _prompt(level="order", ioc_count=6590),
    ]
    records = []
    for prompt in prompts:
        t = float(prompt.ioc_count)
        records.append(
            PredictionRecord(
                prompt_key=prompt.prompt_key,
                model="test-model",
                provider="Test",
                prediction=Prediction(
                    p10=t * 0.8,
                    p50=t,
                    p90=t * 1.2,
                    confidence=0.8,
                    reasoning="test",
                ),
            )
        )
    df = build_frame(prompts, records)
    cell = ScenarioCell(
        genus="Corvus",
        family="Corvidae",
        order="Passeriformes",
        familiarity="well_known",
        ioc_genus=45,
        ioc_family=135,
        ioc_order=6590,
    )
    cons = hierarchy_consistency([cell], df)
    assert bool(cons.iloc[0]["strict_violation"]) is False
