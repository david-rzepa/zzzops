# G1029 review_design (attempt 2)

**Verdict: approved.** Revision 2 (blob f4c4419) resolves review_design:1:1. The diff from revision 1 changes only D2's format line, D3, D4 and the new D5, plus the interfaces, tests and risks that follow from them. The engine is still unchanged. There are no new findings and no owner questions.

## Prior finding

- **review_design:1:1: resolved.** All four parts of the fix are in place:
  - **Skill.** Only the owner chooses Amend or Proceed, in their own words. With no owner present, the goal is created without the paragraph, and the Intent lens raises the departure (an owner question under G1026). A manual acceptance row covers this.
  - **No skip.** The skill never offers an `approve_design` skip for such a goal, and an `edit` that adds the paragraph drops that skip in the same edit.
  - **Lens.** The lens honours only a paragraph that quotes the owner with a date. Otherwise the paragraph "accepts nothing", and test 2 pins that wording.
  - **Approval.** `approve_design.md` shows the paragraph verbatim. I checked the claims D5 rests on:
    - `approve_design` has no `spec` input, so prompt guidance is the cheaper route and it avoids staling every open goal.
    - `zzzops show G --json` does return `goal.spec`.
    - A later spec edit stales `design`, so `approve_design` runs again.

## Notes (non-blocking)

- **Delegated approvals.** In this repository, approvals are delegated to the root, so `approve_design` is usually answered by the root, not the owner. D5's "the owner sees there what was recorded in their name" is therefore true only when the owner answers or reads the item. The real guard is D4: only the owner's own words create the paragraph. The design's own Risks entry ranks the fabricated-quote risk with the trust already placed in `decided_by`/`quote`, which is fair. It is worth one clause in D5, so nobody reads it as an owner check that always happens.
