# Analyze a repository for bootstrap

This stage is read-only in the target repository. Establish a product brief before committing the harness: what outcome is being built, for whom, how success is observed, and which choices could create expensive downstream fan-out. An isolated disposable probe may gather stack evidence without modifying the target.

## Evidence route

1. Read the supplied specification and repository evidence. Reuse any reviewed PROJECT policy, but when policy is absent gather enough product facts first to inform its review; never invent or approve policy locally.
2. Inspect only decision-relevant tree entries, manifests/locks, pinned versions, source/config, instructions, architecture docs, build/test/verify commands, CI, and history or exposed GitHub state when it can change the conclusion.
3. Classify from evidence, without asking the user to select a mode:
   - `greenfield`: no meaningful product scaffold or established conventions;
   - `early_scaffold`: stack or skeleton exists, but architecture/product behavior and harness are minimal;
   - `brownfield`: active product structure or conventions exist and must outrank generic preferences.
4. Stop reading when mode, material constraints, and the next consequential decisions are supported. Record contradictory evidence instead of averaging it away.

## Product interview and unknowns

Reuse supplied/repository evidence before asking 1–3 consequential questions at a time. At effective rigor establish beneficiaries, observable success, scope/non-goals, the initial milestone, operating constraints, and applicable security, data lifecycle, compatibility, failure/recovery, deployment, external-state, accessibility, and governance concerns. Questions elicit product facts, preferences, constraints, and authority; they do not outsource technical design to an inexperienced user.

Classify each unknown as:

- `low_commitment_assumption`: satisfies the [[bounded commitment]](../../../concepts/bounded-commitment.md) recovery bound and reviewed autonomy;
- `high_commitment_choice`: stack, framework, persistence, architecture, or shared tooling with material fan-out; compare credible options, structural cost signals, assumptions, and a falsifiable validation signal;
- `later_goal`: not required to commit the harness architecture;
- `authority_blocker`: unresolved product scope, incompatible public contract, destructive migration, external cost/state/deployment, or safety/privacy authority.

Use effective rigor as the depth control. Vibe establishes purpose, critical constraints, and a small low-commitment milestone. Structured also resolves material stack/version, target, public interface, persistence, verification, and architecture boundaries. Agentic covers applicable security, sensitive data, compatibility, recovery, operations, rollout, and deterministic enforcement. Never turn absent dimensions into ceremony.

If the user has no stack preference, evaluate credible supported options against the product brief. Use the cheapest isolated disposable spike when evidence could change the choice. Proceed when one option clearly dominates under reviewed policy or the human explicitly reviews the exact current design. Record that review and invalidate it after a material design change; never infer it from policy approval, an ordinary PR, or unrelated review. Otherwise carry the high-commitment choice into the canonical goal as a durable blocker and preserve independent safe work.

## Product brief

Produce a concise brief containing only justified entries:

- mode and decisive evidence;
- stack and pinned versions;
- architecture boundaries;
- harness and one canonical verification path shared by CI;
- compact static context plus links to dynamic specialist context;
- initial milestone and explicitly deferred decisions;
- beneficiaries, outcome, success boundary, scope/non-goals, initial milestone;
- assumptions, later goals, commitment classification, blockers, and the smallest observable bootstrap proof.

The brief informs policy review and the canonical top-level product goal; it is not another approval gate. For brownfield work, describe preservation and gaps before additions. Prefer deterministic enforcement for invariants agents must not forget. Do not add generic tooling or begin product implementation during analysis.

## Fixtures

| Evidence | Expected result |
| --- | --- |
| Empty tree; disposable CLI spike; reviewed vibe | `greenfield`; outcome/constraints plus low-commitment stack evidence; no enterprise questionnaire unless another risk escalates it. |
| Manifest, pinned runtime, generated skeleton, no behavior/tests/CI | `early_scaffold`; preserve the selected stack, resolve only architecture-blocking choices, and propose the missing structured harness. |
| Established source/tests/CI/architecture with one incomplete verify command | `brownfield`; existing conventions win, proposal is a gap audit, and canonical-verification repair is identified without re-scaffolding. |
| Reviewed structured rigor plus authentication and sensitive data | Effective agentic depth; surface security, data lifecycle, failure/recovery, operations, and enforcement decisions before architecture commitment. |
