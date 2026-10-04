from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypedDict, TypeVar

from langgraph.graph import END, START, StateGraph
from pydantic import Field

from architect_assistant.backends import Backend
from architect_assistant.models import (
    Attempt,
    Candidate,
    Evaluation,
    EvaluationRequest,
    InstructionSection,
    Judgement,
    Record,
    RunResult,
    Specification,
    Verdict,
    digest,
)
from architect_assistant.rendering import render_instructions


class Limits(Record):
    max_repairs: int = Field(default=2, ge=0, le=10)
    max_operations: int = Field(default=100, ge=1, le=1000)
    max_seconds: float = Field(default=120, gt=0, le=3600)


class BudgetExceeded(RuntimeError):
    pass


T = TypeVar("T")


class Budget:
    def __init__(self, limits: Limits) -> None:
        self.limits = limits
        self.deadline = time.monotonic() + limits.max_seconds
        self.operations = 0

    def call(self, operation: Callable[[], T]) -> T:
        if self.operations >= self.limits.max_operations or time.monotonic() >= self.deadline:
            raise BudgetExceeded("Run budget exhausted")
        self.operations += 1
        result = operation()
        if time.monotonic() >= self.deadline:
            raise BudgetExceeded("Run time budget exhausted")
        return result


class State(TypedDict, total=False):
    candidate: Candidate
    attempts: tuple[Attempt, ...]
    status: str
    error: str | None


def validate_judgement(request: EvaluationRequest, judgement: Judgement) -> Judgement:
    sections = {section.rule_id: section.text for section in request.candidate.sections}
    evidence_valid = bool(judgement.evidence) and all(
        evidence.rule_id in request.criterion.rule_ids
        and evidence.quote in sections.get(evidence.rule_id, "")
        for evidence in judgement.evidence
    )
    if judgement.verdict == Verdict.PASS:
        evidence_valid = evidence_valid and {
            evidence.rule_id for evidence in judgement.evidence
        } == set(request.criterion.rule_ids)
    feedback_valid = (
        bool(judgement.feedback)
        and bool(judgement.repair_rule_ids)
        and (set(judgement.repair_rule_ids) <= set(request.criterion.rule_ids))
    )
    if judgement.verdict != Verdict.UNRESOLVED and (
        not evidence_valid or (judgement.verdict == Verdict.FAIL and not feedback_valid)
    ):
        return Judgement(
            verdict=Verdict.UNRESOLVED,
            reason="Evaluator returned invalid evidence or non-actionable failure feedback.",
        )
    return judgement


