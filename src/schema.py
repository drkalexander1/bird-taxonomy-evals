"""Pydantic models for taxonomy scenarios and model predictions."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, confloat, model_validator

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
SCENARIOS_PATH = DATA_DIR / "scenarios.yaml"
REFERENCE_COUNTS_PATH = DATA_DIR / "taxonomy_reference.csv"
PROMPT_PATH = ROOT / "prompts" / "taxonomy.txt"

TaxonomicLevel = Literal["genus", "family", "order"]
Familiarity = Literal["well_known", "obscure"]
QUANTILE_LEVELS = (0.1, 0.5, 0.9)
IOC_VERSION = "15.2"


class ScenarioCell(BaseModel):
    """One eval cell: a focal genus within its family (3 separate level prompts)."""

    genus: str
    family: str
    order: str
    familiarity: Familiarity
    ioc_genus: int = Field(ge=0)
    ioc_family: int = Field(gt=0)
    ioc_order: int = Field(gt=0)
    notes: str = ""

    @model_validator(mode="after")
    def ordered_ioc_counts(self) -> ScenarioCell:
        if not (self.ioc_genus <= self.ioc_family <= self.ioc_order):
            raise ValueError(
                f"IOC counts must satisfy genus <= family <= order for {self.genus}/{self.family}"
            )
        return self

    @property
    def cell_id(self) -> str:
        return _slug(f"{self.genus}_{self.family}")

    def ioc_count_for_level(self, level: TaxonomicLevel) -> int:
        return {"genus": self.ioc_genus, "family": self.ioc_family, "order": self.ioc_order}[level]


class Scenario(BaseModel):
    """One prompt instance: a single taxonomic level within a cell."""

    id: str
    cell_id: str
    taxonomic_level: TaxonomicLevel
    genus: str
    family: str
    order: str
    familiarity: Familiarity
    ioc_count: int = Field(ge=0)
    ioc_genus: int = Field(ge=0)
    ioc_family: int = Field(gt=0)
    ioc_order: int = Field(gt=0)
    notes: str = ""

    @property
    def taxonomic_unit(self) -> str:
        """Explicit rank + Latin name, e.g. 'the genus Corvus'."""
        latin = {"genus": self.genus, "family": self.family, "order": self.order}[
            self.taxonomic_level
        ]
        return f"the {self.taxonomic_level} {latin}"


REASONING_MAX_LENGTH = 400


class Prediction(BaseModel):
    p10: confloat(ge=0)
    p50: confloat(ge=0)
    p90: confloat(gt=0)
    confidence: confloat(ge=0, le=1)
    reasoning: str = Field(max_length=REASONING_MAX_LENGTH)

    @model_validator(mode="after")
    def ordered_quantiles(self) -> Prediction:
        if not (self.p10 <= self.p50 <= self.p90):
            raise ValueError("predicted quantiles must satisfy p10 <= p50 <= p90")
        return self


def _strict_json_schema(schema: dict) -> dict:
    out = dict(schema)
    if out.get("type") == "object":
        out["additionalProperties"] = False
    if "properties" in out:
        out["properties"] = {k: _strict_json_schema(v) for k, v in out["properties"].items()}
    if "items" in out:
        out["items"] = _strict_json_schema(out["items"])
    for key in ("anyOf", "oneOf", "allOf"):
        if key in out:
            out[key] = [_strict_json_schema(s) for s in out[key]]
    if "$defs" in out:
        out["$defs"] = {k: _strict_json_schema(v) for k, v in out["$defs"].items()}
    return out


def prediction_json_schema() -> dict:
    return _strict_json_schema(Prediction.model_json_schema())


def parse_prediction(data: dict) -> Prediction:
    normalized = dict(data)
    reasoning = normalized.get("reasoning")
    if isinstance(reasoning, str) and len(reasoning) > REASONING_MAX_LENGTH:
        normalized["reasoning"] = reasoning[:REASONING_MAX_LENGTH]
    return Prediction.model_validate(normalized)


class PredictionRecord(BaseModel):
    scenario_id: str
    model: str
    provider: str
    prediction: Prediction
    latency_ms: float | None = None
    raw_response: str | None = None


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def expand_cell(cell: ScenarioCell) -> list[Scenario]:
    scenarios: list[Scenario] = []
    for level in ("genus", "family", "order"):
        scenario_id = f"{cell.cell_id}_{level}"
        scenarios.append(
            Scenario(
                id=scenario_id,
                cell_id=cell.cell_id,
                taxonomic_level=level,  # type: ignore[arg-type]
                genus=cell.genus,
                family=cell.family,
                order=cell.order,
                familiarity=cell.familiarity,
                ioc_count=cell.ioc_count_for_level(level),  # type: ignore[arg-type]
                ioc_genus=cell.ioc_genus,
                ioc_family=cell.ioc_family,
                ioc_order=cell.ioc_order,
                notes=cell.notes,
            )
        )
    return scenarios


def load_scenario_cells(path: Path | None = None) -> list[ScenarioCell]:
    path = path or SCENARIOS_PATH
    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict) or "cells" not in raw:
        raise ValueError(f"Expected top-level 'cells' list in {path}")
    cells = raw["cells"]
    if not isinstance(cells, list):
        raise ValueError(f"Expected list at cells in {path}")
    return [ScenarioCell.model_validate(item) for item in cells]


def load_scenarios(path: Path | None = None) -> list[Scenario]:
    expanded: list[Scenario] = []
    for cell in load_scenario_cells(path):
        expanded.extend(expand_cell(cell))
    return expanded


def load_prompt_template(path: Path | None = None) -> str:
    path = path or PROMPT_PATH
    return path.read_text(encoding="utf-8")


def build_prompt(scenario: Scenario, path: Path | None = None) -> str:
    template = load_prompt_template(path)
    return template.format(taxonomic_unit=scenario.taxonomic_unit)


def load_reference_manifest(path: Path | None = None) -> dict | None:
    path = path or DATA_DIR / "ioc_manifest.json"
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as f:
        return json.load(f)
