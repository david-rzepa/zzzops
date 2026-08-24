# Analyze a repository for bootstrap

This stage is read-only. Establish the minimum evidence needed to classify the repository, resolve consequential architecture choices, and propose a proportionate harness. Do not create goals or modify the target.

## Evidence route

1. Read the supplied specification and reviewed PROJECT policy, especially effective engineering rigor and autonomy. If policy is unreviewed, hand off to `$review-zzzops-policy`, record a resume point, and return here afterward; never initialize policy locally.
2. Inspect only decision-relevant tree entries, manifests/locks, pinned versions, source/config, instructions, architecture docs, build/test/verify commands, CI, and history or exposed GitHub state when it can change the conclusion.
3. Classify from evidence, without asking the user to select a mode:
   - `greenfield`: no meaningful product scaffold or established conventions;
   - `early_scaffold`: stack or skeleton exists, but architecture/product behavior and harness are minimal;
   - `brownfield`: active product structure or conventions exist and must outrank generic preferences.
4. Stop reading when mode, material constraints, and the next consequential decisions are supported. Record contradictory evidence instead of averaging it away.

## Unknowns and interview

Reuse supplied/repository evidence before asking. Classify each unknown as:

- `reversible_assumption`: low-risk, cheap to undo, permitted by reviewed autonomy;
- `later_goal`: not required to commit the harness architecture;
- `architecture_blocker`: changes a foundational boundary and must be resolved first.

Use effective rigor as the depth control. Vibe establishes purpose, critical constraints, and a small reversible milestone. Structured also resolves material stack/version, target, public interface, persistence, verification, and architecture boundaries. Agentic additionally covers applicable security, sensitive data, compatibility, failure/recovery, operations, rollout, and deterministic enforcement. Ask 1–3 consequential questions at a time; never turn absent, irrelevant dimensions into ceremony.

## Proposal

When review is consequential, present a concise proposal containing only justified entries:

- mode and decisive evidence;
- stack and pinned versions;
- architecture boundaries;
- harness and one canonical verification path shared by CI;
- compact static context plus links to dynamic specialist context;
- initial milestone and explicitly deferred decisions;
- assumptions, later goals, blockers, and the smallest observable bootstrap proof.

For brownfield work, describe preservation and gaps before additions. Prefer deterministic enforcement for invariants agents must not forget. Do not add a tool because a generic template contains it, and do not begin product implementation.

## Fixtures

| Evidence | Expected result |
| --- | --- |
| Empty tree; disposable CLI spike; reviewed vibe | `greenfield`; purpose/constraints plus reversible stack assumption; no CI or enterprise questionnaire unless another risk escalates it. |
| Manifest, pinned runtime, generated skeleton, no behavior/tests/CI | `early_scaffold`; preserve the selected stack, resolve only architecture-blocking choices, and propose the missing structured harness. |
| Established source/tests/CI/architecture with one incomplete verify command | `brownfield`; existing conventions win, proposal is a gap audit, and canonical-verification repair is identified without re-scaffolding. |
| Structured default plus authentication and sensitive data | Effective agentic depth; surface security, data lifecycle, failure/recovery, operations, and enforcement decisions before architecture commitment. |
