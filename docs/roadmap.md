# Roadmap

## Implemented first slice

Layered source specifications, a sourced catalog of 65 selectable development rules, architect project profiles and initialization, stable instruction rendering, LangGraph orchestration, separately configurable LangChain builders and evaluators, fresh scoped evaluations with evidence checks, bounded targeted repair, incremental updates, and local draft/run artifacts. An offline fixture demonstrates the workflow without model credentials.

## Next iterations

1. Build a small, architect-reviewed evaluation dataset, including conflicting guidance, malicious candidates, and misleading claims of compliance. Measure judge errors and generation variability on selected models.
2. Test exported instructions in isolated developer-tool scenarios. Start with adding a supported document configuration without engine changes. Keep acceptance scenarios separate from repair examples.
3. Add natural-language concern intake that proposes explicit rules and rubrics for architect review. Extend the researched catalog with framework packs and configured quality-tool mappings as needed.
4. Add revision-specific approval, target-specific exports, source change review, and rollback. An evaluated draft must not automatically become a release.
5. Add a workspace UI, persistent records, authorized multi-user/project access, and documentation retrieval. Introduce durable execution, concurrency, and cost controls as usage requires them.

Model selection, additional agents, and infrastructure follow evaluation results and demonstrated needs. The broader architecture knowledge base remains part of the product vision.
