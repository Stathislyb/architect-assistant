# Architect-owned guidance

The standards catalog supplies the reusable baseline. A project profile selects exact pack versions and adds application or enterprise concerns. `examples/` is for demonstrations; it is not the main authoring location.

## Start a project

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m architect_assistant init guidance/projects/my-application.json --project my-application --standards core backend python
```

Select packs for the actual application. `core` is the common foundation; optional packs require it. Add both backend and frontend only when the profile covers both. Use `--standards-directory` for a catalog located elsewhere. [templates/project.json](templates/project.json) is the minimal profile shape; the initializer creates it without copying any baseline rules.

## Add project concerns

Write local rules under `layers` with `kind: project` and a matching `project` identifier. Give each a stable ID, source concern, rationale, strength, and approval status. Add criteria under `criteria`, linked through `rule_ids`, explaining what a faithful instruction must say. Draft layers cannot be built; approve them after review.

[projects/document-generation.json](projects/document-generation.json) shows the configuration-driven document concern: no document-identifier branches in the engine; supported new documents need configuration changes only; new rendering capabilities may require code. It adopts the catalog rather than duplicating its baseline.

Enterprise restrictions use an `enterprise` layer. Documentation references link through `permitted_by` to an actual integration rule. Documentation alone never grants permission. The document profile's enterprise policy and API reference remain fictional placeholders; replace them with real approved policy before organizational use.

## Build and update

```powershell
.\.venv\Scripts\python.exe -m architect_assistant guidance/projects/my-application.json --output .artifacts/my-first-run --max-operations 200
```

The CLI resolves packs, validates composition, and runs the existing build/evaluate/repair workflow. It saves the fully resolved sources in `run.json` alongside instruction drafts. Add `--previous-run` to reuse unaffected sections after edits. All criteria run again. Larger profiles need deliberately chosen call/time budgets.

Review pack amendments before changing the profile's pinned versions. To change a baseline recommendation, amend its shared pack or adopt a separately governed variant; do not reuse its ID in a local layer to override it. Declared conflicts require resolution before building, and the model consistency evaluator assesses other contradictions.

Generated instructions are still drafts. This local workflow does not guarantee that a coding tool always loads or follows them; target-specific export, independent behavior tests, and CI enforcement remain necessary work. Natural-language concern intake and an authoring UI are still planned; authoring currently uses JSON.
