# Context-engineering audit

This audit applies Anthropic's July 2026 [context-engineering guidance](https://claude.com/blog/the-new-rules-of-context-engineering-for-claude-5-generation-models) to ZzzOps across Codex and Claude. It treats the article's reported prompt reduction as evidence for simplification, not as a transferable percentage target.

| Guideline | Disposition | ZzzOps evidence or change |
| --- | --- | --- |
| Let the model use judgment instead of accumulating universal rules | Already satisfied | Root instructions contain repository invariants and route workflow detail to skills. Safety, authority, privacy, durable state, and observable verification remain explicit because violating them is consequential. Style and implementation judgment defer to repository evidence. |
| Design expressive interfaces instead of constraining behavior with examples | Implemented | The requirements-interview policy now exposes only its meaningful `light`, `standard`, or `thorough` depth choice. Fixed-value mode, stakeholder, execution-question, blocker-interview, and disabled-watch controls were removed from new policy plans. Existing goal schemas, status enums, and CLI parameters remain code-native interfaces. |
| Use progressive disclosure instead of loading everything upfront | Already satisfied | `AGENTS.md` and `CLAUDE.md` are lightweight routers. Skills load shared rules and specialized create, unblock, review, and self-review references only when applicable; routed prompt profiles exclude conditional execution references. |
| Keep tool descriptions simple and avoid repeating instructions | Already satisfied | Skill descriptions select workflows; detailed behavior lives in the selected skill or narrow shared rule. The prompt evaluation detects required cross-harness semantics without copying full procedures into the root files. |
| Prefer automatic memory over storing personal memory in `CLAUDE.md` | Not applicable | ZzzOps stores shared project goals, blockers, policy, and evidence as canonical project state. This is durable product data rather than personal model memory and must remain inspectable across users and harnesses. |
| Prefer rich references over oversimplified prose specs | Already satisfied | Managed JSON schemas, policy enums, implementation code, deterministic workflow fixtures, acceptance ledgers, and repository tests provide high-fidelity references. Human prose explains outcomes and decisions without replacing those interfaces. |
| Put product context in the system prompt | Not applicable | ZzzOps does not own the Codex or Claude system prompt. It supplies repository and workflow context through installed root instructions, skills, rules, and deterministic interfaces. |
| Keep `CLAUDE.md` lightweight and repository-specific | Already satisfied | `CLAUDE.md` delegates to the shared repository instructions and only names Claude-specific skill discovery paths. |
| Keep skills lightweight, opinionated, and progressively disclosed | Already satisfied | Each skill routes one workflow and loads shared or specialized references only when needed. ZzzOps-specific opinions concern durable goals, authority, verification, and continuation rather than general coding style. |
| Simplify without assuming smaller context is automatically better | Implemented | Baseline and final aggregate/per-workflow measurements use the same prompt accounting and routed semantic fixtures. Retained safety and workflow instructions are judged by observable behavior, not deletion volume. |

## Measurement contract

The integrated baseline is 56,766 canonical prompt bytes, approximately 14,200 estimated tokens. Routed Codex/Claude estimates are capture 3,688/3,743, execution 9,278/9,332, policy review 2,164/2,219, migration 3,368/3,423, suggestion 3,383/3,438, acceptance 1,264/1,318, and feedback 2,493/2,547.

The retained implementation changes policy templates, validation, tests, and non-prompt documentation. It must leave those prompt measurements unchanged, preserve all 14 routed Codex/Claude semantic fixtures, and keep the existing ceiling unchanged. The repeated platform and installer matrix runs in CI.
