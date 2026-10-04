# Development standards catalog

This is the reusable foundation for developer instructions. Architects select the packs relevant to an application; project and enterprise concerns live separately under `guidance/`. Research reviewed on 2026-10-04.

| Pack | Rules | Coverage |
| --- | ---: | --- |
| [Core](core.json) | 19 | Responsibility, dependency boundaries, DRY, simplicity, readable changes, tests, coverage, configuration, secrets, logs, dependencies and explicit failures. |
| [Backend](backend.json) | 12 | Authorization, input validation, queries, contracts, limits, secure transport, outbound access, retries, consistency, observability and migrations. |
| [Frontend](frontend.json) | 10 | Semantic HTML, keyboard/focus, forms, safe rendering, server trust boundaries, state, asynchronous feedback, performance, browser secrets and responsive layout. |
| [Python](python.json) | 7 | Conventions, types, mutable defaults, resource cleanup, exceptions, asynchronous work and subprocesses. |
| [TypeScript](typescript.json) | 6 | Strict checking, boundary validation, variants, type escape hatches, promises and mutation. |
| [C#](csharp.json) | 5 | Conventions/analyzers, nullability, asynchronous flow, disposal and comparison semantics. |
| [Java](java.json) | 6 | Resources, generics, collections, exceptions, time and concurrency. |

## How rules work

Every rule has an identifier, actionable guidance, rationale, source URL, strength, category, and suggested independent checks. Each has a separate instruction-evaluation criterion. Composition also adds a criterion for consistency across the adopted rules and local concerns.

These are our engineering synthesis of the linked resources, not verbatim source requirements or compliance certification. `must` means required after adoption. `should` preserves room for a justified engineering choice; its evaluator checks that the instruction expresses the recommendation faithfully. Conditional clauses remain essential: a CLI without a database does not need a migration framework.

Quality checks are suggestions for verification, not a promise that the assistant has run those tools. Coverage thresholds, method sizes, particular frameworks, microservices, test ratios, and telemetry vendors are not imposed universally. Set justified project targets explicitly.

Keep one authoritative definition for each rule. Do not copy baseline guidance into each project, silently override identifiers, or add every language pack to every application. Language/runtime features must match the application's supported versions. The Java pack uses Oracle's established tutorials for fundamentals; several target JDK 8, so project API choices need current JDK documentation.

## Maintenance

Change guidance and its evaluation criterion together, increment the pack version, and document the rationale in the change. Architects review amendments before updating their pinned profile versions. Runs preserve resolved rule snapshots and hashes, allowing unchanged instructions to be reused and changed instructions to be evaluated again. Version labels are maintained through repository review; they are not an immutable catalog service.

The current foundation covers common web/server development and four languages. Framework, mobile, embedded, data-engineering and agent-runtime packs can be added when needed. Source URLs may evolve; updates require fresh review rather than automatic web ingestion.

## Primary references

Rule records link to the specific supporting pages. The source families include [Google code review](https://google.github.io/eng-practices/review/reviewer/looking-for.html), [Microsoft architectural principles](https://learn.microsoft.com/en-us/dotnet/architecture/modern-web-apps-azure/architectural-principles), [OWASP security guidance](https://cheatsheetseries.owasp.org/), [W3C accessibility tutorials](https://www.w3.org/WAI/tutorials/), [MDN web documentation](https://developer.mozilla.org/), the original [Twelve-Factor guidance](https://12factor.net/), and [testing guidance](https://martinfowler.com/articles/practical-test-pyramid.html).

Language-specific rules reference [Python](https://docs.python.org/3/), [TypeScript](https://www.typescriptlang.org/docs/), [typescript-eslint](https://typescript-eslint.io/rules/no-floating-promises/), [Microsoft C#/.NET](https://learn.microsoft.com/en-us/dotnet/csharp/), and [Oracle Java](https://docs.oracle.com/javase/tutorial/).
