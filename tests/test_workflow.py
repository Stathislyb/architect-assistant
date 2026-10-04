from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from architect_assistant.backends import DemoBackend, LangChainBackend
from architect_assistant.cli import main
from architect_assistant.models import (
    EvaluationRequest,
    Evidence,
    InstructionSection,
    Judgement,
    Specification,
    Verdict,
    digest,
)
from architect_assistant.rendering import render_instructions
from architect_assistant.workflow import Limits, run_workflow


class TrackingBackend(DemoBackend):
    def __init__(self, omit_rule=None):
        super().__init__(omit_rule)
        self.repairs = []
        self.requests = []

    def repair(self, rule, section, findings, references):
        self.repairs.append(rule.id)
        return super().repair(rule, section, findings, references)

    def evaluate(self, request):
        self.requests.append(request)
        return super().evaluate(request)


def test_targeted_repair_and_fresh_full_evaluation(specification):
    backend = TrackingBackend("DOC_CONFIGURATION")
    result = run_workflow(specification, backend)
    assert result.status == "evaluated"
    assert backend.repairs == ["DOC_CONFIGURATION"]
    assert len(result.attempts) == 2
    old, new = result.attempts
    assert old.candidate_hash != new.candidate_hash
    assert old.evaluations[-1].judgement.verdict == Verdict.FAIL
    assert old.evaluations[-2].judgement.verdict == Verdict.PASS
    assert old.evaluations[-3].judgement.verdict == Verdict.FAIL
    assert all(e.judgement.verdict == Verdict.PASS for e in new.evaluations)
    assert len(backend.requests) == 2 * len(specification.criteria)
    assert set(EvaluationRequest.model_fields) == {"specification", "candidate", "criterion"}
    for section in old.candidate.sections:
        if section.rule_id != "DOC_CONFIGURATION":
            assert section in new.candidate.sections
    assert old.candidate.specification_hash == digest(specification)


@pytest.mark.parametrize("mode", ["no_evidence", "fabricated_evidence", "exception"])
def test_evaluator_cannot_pass_without_valid_evidence(specification, mode):
    class InvalidJudge(DemoBackend):
        def evaluate(self, request):
            if mode == "exception":
                raise RuntimeError("secret-provider-token")
            return Judgement(
                verdict=Verdict.PASS,
                reason="Looks fixed",
                evidence=()
                if mode == "no_evidence"
                else (Evidence(rule_id="DOC_CONFIGURATION", quote="This quote does not exist"),),
            )

    result = run_workflow(specification, InvalidJudge())
    assert result.status == "needs_attention"
    assert all(e.judgement.verdict == Verdict.UNRESOLVED for e in result.attempts[0].evaluations)
    assert "secret-provider-token" not in result.model_dump_json()


def test_unchanged_candidate_does_not_pass_on_claim_of_repair(specification):
    class ClaimingBuilder(DemoBackend):
        def repair(self, rule, section, findings, references):
            return section

    result = run_workflow(specification, ClaimingBuilder("DOC_CONFIGURATION"))
    assert result.status == "needs_attention"
    assert result.error == "Repair made no changes"
    assert len(result.attempts) == 1


def test_nonconverging_repairs_stop_at_limit(specification):
    class Nonconverging(DemoBackend):
        def repair(self, rule, section, findings, references):
            return InstructionSection(rule_id=rule.id, text=section.text + " Still unresolved.")

    result = run_workflow(specification, Nonconverging("DOC_CONFIGURATION"), Limits(max_repairs=1))
    assert result.status == "needs_attention"
    assert len(result.attempts) == 2


def test_run_budget_covers_build_evaluation_and_repair(specification):
    result = run_workflow(specification, DemoBackend(), Limits(max_operations=7))
    assert result.operations == 7
    assert result.status == "needs_attention"
    assert result.attempts[0].evaluations[0].judgement.verdict == Verdict.PASS
    assert result.attempts[0].evaluations[1].judgement.verdict == Verdict.UNRESOLVED


def test_build_budget_exhaustion_is_visible(specification):
    result = run_workflow(specification, DemoBackend(), Limits(max_operations=1))
    assert result.status == "needs_attention"
    assert result.operations == 1
    assert not result.attempts


