# Policy context boundary

ZzzOps keeps shipped operational defaults in `plugins/zzzops/zzzops/templates/project-goals/INIT_PLAN.json`. Policy review copies accepted decisions and settings into the project policy with their stable identity, digest, source, and snapshot. Ordinary workflows consume that reviewed project policy; they do not select a shipped fallback when a setting is absent.

| Context class | What belongs there | Loading rule |
| --- | --- | --- |
| Static routed prompts | Safety and authority invariants, goal/verification rules, instructions to obey reviewed policy, and semantics for an already-selected value | Loaded only by the routed workflow; no recommended or missing-policy fallback value |
| Current project policy | The project's reviewed decisions and settings | Loaded for ordinary work and counted separately from static prompts |
| Cold defaults and policy review | The canonical initialization catalog, provenance comparison, proposals, and recommendations | Loaded only while initializing or reviewing policy, plus deterministic validation/authoring tests |
| Public documentation | Explanations of out-of-the-box behavior, including `docs/EXECUTION.md` | Never part of an ordinary routed prompt unless explicitly requested |
| Runtime schema/interpreters | Supported-value validation, repository evidence probes, and behavior for the value selected in project policy | May interpret a value; may not silently choose one when policy is missing |

The classified inventory covers artifact verification, dependency gating, resource reservations and parallelism, blocker order, execution reports, refill categories, review modes, workflow invocation modes, and authority/verification invariants. It distinguishes policy choices from command-interface defaults and safety semantics. A missing current operational setting makes the affected policy row stale and routes affected work through `$review-zzzops-policy`; complete unrelated policy remains independently usable only when its boundary is deterministic.

Run `python3 .agents/policy_default_inventory.py` to validate the boundary. The check derives distinctive values from the canonical catalog, requires an explicit interpreter classification for any routed occurrence, and rejects known fallback wording. `python3 .agents/prompt_stats.py --check` reports static routed bytes, current project-policy bytes, and cold default/review bytes separately. Public documentation and runtime source are reported as boundary classes, not counted as static prompt savings.
