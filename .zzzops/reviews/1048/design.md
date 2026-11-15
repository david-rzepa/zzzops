# G1048: show the default process and CLI disclosure

## Owner direction

The owner requested: “Ok I think we should provide information about the default workflow. I don’t think it mentions anywhere how it’s the CLI that returns next instructions and it’s that that’s performing the disclosure.” The existing override “Don’t merge the paper to main” remains binding. This goal prepares and reconciles a dev-only change; root retains final merge authority.

## Focused edit

Change only the ZzzOps illustration in `docs/WHITEPAPER.md`, preserving the conceptual argument, Prior Work and existing-term acknowledgement, Future Work, byline and verified v3.0.0 implementation pin. Add a short phase-level sketch of the shipped opinionated process:

A recorded goal leads to design, independent review and separate adversarial critique, filtering and human design approval. After branch/base preparation, test design and its review precede implementation; checks and implementation review/filter follow. The process culminates in an integration PR **and** human merge approval before merge. Design reviewers can become ready together; integration and merge approval have their own prerequisites and can also proceed alongside one another. Findings can reopen earlier work. Avoid an exhaustive node catalogue or a single serial chain.

The repository owns and can customize the workflow, policy and prompts; the mostly unopinionated engine still enforces stable coordination invariants. This sketch describes the checked fifteen-node shipped default, not every repository's process.

## Make the CLI handoff visible

Replace the existing ZzzOps diagram labels and equivalent prose with the concrete loop:

1. The coordinator calls `zzzops next`. The CLI computes and returns a frontier view: multiple eligible actions, waits, human items and exact start commands. Capacity and display rules can limit the visible set. This overview identifies work; it is not the full task-instruction bundle.
2. The coordinator follows an eligible `zzzops start` command. For an agent node, the CLI selects and returns its task card: prompt, selected instructions, declared inputs/context, pointers and exact submit/renew commands. For an operation node, start executes that operation instead of returning an agent card. Human decisions remain explicit CLI items.
3. A worker records its result with `zzzops submit`; operations and human answers also update recorded state. The coordinator calls next again. The software selects the disclosures; the coordinator dispatches the indicated work rather than inventing a process or relying on an invisible scheduler.

Keep the existing capability/model-guidance distinction. Use short diagram labels, an agent/operation branch and a feedback arrow to next, with readable equivalent prose. Reject a full CLI reference, raw schemas and a misleading diagram in which the coordinator itself selects card contents.

## Verification and boundaries

Source inspection at `ffb3e43f3be01ebd7733a3751d57f79c5dc7f33b` covered the shipped workflow, `render.goal_actions/render_next`, `verbs.start` and `card.build`. Review the focused diff for accurate prerequisites, CLI roles, accessible wording and diagram/prose agreement. Use an unchanged-test checkpoint and existing whitespace command; no new tests, checkers or infrastructure. Run configured local full validation once on the changed tree before remote CI, then ordinary independent/exact-head gates. No other files, runtime/policy changes, main activity, release/tag/publication actions, blog or banked reset.
