# G1036 adversarial design review

Approved with no findings.

Reviewed the attempt 9 design change and current specification against the adversary lens. The latest owner instructions explicitly authorize a simpler conceptual paper, proposed Future Work and retirement of the goal-specific checker; these are settled scope choices, not new owner decisions.

The design avoids the cheapest misleading interpretations of the new parallelism/routing explanation. It states that the frontier can identify several eligible actions, not that every printed compact view lists every action or that every eligible action may run concurrently without constraints. At c455, `render.goal_actions/render_next` collect multiple actions, and `verbs.start` enforces agent capacity and shared-workspace lease guards. The planned explanation preserves those boundaries.

The model distinction is also accurate: `render.action` exposes capability and `card.build` populates `run.models` from `settings.routing.tiers`; the coordinator/harness performs dispatch. The design explicitly rejects autonomous dispatch or verified-model-identity claims and labels richer scheduling/routing as proposed Future Work. Parallel eligibility and model guidance are not presented as correctness, safety or savings guarantees.

The mostly unopinionated engine remains bounded by stable execution/state invariants. Repository customization does not imply arbitrary removal of engine invariants, and selective task cards are not promised as isolation. General-pattern and implementation claims remain distinct; no empirical or historical-priority evidence is invented.

Retiring `.agents/whitepaper_check.py` through `test_design` respects the accepted-test boundary. Ordinary local repository verification, independent reviews, approvals and PR #773's GitHub blocker remain in place. The design does not authorize runtime, policy, template, schema, contract or private-evidence changes, external publication, or weakening branch rules. No security, privacy, data-loss or irreversible-action defect was identified in this documentation-only plan.

No previous findings were open on this card. No tests were run: this phase reviews a design and source-backed boundaries, and changes no application code.
