# Architect Assistant

An agentic application that helps architects keep an overview of their applications and turn architectural decisions into guidance and checks for AI-assisted development.

As AI tools produce more code, architects need ways to keep that code aligned with business requirements, technical constraints, and maintainable designs. This project explores how an assistant can support that work through a shared knowledge base and explicit engineering controls.

The project is also a portfolio demonstration of building agent applications with clear responsibilities, controlled tool access, traceable outputs, and measurable quality.

## Intended capabilities

- Maintain decision records, target architectures, business requirements, and technical requirements for multiple applications.
- Connect decisions and requirements to the applications and components they affect.
- Generate versioned instructions for developers' AI coding tools from approved architectural knowledge.
- Review proposed code changes against relevant decisions and engineering rules, with evidence for each finding.
- Give architects an overview of missing decisions, outdated guidance, and unresolved architectural concerns.

## First working slice

A Python CLI uses LangGraph and LangChain to build developer instructions from a reusable standards catalog and architect-owned project/enterprise guidance. It evaluates each criterion with fresh, relevant context, repairs only affected sections, and repeats the full evaluation within configured limits. Updates can reuse unchanged sections.

Inputs and criteria remain outside builders' control. Outputs are Markdown drafts and JSON run records containing source snapshots, candidate hashes, and per-criterion findings. Instructions guide coding tools; deterministic checks and access controls enforce rules.

## Run locally

Requires Python 3.11 or newer. Create a virtual environment, then install the project and development tools using the checked-in dependency constraints:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c requirements.lock -e ".[dev]"
.\.venv\Scripts\python.exe -m architect_assistant guidance/projects/document-generation.json --output .artifacts/first-run --demo-omit-rule DOC_CONFIGURATION --max-operations 200
```

If Windows redirects `python` to the Store, use your installed Python executable for the first command. On macOS/Linux, use `.venv/bin/python` for the remaining commands.

The demo intentionally generates a weak section, shows its failed criteria, repairs it, and evaluates again. It requires no API keys. **The demo evaluator checks source copying; its passes do not certify semantic quality or coding-tool behavior.**

Inspect `candidate-1.md`, `candidate-2.md`, and `run.json` in the output directory. Each run requires a new directory to preserve its artifacts. A successful CLI exit means the configured evaluations passed; the candidate remains a draft.

## Create your project's guidance

Architects create a project profile that selects versioned rule packs and holds their own concerns. There is no need to copy the demonstration's baseline rules:

```powershell
.\.venv\Scripts\python.exe -m architect_assistant init guidance/projects/my-application.json --project my-application --standards core backend python
.\.venv\Scripts\python.exe -m architect_assistant guidance/projects/my-application.json --output .artifacts/my-application --max-operations 200
```

Run commands from the repository root, or pass `--standards-directory` with the catalog location. Use `core frontend typescript` for a TypeScript UI, for example. The catalog contains **65 rules** across core, backend, frontend, Python, TypeScript, C#, and Java packs. Optional packs require `core`; dependencies are never adopted silently.

- [Standards catalog and sources](standards/README.md): shared rules, rationale, evaluation criteria, and suggested independent checks.
- [Architect authoring guide](guidance/README.md): selecting packs and writing project or enterprise concerns.
- [Document-generation profile](guidance/projects/document-generation.json): adopts core, backend, and Python, adding the configuration-driven document concern and a fictional integration policy.
- `examples/document-generation.json`: the original small, self-contained repair demonstration, retained for compatibility and tests.

Review the packs before adoption. Profiles pin their versions, and a catalog version mismatch requires an explicit profile update. Mandatory rules and advisory practices are distinct; conditional rules apply when the corresponding capability exists. The local adoption and approval fields remain trusted author input rather than authenticated approval decisions.

After changing guidance or integration references, build against a prior evaluated run:

```powershell
.\.venv\Scripts\python.exe -m architect_assistant guidance/projects/document-generation.json --output .artifacts/updated-run --previous-run .artifacts/first-run/run.json --max-operations 200
```

Only changed rules or rules with changed documentation references are rebuilt. Every criterion is evaluated again, including consistency across the full candidate.

## Use models

Install the LangChain integration packages for your selected providers and configure their credentials through environment variables. For example, the [Anthropic integration](https://docs.langchain.com/oss/python/integrations/chat/anthropic) uses `langchain-anthropic` and `ANTHROPIC_API_KEY`. Provider packages are optional and are not included in the demo dependency snapshot.

```powershell
.\.venv\Scripts\python.exe -m architect_assistant guidance/projects/document-generation.json --output .artifacts/model-run --backend model --builder-model "provider:builder-model-id" --evaluator-model "provider:evaluator-model-id" --max-operations 200
```

Replace the model identifiers with supported models for your provider. Builder and evaluator models are selected independently. No paid model calls were used to validate this initial implementation; judge calibration and actual developer-tool behavior tests remain next steps.

More adopted rules mean more builder/evaluator calls. Choose applicable packs and deliberate budgets. A large catalog is not intended to be injected into every task; each criterion receives only its applicable rules and sections, while composed consistency receives the full adopted set.

## Development checks

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check src tests
.\.venv\Scripts\ruff.exe format --check src tests
```

`requirements.lock` records exact versions from the validated development environment. It is a pip constraints snapshot, without package hashes; it is not a provider or platform guarantee. CI runs lint and offline control tests without model credentials.

- [Product scope](docs/product-scope.md)
- [Architecture and current limits](docs/architecture.md)
- [Roadmap](docs/roadmap.md)
