# G1036 design review, attempt 9

Approved with no findings. Reviewed the changed design first, then the current design/spec and the assigned seven lenses independently. No other review of this subject was read. The previous card lists no findings requiring status.

- **Intent:** The design preserves the general definition-first concept paper and configurable-layer philosophy, then directly implements the owner's latest requests: multiple eligible actions, task-specific model guidance, less evidence machinery and proposed Future Work. Earlier owner decisions are retained with the latest supersession explicit; no new owner choice is taken.
- **Simplicity:** Removing the goal-specific checker and ledger is proportionate to a prose revision. Retirement occurs through test_design rather than a replacement framework, and the plan keeps the existing conceptual structure and ordinary verification.
- **Truth:** Checked c455 source in engine/render.py::goal_actions, render_next, action and run_capability, plus engine/card.py::build. These support multiple eligible actions, capacity and per-action capability, with card model suggestions drawn from settings.routing.tiers. The design correctly leaves actual dispatch/model choice to the coordinator/harness and automated orchestration as proposed work. It also qualifies compact-output truncation.
- **Adversary:** The design does not turn eligibility or model suggestions into safety/correctness guarantees, introduce private evidence, invent decisions, or authorize external publication. Existing GitHub rules and the PR blocker remain intact.
- **Concurrency:** Independent work is distinguished from unrestricted shared-workspace access; capacity/prerequisite/workspace constraints are acknowledged without expanding runtime scope.
- **Rollout:** Only documentation and the goal-specific manual checker change. The accepted test checkpoint retires the frozen checker before implementation, preserving the test-freeze boundary; runtime, policy, templates and contracts remain unchanged. Existing PR #773 is updated under existing gates.
- **Experience:** A shorter paper, explicit plural frontier and concise proposed applications address the owner's difficulty with depth and evidence overhead. At most two diagrams retain equivalent prose, and the byline/blog draft status remain clear.

This is a design review based on the cited immutable source and design diff. No runtime changes or new tests were needed to assess it. Implementation review must verify the actual wording and removal of obsolete checker commands.
