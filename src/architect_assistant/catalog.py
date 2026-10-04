from __future__ import annotations

import json
from pathlib import Path

from pydantic import Field, model_validator

from architect_assistant.models import (
    ApiReference,
    Criterion,
    GuidanceLayer,
    LayerKind,
    Record,
    Rule,
    Specification,
)


class StandardSelection(Record):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    version: str = Field(min_length=1)


class RulePack(Record):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    version: str = Field(min_length=1)
    description: str = Field(min_length=1)
    requires: tuple[str, ...] = ()
    rules: tuple[Rule, ...] = Field(min_length=1)
    criteria: tuple[Criterion, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_rules(self) -> RulePack:
        Specification(
            project="catalog-validation",
            version=self.version,
            layers=(
                GuidanceLayer(
                    id=f"standard-{self.id}",
                    version=self.version,
                    kind=LayerKind.BASELINE,
                    status="approved",
                    rules=self.rules,
                ),
            ),
            criteria=self.criteria,
        )
        return self


class ProjectProfile(Record):
    project: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1)
    standards: tuple[StandardSelection, ...] = Field(min_length=1)
    layers: tuple[GuidanceLayer, ...] = ()
    criteria: tuple[Criterion, ...] = ()
    references: tuple[ApiReference, ...] = ()

    @model_validator(mode="after")
    def validate_selections(self) -> ProjectProfile:
        ids = [selection.id for selection in self.standards]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate standard selections")
        if any(layer.kind == LayerKind.BASELINE for layer in self.layers):
            raise ValueError("Select reusable baseline packs through standards")
        return self


def compose_profile(profile: ProjectProfile, standards_directory: Path) -> Specification:
    """Resolve explicit version-pinned adoptions; never silently load a newer policy version."""
    layers = list(profile.layers)
    criteria = list(profile.criteria)
    local_rule_ids = {rule.id for layer in profile.layers for rule in layer.rules}
    locally_covered = {rule_id for criterion in profile.criteria for rule_id in criterion.rule_ids}
    missing_criteria = local_rule_ids - locally_covered
    if missing_criteria:
        raise ValueError(
            "Local rules need explicit evaluation criteria: " + ", ".join(sorted(missing_criteria))
        )
    selected_ids = {selection.id for selection in profile.standards}
    for selection in sorted(profile.standards, key=lambda selection: selection.id):
        path = standards_directory / f"{selection.id}.json"
        pack = RulePack.model_validate_json(path.read_text(encoding="utf-8-sig"))
        if pack.id != selection.id or pack.version != selection.version:
            raise ValueError(
                f"Standard {selection.id}@{selection.version} does not match catalog "
                f"{pack.id}@{pack.version}; review the change before adopting it"
            )
        missing = set(pack.requires) - selected_ids
        if missing:
            raise ValueError(f"Standard {pack.id} also requires: {', '.join(sorted(missing))}")
        layers.append(
            GuidanceLayer(
                id=f"standard-{pack.id}",
                version=pack.version,
                kind=LayerKind.BASELINE,
                status="approved",
                rules=pack.rules,
            )
        )
        criteria.extend(pack.criteria)
    criteria.append(
        Criterion(
            id="CHECK_COMPOSED_CONSISTENCY",
            area="cross-rule consistency",
            rule_ids=tuple(sorted(rule.id for layer in layers for rule in layer.rules)),
            rubric=(
                "Assess composed guidance across adopted baseline, project and enterprise rules. "
                "Pass only when the sections preserve applicable source obligations and exceptions "
                "without contradictions, invented permissions or unsupported requirements. "
                "Cite a short exact excerpt from every section. Documentation is not permission."
            ),
        )
    )
    return Specification(
        project=profile.project,
        version=profile.version,
        layers=tuple(sorted(layers, key=lambda layer: layer.id)),
        criteria=tuple(sorted(criteria, key=lambda criterion: criterion.id)),
        references=profile.references,
    )


def load_specification(path: Path, standards_directory: Path) -> Specification:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(data, dict) and "standards" in data:
        return compose_profile(ProjectProfile.model_validate(data), standards_directory)
    return Specification.model_validate(data)
