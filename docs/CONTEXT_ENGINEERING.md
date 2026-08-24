# Repository context-engineering audit

This historical audit applies Anthropic's July 2026 [context-engineering guidance](https://claude.com/blog/the-new-rules-of-context-engineering-for-claude-5-generation-models) only to the context used by agents maintaining this repository. It does not prescribe Agent Plugin behavior.

| Guideline | Disposition | Repository evidence or decision |
| --- | --- | --- |
| Let the model use judgment instead of accumulating universal rules | Already satisfied | Root instructions retain only repository invariants and route ZzzOps workflows to their existing authorities. They do not restate general coding style or implementation tactics. |
| Design expressive interfaces instead of constraining behavior with examples | Already satisfied | Maintainers use the repository's schemas, enums, CLI contracts, and tests as the authoritative interfaces. Changing those shipped interfaces is outside this audit. |
| Use progressive disclosure instead of loading everything upfront | Already satisfied | `AGENTS.md` routes goal work to the relevant skill and specialized references. `CLAUDE.md` delegates to the same root context instead of duplicating it. |
| Keep tool descriptions simple and avoid repeating instructions | Already satisfied | Root context names workflows and repository boundaries; selected skills and rules carry their own detail. The root files do not duplicate tool manuals. |
| Prefer automatic memory over storing personal memory in `CLAUDE.md` | Not applicable | ZzzOps goals and reviewed policy are shared, inspectable repository state rather than personal model memory. `CLAUDE.md` contains no personal memory. |
| Prefer rich references over oversimplified prose specs | Already satisfied | Repository work can inspect implementation code, schemas, fixtures, CI definitions, tests, and the acceptance ledger directly. Root instructions point to those authorities rather than paraphrasing them. |
| Put product context in the system prompt | Not applicable | This repository cannot control the Codex system prompt. Its reviewed charter and local instructions supply repository context through supported project surfaces. |
| Keep `CLAUDE.md` lightweight and repository-specific | Already satisfied | `CLAUDE.md` has one delegation sentence plus the repository-specific locations of installed and canonical skills. |
| Keep skills lightweight, opinionated, and progressively disclosed | Outside scope | The canonical skills are shipped ZzzOps runtime content. They may be audited under a separate runtime goal, but this repository-only goal does not edit them. |
| Simplify without assuming smaller context is automatically better | Implemented by boundary | The audit uses the existing prompt measurements and behavioral checks as guardrails. It removes the initially proposed runtime rewrite rather than treating instruction deletion as an end in itself. |

## Verification boundary

The historical baseline was 56,766 canonical prompt bytes, approximately 14,200 estimated tokens. Current Codex Agent Plugin prompt accounting is reported by `.agents/prompt_stats.py`. Its blocking limits cover the always-loaded repository instructions and the frequently routed goal-capture and execution contexts. Per-workflow profiles and the complete prompt inventory remain advisory: mutually exclusive, explicitly invoked workflows do not consume one artificial shared allowance. Each blocking limit records its baseline and justified headroom in the checker; changing one requires explicit value justification.

Context-only changes must remain separate from Agent Plugin skills, runtime rules, policy validators, initialization templates, and downstream behavior. Required CI at the exact final PR head supplies the shipped-behavior regression evidence.

## Hot-path distillation ([goal #302](https://github.com/david-rzepa/zzzops/issues/302))

The deterministic Codex route measurement includes `AGENTS.md` and normalizes prompt line endings before estimating `ceil(bytes / 4)` tokens.

| Context | Baseline bytes / tokens | Final bytes / tokens | Reduction |
| --- | ---: | ---: | ---: |
| Always loaded | 2,499 / 625 | 2,499 / 625 | unchanged |
| Goal capture | 15,041 / 3,761 | 13,294 / 3,324 | 1,747 bytes / 437 tokens (11.6%) |
| Goal execution | 37,886 / 9,472 | 33,850 / 8,463 | 4,036 bytes / 1,009 tokens (10.7%) |

Capture savings came from shared `BACKENDS.md` (527 bytes), `CONTINUATION.md` (295), `FEEDBACK.md` (504), and the capture skill (421). Execution receives the same 1,326 shared bytes and additionally saves 1,584 from `EXECUTE.md`, 531 from `BRANCH_REVIEW.md`, and 595 from `SELF_REVIEW.md`. `AGENTS.md`, initialization, goal-state semantics, and execution strategy were retained because they carry distinct always-loaded, authority, state, verification, and parallelism behavior.

The first new fixture made the routed evaluation fail on the previously prose-only `Git-free creation` invariant before the compact replacement restored it. Broader contract tests also rejected tempting paraphrases that lost exact unattended-question, priority, work-state, review-read, unknown-discovery, self-review, or provenance signals; those behaviors were retained. Final deterministic evaluation passes 10/10 workflows in about 3–5 ms with zero tool calls and retries. Prompt-budget tests, 147 workflow/runtime tests, three manual-acceptance tests, and Agent Plugin schema validation also pass locally; required cross-platform CI remains the final exact-head gate.