def test_builder_cannot_change_rule_ownership(specification):
    class WrongOwner(DemoBackend):
        def build(self, rule, references):
            return InstructionSection(rule_id="UNAPPROVED", text=rule.guidance)

    result = run_workflow(specification, WrongOwner())
    assert result.status == "error"
    assert not result.attempts


@pytest.mark.parametrize(
    "change",
    ["draft", "scope", "duplicate", "conflict", "reference", "criterion"],
)
def test_composition_rejects_invalid_sources(specification, change):
    data = specification.model_dump(mode="json")
    if change == "draft":
        data["layers"][0]["status"] = "draft"
    elif change == "scope":
        data["layers"][1]["project"] = "other-project"
    elif change == "duplicate":
        data["layers"][1]["rules"][0]["id"] = "BASE_DRY"
    elif change == "conflict":
        data["layers"][1]["rules"][0]["conflicts_with"] = ["BASE_DRY"]
    elif change == "reference":
        data["references"][0]["permitted_by"] = "UNKNOWN"
    elif change == "criterion":
        data["criteria"][0]["rule_ids"] = ["UNKNOWN"]
    with pytest.raises(ValidationError):
        Specification.model_validate(data)


def test_source_update_requires_new_candidate(specification):
    old_candidate = run_workflow(specification, DemoBackend()).attempts[-1].candidate
    data = specification.model_dump(mode="json")
    data["layers"][1]["version"] = "0.2.0"
    data["layers"][1]["rules"][0]["guidance"] += " Preserve configured locale."
    updated = Specification.model_validate(data)
    with pytest.raises(ValueError, match="different specification"):
        render_instructions(updated, old_candidate)
    new_candidate = run_workflow(updated, DemoBackend()).attempts[-1].candidate
    assert new_candidate.specification_hash != old_candidate.specification_hash


def test_deterministic_rendering_and_repeatable_demo(specification):
    first = run_workflow(specification, DemoBackend())
    second = run_workflow(specification, DemoBackend())
    assert first == second
    text = render_instructions(specification, first.attempts[0].candidate)
    assert "Status: draft" in text
    assert "Documentation does not grant integration permissions" in text


def test_model_evaluators_receive_new_context_without_builder_claims(specification):
    candidate = run_workflow(specification, DemoBackend()).attempts[0].candidate
    messages_seen = []
    factories = []

    class FakeStructuredModel:
        def with_structured_output(self, schema):
            assert schema is Judgement
            return self

        def invoke(self, messages):
            messages_seen.append(messages)
            return Judgement(verdict=Verdict.UNRESOLVED, reason="Test fixture")

    def evaluator_factory():
        model = FakeStructuredModel()
        factories.append(model)
        return model

    backend = LangChainBackend(lambda: None, evaluator_factory)
    request = EvaluationRequest(
        specification=specification,
        candidate=candidate,
        criterion=specification.criteria[0],
    )
    backend.evaluate(request)
    backend.evaluate(request)
    assert factories[0] is not factories[1]
    assert messages_seen[0] is not messages_seen[1]
    assert len(messages_seen[0]) == len(messages_seen[1]) == 2
    payload = json.loads(messages_seen[0][1].content)
    assert payload["criterion"] == request.criterion.model_dump(mode="json")
    assert len(payload["source_rules"]) == len(payload["sections"]) == 1
    assert payload["source_rules"][0]["id"] == request.criterion.rule_ids[0]
    assert payload["candidate_hash"] == digest(candidate)
    assert "history" not in payload


def test_cli_preserves_history_and_writes_drafts(tmp_path):
    from pathlib import Path

    spec = Path(__file__).parents[1] / "examples" / "document-generation.json"
    output = tmp_path / "run"
    assert main([str(spec), "--output", str(output), "--demo-omit-rule", "DOC_CONFIGURATION"]) == 0
    assert (output / "candidate-1.md").exists()
    assert (output / "candidate-2.md").exists()
    assert json.loads((output / "run.json").read_text())["backend"] == "demo-fixture"
    assert not (output / "AGENTS.md").exists()
    with pytest.raises(SystemExit):
        main([str(spec), "--output", str(output)])


