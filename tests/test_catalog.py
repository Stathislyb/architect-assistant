from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from architect_assistant.backends import DemoBackend
from architect_assistant.catalog import (
    ProjectProfile,
    RulePack,
    StandardSelection,
    compose_profile,
    load_specification,
)
from architect_assistant.cli import main
from architect_assistant.models import RunResult, Specification, digest
from architect_assistant.rendering import render_instructions
from architect_assistant.workflow import run_workflow

ROOT = Path(__file__).parents[1]
STANDARDS = ROOT / "standards"
PACKS = ["core", "backend", "frontend", "python", "typescript", "csharp", "java"]


def profile(*ids):
    return ProjectProfile(
        project="test-project",
        version="0.1.0",
        standards=tuple(StandardSelection(id=pack_id, version="0.1.0") for pack_id in ids),
    )


@pytest.mark.parametrize("pack_id", PACKS)
def test_catalog_content_has_provenance_and_evaluation_coverage(pack_id):
    pack = RulePack.model_validate_json((STANDARDS / f"{pack_id}.json").read_text())
    assert pack.id == pack_id
    assert {rule.id for rule in pack.rules} == {
        rule_id for criterion in pack.criteria for rule_id in criterion.rule_ids
    }
    for rule in pack.rules:
        assert rule.source.startswith("https://")
        assert rule.category == pack_id
        assert rule.verification and all(check.strip() for check in rule.verification)
        assert rule.guidance.startswith(rule.strength.upper())


def test_all_packs_compose_without_duplicate_rules_or_criteria():
    specification = compose_profile(profile(*PACKS), STANDARDS)
    assert len(specification.rules) == 65
    assert len(specification.criteria) == 66
    consistency = next(c for c in specification.criteria if c.id == "CHECK_COMPOSED_CONSISTENCY")
    assert set(consistency.rule_ids) == {r.id for r in specification.rules}


def test_selection_excludes_unadopted_languages_and_roles():
    specification = compose_profile(profile("core", "frontend", "typescript"), STANDARDS)
    assert {rule.category for rule in specification.rules} == {"core", "frontend", "typescript"}
    assert len(specification.rules) == 35


def test_pack_version_change_requires_explicit_adoption(tmp_path):
    core = json.loads((STANDARDS / "core.json").read_text())
    core["version"] = "0.2.0"
    (tmp_path / "core.json").write_text(json.dumps(core))
    with pytest.raises(ValueError, match="review the change"):
        compose_profile(profile("core"), tmp_path)


def test_required_baseline_is_not_silently_adopted():
    with pytest.raises(ValueError, match="requires: core"):
        compose_profile(profile("backend"), STANDARDS)


@pytest.mark.parametrize("pack_id", ["../core", "../../secrets", "core/../backend"])
def test_selection_cannot_escape_catalog_directory(pack_id):
    with pytest.raises(ValidationError):
        profile(pack_id)


def test_unknown_and_duplicate_selections_are_rejected():
    with pytest.raises(FileNotFoundError):
        compose_profile(profile("missing"), STANDARDS)
    with pytest.raises(ValidationError, match="Duplicate standard"):
        profile("core", "core")


def test_colliding_project_rule_cannot_override_baseline():
    data = json.loads((ROOT / "guidance/projects/document-generation.json").read_text())
    data["layers"][0]["rules"][0]["id"] = "CORE_DRY"
    for criterion in data["criteria"]:
        criterion["rule_ids"] = [
            "CORE_DRY" if rule_id == "DOC_CONFIGURATION" else rule_id
            for rule_id in criterion["rule_ids"]
        ]
    with pytest.raises(ValidationError, match="Duplicate rule"):
        compose_profile(ProjectProfile.model_validate(data), STANDARDS)


def test_composed_consistency_does_not_replace_local_rule_criteria():
    data = json.loads((ROOT / "guidance/projects/document-generation.json").read_text())
    data["criteria"] = []
    with pytest.raises(ValueError, match="Local rules need explicit evaluation criteria"):
        compose_profile(ProjectProfile.model_validate(data), STANDARDS)


def test_expanded_profile_runs_targeted_repair_through_cli(tmp_path):
    output = tmp_path / "run"
    assert (
        main(
            [
                str(ROOT / "guidance/projects/document-generation.json"),
                "--standards-directory",
                str(STANDARDS),
                "--output",
                str(output),
                "--demo-omit-rule",
                "DOC_CONFIGURATION",
                "--max-operations",
                "200",
            ]
        )
        == 0
    )
    result = RunResult.model_validate_json((output / "run.json").read_text())
    assert len(result.specification.rules) == 40
    assert len(result.attempts) == 2
    old, new = result.attempts
    changed = [
        a.rule_id
        for a, b in zip(old.candidate.sections, new.candidate.sections, strict=True)
        if a != b
    ]
    assert changed == ["DOC_CONFIGURATION"]
    assert "not executed by this builder" in (output / "candidate-2.md").read_text()


def test_init_creates_profile_without_copying_rules_and_preserves_existing_file(tmp_path):
    path = tmp_path / "my-project.json"
    args = [
        "init",
        str(path),
        "--project",
        "my-project",
        "--standards",
        "core",
        "python",
        "--standards-directory",
        str(STANDARDS),
    ]
    assert main(args) == 0
    data = json.loads(path.read_text())
    assert data["layers"] == []
    assert [selection["id"] for selection in data["standards"]] == ["core", "python"]
    assert len(load_specification(path, STANDARDS).rules) == 26
    original = path.read_bytes()
    with pytest.raises(SystemExit):
        main(args)
    assert path.read_bytes() == original


def test_pre_catalog_hashes_remain_valid(specification):
    data = specification.model_dump(mode="json")
    for layer in data["layers"]:
        for rule in layer["rules"]:
            rule.pop("category")
            rule.pop("verification")
    old_hash = hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    restored = Specification.model_validate(data)
    assert digest(restored) == old_hash
    candidate = run_workflow(restored, DemoBackend()).attempts[0].candidate
    assert candidate.specification_hash == old_hash
    assert render_instructions(restored, candidate)
