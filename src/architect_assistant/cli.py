from __future__ import annotations

import argparse
import sys
from pathlib import Path

from langchain.chat_models import init_chat_model

from architect_assistant.backends import DemoBackend, LangChainBackend
from architect_assistant.catalog import (
    ProjectProfile,
    RulePack,
    StandardSelection,
    compose_profile,
    load_specification,
)
from architect_assistant.models import RunResult
from architect_assistant.rendering import render_instructions
from architect_assistant.workflow import Limits, run_workflow


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "init":
        return initialize_profile(argv[1:])
    parser = argparse.ArgumentParser(
        description="Build and evaluate draft developer instructions",
        epilog=(
            "Create a profile: architect-assistant init guidance/projects/my-project.json "
            "--project my-project --standards core backend python"
        ),
    )
    parser.add_argument(
        "specification", type=Path, help="Project profile or composed specification"
    )
    parser.add_argument(
        "--standards-directory",
        type=Path,
        default=Path("standards"),
        help="Reusable catalog directory (default: standards, relative to the current directory)",
    )
    parser.add_argument(
        "--output", type=Path, required=True, help="New directory for run artifacts"
    )
    parser.add_argument("--backend", choices=("demo", "model"), default="demo")
    parser.add_argument("--builder-model", help="LangChain provider:model identifier")
    parser.add_argument(
        "--evaluator-model", help="Independently selected provider:model identifier"
    )
    parser.add_argument("--demo-omit-rule", help="Demonstrate repair of a weak section (demo only)")
    parser.add_argument("--max-repairs", type=int, default=2)
    parser.add_argument("--max-operations", type=int, default=100)
    parser.add_argument("--max-seconds", type=float, default=120)
    parser.add_argument(
        "--previous-run", type=Path, help="Reuse unchanged sections from this run.json"
    )
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("Output directory already exists; choose a new one to preserve run history")
    if args.backend == "model" and (not args.builder_model or not args.evaluator_model):
        parser.error("Model mode requires both --builder-model and --evaluator-model")
    if args.backend == "model" and args.demo_omit_rule:
        parser.error("--demo-omit-rule applies only to the demo backend")
    try:
        specification = load_specification(args.specification, args.standards_directory)
        limits = Limits(
            max_repairs=args.max_repairs,
            max_operations=args.max_operations,
            max_seconds=args.max_seconds,
        )
        previous = (
            RunResult.model_validate_json(args.previous_run.read_text(encoding="utf-8-sig"))
            if args.previous_run
            else None
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    if args.demo_omit_rule and args.demo_omit_rule not in {r.id for r in specification.rules}:
        parser.error("Unknown --demo-omit-rule")
    if args.backend == "demo":
        backend = DemoBackend(args.demo_omit_rule)
        print("DEMO: fixture checks only; this does not certify instruction quality.")
    else:
        backend = LangChainBackend(
            builder_factory=lambda: init_chat_model(
                args.builder_model,
                timeout=min(30, limits.max_seconds),
                max_retries=0,
                max_tokens=2000,
            ),
            evaluator_factory=lambda: init_chat_model(
                args.evaluator_model,
                timeout=min(30, limits.max_seconds),
                max_retries=0,
                max_tokens=2000,
            ),
        )
        backend.name = f"langchain (builder={args.builder_model}, evaluator={args.evaluator_model})"
    try:
        result = run_workflow(specification, backend, limits, previous=previous)
    except ValueError as exc:
        parser.error(str(exc))
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "run.json").write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
    for attempt in result.attempts:
        (args.output / f"candidate-{attempt.candidate.revision}.md").write_text(
            render_instructions(specification, attempt.candidate),
            encoding="utf-8",
        )
        print(f"Candidate {attempt.candidate.revision}:")
        for evaluation in attempt.evaluations:
            print(f"  {evaluation.criterion_id}: {evaluation.judgement.verdict}")
    print(f"Result: {result.status}; operations: {result.operations}; artifacts: {args.output}")
    if result.error:
        print(result.error)
    return 0 if result.status == "evaluated" else 1


def initialize_profile(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Create an architect's project guidance profile")
    parser.add_argument("output", type=Path, help="New project profile JSON file")
    parser.add_argument("--project", required=True)
    parser.add_argument("--standards", nargs="+", default=["core"], help="Pack IDs to adopt")
    parser.add_argument("--standards-directory", type=Path, default=Path("standards"))
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("Profile already exists; edit it or choose a new path")
    try:
        selections = []
        for pack_id in args.standards:
            # Validate the identifier before turning it into a filesystem path.
            selection = StandardSelection(id=pack_id, version="pending")
            pack = RulePack.model_validate_json(
                (args.standards_directory / f"{selection.id}.json").read_text(encoding="utf-8-sig")
            )
            selections.append(StandardSelection(id=selection.id, version=pack.version))
        profile = ProjectProfile(project=args.project, version="0.1.0", standards=tuple(selections))
        compose_profile(profile, args.standards_directory)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation also protects against another process creating the file after the check.
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(profile.model_dump_json(indent=2) + "\n")
    print(f"Created project profile: {args.output}")
    print("Selected versions: " + ", ".join(f"{s.id}@{s.version}" for s in selections))
    print("Review the adopted rules, then add project/enterprise layers and their criteria.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