def test_source_update_rebuilds_only_affected_section_but_rechecks_all(specification):
    previous = run_workflow(specification, DemoBackend())
    data = specification.model_dump(mode="json")
    data["layers"][1]["version"] = "0.2.0"
    data["layers"][1]["rules"][0]["guidance"] += " Preserve configured locale."
    updated = Specification.model_validate(data)

    class CountingBuilder(TrackingBackend):
        built = []

        def build(self, rule, references):
            self.built.append(rule.id)
            return super().build(rule, references)

    backend = CountingBuilder()
    result = run_workflow(updated, backend, previous=previous)
    assert result.status == "evaluated"
    assert backend.built == ["DOC_CONFIGURATION"]
    assert len(result.reused_rule_ids) == 5
    assert len(backend.requests) == len(updated.criteria)
    assert result.attempts[0].candidate.revision == 2


def test_reference_change_rebuilds_its_governing_rule(specification):
    previous = run_workflow(specification, DemoBackend())
    data = specification.model_dump(mode="json")
    data["references"][0]["version"] = "v2-demo"
    updated = Specification.model_validate(data)
    result = run_workflow(updated, DemoBackend(), previous=previous)
    assert "ENT_INTEGRATIONS" not in result.reused_rule_ids
    assert len(result.reused_rule_ids) == 5
    assert result.operations == 1 + len(updated.criteria)


def test_incremental_updates_have_their_own_repair_budget(specification):
    previous = run_workflow(specification, DemoBackend("DOC_CONFIGURATION"))
    data = specification.model_dump(mode="json")
    data["layers"][1]["rules"][0]["guidance"] += " Preserve configured locale."
    updated = Specification.model_validate(data)
    result = run_workflow(
        updated,
        DemoBackend("DOC_CONFIGURATION"),
        Limits(max_repairs=1),
        previous=previous,
    )
    assert result.status == "evaluated"
    assert [attempt.candidate.revision for attempt in result.attempts] == [3, 4]


def test_previous_run_cannot_cross_project_scope(specification):
    previous = run_workflow(specification, DemoBackend())
    data = specification.model_dump(mode="json")
    data["project"] = "other-project"
    data["layers"][1]["project"] = "other-project"
    updated = Specification.model_validate(data)
    with pytest.raises(ValueError, match="different project"):
        run_workflow(updated, DemoBackend(), previous=previous)


def test_cross_rule_pass_needs_evidence_for_every_rule(specification):
    class PartialJudge(DemoBackend):
        def evaluate(self, request):
            result = super().evaluate(request)
            return result.model_copy(update={"evidence": result.evidence[:1]})

    result = run_workflow(specification, PartialJudge())
    assert result.status == "needs_attention"
    assert result.attempts[0].evaluations[-1].judgement.verdict == Verdict.UNRESOLVED


def test_feedback_cannot_expand_repair_scope(specification):
    class OverreachingJudge(DemoBackend):
        def evaluate(self, request):
            result = super().evaluate(request)
            if result.verdict == Verdict.FAIL:
                return result.model_copy(update={"repair_rule_ids": ("UNAPPROVED",)})
            return result

    result = run_workflow(specification, OverreachingJudge("DOC_CONFIGURATION"))
    assert result.status == "needs_attention"
    assert len(result.attempts) == 1


def test_elapsed_time_exhaustion_is_not_a_pass(specification, monkeypatch):
    from architect_assistant import workflow

    clock = iter([0, 0, 2])
    monkeypatch.setattr(workflow.time, "monotonic", lambda: next(clock))
    result = run_workflow(specification, DemoBackend(), Limits(max_seconds=1))
    assert result.status == "needs_attention"
    assert result.operations == 1


def test_candidates_and_sources_are_immutable(specification):
    result = run_workflow(specification, DemoBackend())
    with pytest.raises(ValidationError):
        result.attempts[0].candidate.sections[0].text = "Weakened instruction"
    with pytest.raises(ValidationError):
        specification.layers[0].rules[0].guidance = "Weakened source"