def run_workflow(
    specification: Specification,
    backend: Backend,
    limits: Limits | None = None,
    previous: RunResult | None = None,
) -> RunResult:
    """Bounded graph with immutable candidates and fresh evaluator inputs at every revision."""
    limits = limits or Limits()
    budget = Budget(limits)
    specification_hash = digest(specification)
    reusable: dict[str, InstructionSection] = {}
    revision = 1
    if previous is not None:
        if previous.specification.project != specification.project:
            raise ValueError("Previous run belongs to a different project")
        if previous.status != "evaluated" or not previous.attempts:
            raise ValueError("Only an evaluated prior candidate can be used for an update")
        prior_candidate = previous.attempts[-1].candidate
        render_instructions(previous.specification, prior_candidate)
        revision = prior_candidate.revision + 1
        old_rules = {rule.id: rule for rule in previous.specification.rules}
        old_sections = {section.rule_id: section for section in prior_candidate.sections}
        for rule in specification.rules:
            old_refs = {
                ref for ref in previous.specification.references if ref.permitted_by == rule.id
            }
            new_refs = {ref for ref in specification.references if ref.permitted_by == rule.id}
            if old_rules.get(rule.id) == rule and old_refs == new_refs:
                reusable[rule.id] = old_sections[rule.id]

    def candidate_from(sections: tuple[InstructionSection, ...], revision: int) -> Candidate:
        candidate = Candidate(
            revision=revision,
            specification_hash=specification_hash,
            sections=tuple(sorted(sections, key=lambda section: section.rule_id)),
        )
        render_instructions(specification, candidate)  # Validate coverage before evaluation.
        return candidate

    def references_for(rule_id: str):
        return tuple(ref for ref in specification.references if ref.permitted_by == rule_id)

    def build(state: State) -> State:
        try:
            sections = []
            for rule in specification.rules:
                if rule.id in reusable:
                    sections.append(reusable[rule.id])
                    continue
                section = budget.call(
                    lambda rule=rule: backend.build(rule, references_for(rule.id))
                )
                if section.rule_id != rule.id:
                    raise ValueError("Builder changed rule ownership")
                sections.append(section)
            return {"candidate": candidate_from(tuple(sections), revision), "attempts": ()}
        except BudgetExceeded as exc:
            return {"status": "needs_attention", "error": str(exc)}
        except Exception as exc:
            # Provider exceptions may include credentials or submitted context. Do not persist them.
            return {"status": "error", "error": f"Build failed ({type(exc).__name__})"}

    def evaluate(state: State) -> State:
        candidate = state["candidate"]
        evaluations: list[Evaluation] = []
        exhausted = False
        for criterion in specification.criteria:
            request = EvaluationRequest(
                specification=specification,
                candidate=candidate,
                criterion=criterion,
            )
            try:
                if exhausted:
                    raise BudgetExceeded("Run budget exhausted")
                judgement = budget.call(lambda request=request: backend.evaluate(request))
                judgement = validate_judgement(request, judgement)
            except BudgetExceeded:
                exhausted = True
                judgement = Judgement(verdict=Verdict.UNRESOLVED, reason="Run budget exhausted")
            except Exception as exc:
                judgement = Judgement(
                    verdict=Verdict.UNRESOLVED,
                    reason=f"Evaluation failed ({type(exc).__name__})",
                )
            evaluations.append(
                Evaluation(
                    criterion_id=criterion.id,
                    area=criterion.area,
                    candidate_hash=digest(candidate),
                    judgement=judgement,
                )
            )
        attempt = Attempt(
            candidate=candidate,
            candidate_hash=digest(candidate),
            evaluations=tuple(evaluations),
        )
        attempts = (*state.get("attempts", ()), attempt)
        if all(result.judgement.verdict == Verdict.PASS for result in evaluations):
            status = "evaluated"
        elif any(result.judgement.verdict == Verdict.UNRESOLVED for result in evaluations):
            status = "needs_attention"
        elif len(attempts) > limits.max_repairs:
            status = "needs_attention"
        else:
            status = "repair"
        return {"attempts": attempts, "status": status}

    def repair(state: State) -> State:
        candidate = state["candidate"]
        failed = tuple(
            evaluation
            for evaluation in state["attempts"][-1].evaluations
            if evaluation.judgement.verdict == Verdict.FAIL
        )
        targets = {
            rule_id for evaluation in failed for rule_id in evaluation.judgement.repair_rule_ids
        }
        try:
            sections = []
            for section in candidate.sections:
                if section.rule_id not in targets:
                    sections.append(section)
                    continue
                findings = tuple(
                    finding
                    for finding in failed
                    if section.rule_id in finding.judgement.repair_rule_ids
                )
                replacement = budget.call(
                    lambda section=section, findings=findings: backend.repair(
                        specification.rule(section.rule_id),
                        section,
                        findings,
                        references_for(section.rule_id),
                    )
                )
                if replacement.rule_id != section.rule_id:
                    raise ValueError("Repair changed rule ownership")
                sections.append(replacement)
            updated = candidate_from(tuple(sections), candidate.revision + 1)
            if updated.sections == candidate.sections:
                return {"status": "needs_attention", "error": "Repair made no changes"}
            return {"candidate": updated, "status": "evaluate"}
        except BudgetExceeded as exc:
            return {"status": "needs_attention", "error": str(exc)}
        except Exception as exc:
            return {"status": "error", "error": f"Repair failed ({type(exc).__name__})"}

    graph = StateGraph(State)
    graph.add_node("build", build)
    graph.add_node("evaluate", evaluate)
    graph.add_node("repair", repair)
    graph.add_edge(START, "build")
    graph.add_conditional_edges("build", lambda state: END if state.get("status") else "evaluate")
    graph.add_conditional_edges(
        "evaluate",
        lambda state: "repair" if state["status"] == "repair" else END,
    )
    graph.add_conditional_edges(
        "repair",
        lambda state: "evaluate" if state["status"] == "evaluate" else END,
    )
    result = graph.compile().invoke({}, {"recursion_limit": 2 * limits.max_repairs + 5})
    return RunResult(
        specification=specification,
        status=result["status"],
        backend=backend.name,
        attempts=result.get("attempts", ()),
        operations=budget.operations,
        limits=limits.model_dump(),
        reused_rule_ids=tuple(sorted(reusable)),
        error=result.get("error"),
    )
