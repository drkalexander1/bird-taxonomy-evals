"""Unit tests for taxonomy scoring and prompts."""

from __future__ import annotations

from src.schema import Prediction, PredictionRecord, Scenario, build_prompt
from src.score import (
    build_frame,
    crps_point_target,
    hierarchy_consistency,
    mean_pinball,
    pinball_loss,
)


def _scenario(
    *,
    level: str,
    cell_id: str = "corvus_corvidae",
    ioc_count: int = 45,
) -> Scenario:
    return Scenario(
        id=f"{cell_id}_{level}",
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
    sc = _scenario(level="genus")
    assert sc.taxonomic_unit == "the genus Corvus"
    sc = _scenario(level="family", ioc_count=135)
    assert sc.taxonomic_unit == "the family Corvidae"


def test_build_prompt():
    sc = _scenario(level="genus")
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
    scenarios = [
        _scenario(level="genus", ioc_count=45),
        _scenario(level="family", ioc_count=135),
        _scenario(level="order", ioc_count=6590),
    ]
    records = []
    for s in scenarios:
        if s.taxonomic_level == "genus":
            p10, p50, p90 = 100.0, 200.0, 250.0
        elif s.taxonomic_level == "family":
            p10, p50, p90 = 100.0, 150.0, 200.0
        else:
            p10, p50, p90 = 5000.0, 6000.0, 7000.0
        records.append(
            PredictionRecord(
                scenario_id=s.id,
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
    df = build_frame(scenarios, records)
    cons = hierarchy_consistency(df)
    assert len(cons) == 1
    assert bool(cons.iloc[0]["strict_violation"]) is True


def test_hierarchy_coherent():
    scenarios = [
        _scenario(level="genus", ioc_count=45),
        _scenario(level="family", ioc_count=135),
        _scenario(level="order", ioc_count=6590),
    ]
    records = []
    for s in scenarios:
        t = float(s.ioc_count)
        records.append(
            PredictionRecord(
                scenario_id=s.id,
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
    df = build_frame(scenarios, records)
    cons = hierarchy_consistency(df)
    assert bool(cons.iloc[0]["strict_violation"]) is False
