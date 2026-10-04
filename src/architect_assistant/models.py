from __future__ import annotations

import hashlib
import json
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)


class LayerKind(StrEnum):
    BASELINE = "baseline"
    PROJECT = "project"
    ENTERPRISE = "enterprise"


class Rule(Record):
    id: str = Field(pattern=r"^[A-Z][A-Z0-9_-]*$")
    title: str = Field(min_length=1, max_length=200)
    guidance: str = Field(min_length=1, max_length=4000)
    rationale: str = Field(min_length=1, max_length=2000)
    source: str = Field(min_length=1, max_length=500)
    strength: str = Field(pattern=r"^(must|should)$")
    conflicts_with: tuple[str, ...] = ()
    category: str = Field(default="general", min_length=1)
    verification: tuple[str, ...] = ()


class GuidanceLayer(Record):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    version: str = Field(min_length=1)
    kind: LayerKind
    status: str = Field(pattern=r"^(draft|approved)$")
    project: str | None = None
    rules: tuple[Rule, ...] = Field(min_length=1)


class ApiReference(Record):
    id: str = Field(pattern=r"^[A-Z][A-Z0-9_-]*$")
    title: str = Field(min_length=1)
    url: str = Field(pattern=r"^https://")
    version: str = Field(min_length=1)
    permitted_by: str = Field(min_length=1)


class Criterion(Record):
    id: str = Field(pattern=r"^[A-Z][A-Z0-9_-]*$")
    area: str = Field(min_length=1)
    rule_ids: tuple[str, ...] = Field(min_length=1)
    rubric: str = Field(min_length=1, max_length=4000)


class Specification(Record):
    project: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1)
    layers: tuple[GuidanceLayer, ...] = Field(min_length=1)
    criteria: tuple[Criterion, ...] = Field(min_length=1)
    references: tuple[ApiReference, ...] = ()

    @model_validator(mode="after")
    def validate_composition(self) -> Specification:
        def unique(values: list[str], label: str) -> None:
            if len(values) != len(set(values)):
                raise ValueError(f"Duplicate {label} identifiers")

        unique([layer.id for layer in self.layers], "layer")
        unique([rule.id for rule in self.rules], "rule")
        unique([criterion.id for criterion in self.criteria], "criterion")
        unique([reference.id for reference in self.references], "reference")
        ids = {rule.id for rule in self.rules}
        for layer in self.layers:
            if layer.status != "approved":
                raise ValueError(f"Layer {layer.id} is not approved")
            if layer.kind == LayerKind.PROJECT and layer.project != self.project:
                raise ValueError(f"Layer {layer.id} belongs to a different project")
            if layer.project is not None and layer.project != self.project:
                raise ValueError(f"Layer {layer.id} is outside the requested project")
        for rule in self.rules:
            if rule.conflicts_with:
                raise ValueError(f"Resolve declared conflicts for {rule.id} before building")
        for criterion in self.criteria:
            if not set(criterion.rule_ids) <= ids:
                raise ValueError(f"Unknown rules in criterion {criterion.id}")
        covered = {rule_id for criterion in self.criteria for rule_id in criterion.rule_ids}
        if covered != ids:
            raise ValueError("Every rule needs at least one evaluation criterion")
        for reference in self.references:
            if reference.permitted_by not in ids:
                raise ValueError(f"Reference {reference.id} has no governing integration rule")
        return self

    @property
    def rules(self) -> tuple[Rule, ...]:
        # Stable rendering independent of JSON array order. No layer silently overrides another.
        return tuple(sorted((r for layer in self.layers for r in layer.rules), key=lambda r: r.id))

    def rule(self, rule_id: str) -> Rule:
        return next(rule for rule in self.rules if rule.id == rule_id)


class InstructionSection(Record):
    rule_id: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=6000)


class Candidate(Record):
    revision: int = Field(ge=1)
    specification_hash: str
    sections: tuple[InstructionSection, ...]


class Verdict(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNRESOLVED = "unresolved"


class Evidence(Record):
    rule_id: str
    quote: str = Field(min_length=1, max_length=6000)


class Judgement(Record):
    verdict: Verdict
    reason: str = Field(min_length=1, max_length=4000)
    evidence: tuple[Evidence, ...] = ()
    feedback: str = Field(default="", max_length=4000)
    repair_rule_ids: tuple[str, ...] = ()


class Evaluation(Record):
    criterion_id: str
    area: str
    candidate_hash: str
    judgement: Judgement


class EvaluationRequest(Record):
    """A fresh evaluation envelope: deliberately excludes history and builder claims."""

    specification: Specification
    candidate: Candidate
    criterion: Criterion


class Attempt(Record):
    candidate: Candidate
    candidate_hash: str
    evaluations: tuple[Evaluation, ...]


class RunResult(Record):
    specification: Specification
    status: str = Field(pattern=r"^(evaluated|needs_attention|error)$")
    backend: str
    attempts: tuple[Attempt, ...]
    operations: int
    limits: dict[str, int | float]
    workflow_version: str = "0.2.0"
    prompt_version: str = "0.2.0"
    reused_rule_ids: tuple[str, ...] = ()
    error: str | None = None


def digest(record: Record) -> str:
    def compatible_data(value):
        if isinstance(value, list):
            return [compatible_data(item) for item in value]
        if isinstance(value, dict):
            value = {key: compatible_data(item) for key, item in value.items()}
            if {"guidance", "rationale", "source"} <= value.keys():
                # Preserve hashes of pre-catalog records with absent optional rule metadata.
                if value.get("category") == "general":
                    value.pop("category")
                if value.get("verification") == []:
                    value.pop("verification")
            return value
        return value

    canonical = json.dumps(
        compatible_data(record.model_dump(mode="json")), sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
