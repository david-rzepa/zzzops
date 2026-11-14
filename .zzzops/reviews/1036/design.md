# G1036 design: deterministic progressive disclosure

Design refresh, attempt 7, 2026-11-14. This replaces the obsolete report gate, evaluation requirements and binding assumptions in revision 6; the earlier design/review history remains in Git. This phase produces a design only.

## Owner decisions

WD1–WD8 were recorded from the 2026-11-01 interview, relayed by the coordinator. Quotes preserve the owner's words; the interpretation below reflects the clarified scope.

| ID | Question | Owner's answer | Application |
|---|---|---|---|
| WD1 | Audience | “Both, practitioner-first” | Accessible front half; precise technical back half. |
| WD2 | Core claim | “Progressive disclosure” | The disclosure mechanism organizes the paper. Reliability and cheapness remain design aims, without an empirical claim. |
| WD3 | Venue | “Repo page + blog post” | Reference paper at `docs/WHITEPAPER.md`, linked from README; shorter blog draft. |
| WD4 | Blog location | “External, you publish” | `docs/blog/release-1.md` is an owner-published draft; this goal performs no external publication. |
| WD5 | Prior art | “Brief related-work section” | Generic comparison of approaches, without benchmarks. |
| WD6 | Term | “Coin "deterministic progressive disclosure"” | Define this term through frontier computation and per-node cards. |
| WD7 | Byline | “Your name” | David Rzepa, with an agent drafting/review disclosure. |
| WD8 | Evidence | “Ratios and trends only” | Applies if cost/performance evidence is mentioned; no such evidence is required or planned. |

The owner clarified, relayed by the coordinator for this attempt: “We don't need to include dogfood evidence in the paper, I just wanted to finish dogfooding first to ensure there were no major issues that would require changes to the whitepaper”. The owner also said: “Yeah I would say the paper should still focus around the idea of ¨deterministic progressive disclousre¨”. The governing purpose remains: “My hope is that if there's enough detail describing exactly the behavior, then I can use it to spot flaws and we can keep it as a working document while we tweak things”. These settle the refresh; no new owner choice is needed.

## Outcome and approach

Deliver a dated, long-form working paper that explains **state → frontier → next → task card → result/review → recomputed context**. Its thesis is that executable, declared workflow state selects the next work and the context initially disclosed to that worker. Every behavioral detail should explain this mechanism, expose a failure boundary, or make a claim auditable. Do not turn the paper into a second CLI manual.

Create `docs/WHITEPAPER.md` (roughly 5,000–7,000 words, flexible for clarity), `docs/blog/release-1.md` (roughly 900–1,200 words), and a small manually invoked `.agents/whitepaper_check.py`; add a neutral README link describing the paper's mechanism and audit purpose. The blog is explicitly a draft announcement for owner publication and asserts no official release, deployment or completed run. Agent drafting/review disclosure appears with David Rzepa's byline.

The documentation layout and normative-reference arrangement inherit G1017. The review/filter model inherits G1000, read through the current implementation: the shipped default graph has since become 15 nodes with multi-lens reviewers, rather than the dependency design's historical 26-node form. Explain the checked default and cite its tests; do not re-design either dependency. `docs/design/SPEC.md` remains the exact normative schema/algorithm reference; `DESIGN.md` records decisions and rationale. Record discrepancies separately, without silently changing either document to fit the paper.

Rejected approaches: an encyclopedia would obscure the thesis and duplicate SPEC; a short manifesto would not expose flaws; a dogfood case study or evaluation would reintroduce the owner's discarded deliverable and privacy risk. Pinning every claim to the installed package while implying its extra feature has merged would misstate provenance. Requiring plugin equality between that unmerged snapshot and a dev-based docs worktree would needlessly block writing. No new infrastructure is justified.

## Narrative and technical coverage

The front half starts with the definition, why durable workflow state matters across interrupted sessions, one complete loop, a compact correction example, and situations where the mechanism is excessive or insufficient. State the intended benefit as an aim, not proven reliability or savings. Related work briefly compares issue-tracker agents, orchestration frameworks, single-session work and retrieval/context loading. Retrieval can itself be deterministic; the distinction is declared workflow selection versus relevance-based or agent-chosen selection, not a claim that all retrieval is stochastic.

The back half follows the same loop at increasing precision:

1. **State and snapshot.** Show goal documents, records, artifacts, lease refs, policy and workflow as durable Git data. Explain the invocation's fetched snapshot and expected-ref, atomic compare-and-swap writes, including contention/retry; goal-creation request keys provide a bounded example of ambiguous remote-response recovery. Git history is useful provenance, not authenticated or tamper-proof execution evidence.
2. **Frontier and next.** Define the pure frontier as a function of its complete preloaded arguments, including `now`. Give the eight states (`skipped`, `blocked`, `waiting`, `running`, `reclaimable`, `ready`, `needs_human`, `current`) in a compact trigger table. Explain readiness from current/ok producers, reviewed dependencies enabling discovery before delivery, named waits versus dead ends, holds, releases, priorities, capacity and batched human items. Summarize precedence rather than invent a simplified state machine that contradicts it: live leases appear before missing-input checks; stale inputs, blocked records, corrections, non-ok results and approval rules then determine work. State which rules require capabilities.
3. **The card as disclosure.** Show a short annotated card: declared prompt, selected instruction names, semantic inputs versus readiness/context edges, declared policy values, changed/previous/correction views, immutable read pointers, workspace and exact submit/renew commands. Initial disclosure is selective; pointers allow deeper reading, and workers can inspect other material. It is no access-control boundary. Prompt text is not an identity input merely because the card displays it.
4. **Result and invalidation.** Distinguish artifact blob identity, normalized checkpoint change identity and full code-tree checks; explain selected subfields, definition allowlists, declared policy and review subjects. Context edges gate readiness but do not invalidate records. Prompts/instructions and provenance are excluded from normal fingerprints; bumping `rev` is the configured migration mechanism when their change should force reruns. A fingerprint match says declared identity is unchanged, not that the reasoning or output is correct.
5. **Review and correction.** Explain finding target fingerprints, live/carried findings, blocked targets with held output, filter joins, notes, material findings, required responses and dispute escalation. A filter cannot demote a material claim. Cover review independence as holder-label comparison, and owner-question interviewing as prompt/policy procedure supported by durable blocked answers. Round budgets are capability-dependent and stage-specific: count newly raised material-finding rounds, retain the base-only/no-checkpoint and other specified exemptions, and separate these from lease/repeat/dispute caps. Include the boundary cases in the ledger rather than quoting an older “number of retries” approximation.
6. **Recomputed delivery context.** Use code-tree versus change identity to explain frozen tests, merge-sync carry, refused carry, sync-focused implementation re-review and rerun tree checks. Connect stacked PR delivery and expected-head merge checks to their source. Optional Git-flow release/hotfix lines select targets, sync/back-merge and approval gates. Repository deployment and artifact-promotion procedures are external to these Git operations. Recorded production-merge evidence is narrower than application deployment or successful publication to users.
7. **Authority and recovery.** Distinguish engine checks, shipped defaults, root/human procedures and unknowns in an explicit table. Routing tiers advise dispatch; they do not prove which model executed. Lease fencing rejects superseded engine writes but does not kill a process or isolate a filesystem. Explain expiry/reclaim, stale submissions, offline read-only/unknown-lease behavior, worktree conflicts and recovery from source-backed cases. Bootstrap, capability floors and default-policy notices support adoption; installed defaults do not silently replace repository policy.

“Deterministic” is qualified throughout: identical complete frontier arguments yield identical computed results. Git refs alone do not determine byte-identical cards or `next`: clock/lease state, holder/attempt, reader material, command prefix, local paths and rendering context also enter. Generated prose, external tools, GitHub/CI observations and human decisions remain outside that claim.

## Diagrams and worked examples

Use three small Mermaid diagrams: the disclosure loop, a state/transition overview, and the identity/invalidation boundary. Keep labels short, avoid color-dependent meaning and oversized default-graph pictures, and provide equivalent prose immediately below each diagram. Use normal headings, linked contents, narrow tables and text that remains understandable in print when Mermaid does not render.

One clearly synthetic worked sequence follows two generic goals through dependency design readiness, a card with a long-input read pointer, an independent review finding, filter/correction/re-review and approval. Show the exact state and reason before/after each meaningful change and what context the next worker receives. A paired failure/recovery example shows interruption and reclaim, rejection of the old attempt, then an upstream sync: carry preserves qualifying change-bound records while tree checks and sync review still run; an unsafe/conflicting resolution refuses carry or blocks for correction. Check each step against existing tests and cite them beside the example. Do not imply the historical 12-node test fixture is today's shipped graph, or claim a synthetic trace was production evidence. Prefer a concise checked walkthrough over building an exhaustive simulator.

## Source binding and upkeep

Refresh refs/builds before drafting and again before final review. Preparation verified remote dev at `c455b09914b49fd65e169f91a4f79110e3e2540b`; its archived source reports build `0.0.0-dev d0738ea601d8`. The installed/tested snapshot is `4ff4e3f188f613adbd22a0726c1bbde69eed9d1b`, installed build `0.0.0-dev a81bbe0dd4ce`. The diff contains the release-summary extension and its tests/docs; it is on a dogfood branch, unmerged into dev and not an official release.

Use the refreshed **dev core snapshot and its own computed package build** as the paper's primary binding. If the extension is explained, put it in a clearly labelled supplementary subsection bound separately to `4ff4e3f…` and `a81bbe0dd4ce`. It derives read-only summaries and distinguishes recorded production merges from closure or missing evidence; no core-engine claim depends on its presence. The dated header exposes source commit, package build, checked date, integration status and supplementary status. Source/test links use immutable commit URLs; local relative links serve repository documents. No rule requires the docs goal's dev-based tree to contain the extension.

The manual checker reads the paper's labelled binding fields and claim ledger, verifies pinned Git paths and named symbols/tests, archives pinned snapshots into temporary directories, and recomputes their `--version`. It reports plugin drift between the working tree and primary binding for an explicit refresh/review decision; it never substitutes an installed package or edits bindings. It reproduces the two size exceptions with existing fixtures. No CI wiring, scheduled upkeep, dependency installation or benchmark framework. Store execution evidence in the goal artifact/PR, not a public transcript dump.

Upkeep is short: choose a fresh source snapshot; inspect engine/template/capability changes; update affected claims, ledger rows, examples and discrepancy status; compute the matching build; rerun the manual check and relevant existing tests; refresh the blog only where its claims changed. Preserve older pins when describing historical/unmerged behavior.

## Claim ledger and verification

Each material claim gets an ID, scope (engine/default/procedure/unmerged/aim), exact statement, pinned source symbol or SPEC section, named test/reproduction, and known limit. References prove only their actual assertions. A seed map for implementation is:

| Claim family | Core source | Existing evidence |
|---|---|---|
| Snapshot/CAS/recovery | `store.py`, `session.py`, `verbs.py`; SPEC §4.2–4.4 | `test_engine_store.py::NewAndNextTests` and `IdempotentNewTests` |
| States, dependencies, holds | `frontier.py`; SPEC §4.9–4.11 | `test_engine_frontier.py`, `test_engine_portfolio.py::DependencyTests` |
| Identity/context omissions | `fingerprint.py`; SPEC §4.7–4.8 | `test_engine_frontier.py::FingerprintTests`, `test_engine_identity.py` |
| Cards and size | `card.py::build/shrink`; SPEC §4.20 | `test_engine_card_budget.py::ShrinkBudgetTests`, `test_engine_card_preview_fallback.py` |
| next truncation exception | `render.py::render_next`; SPEC §3.15 | `test_engine_portfolio.py::RenderTests::test_truncation_keeps_under_8k` plus waiting-list reproduction below |
| Lease and actor limits | `leases.py`, `verbs.py::start/submit`; SPEC §4.12/4.14 | `test_engine_lifecycle.py::LeaseTests::test_independence_and_held_goal` and `test_submit_after_reclaim_is_fenced` |
| Review/filter/answers | `frontier.py`, `records.py`; SPEC §4.9/4.14/4.15 | `test_engine_review_lenses.py::ReviewJourneyTests`, `test_engine_blocked_findings.py`, `test_engine_owner_questions.py` |
| Budgets, sync, carry, freeze | `frontier.py`, `carry.py`, `identity.py`, `verbs.py`; SPEC §4.10/4.16/4.21 | `test_engine_round_budget.py`, `test_engine_round_budget_zero.py`, `test_engine_merge_sync.py`, `test_engine_clean_sync.py`, `test_engine_merge_sync_recovery.py` |
| Delivery, lines, adoption | `ops/`, `lines.py`, `defaults.py`; SPEC §5/§8.3 | `test_engine_ops.py::ChecksJourney`, `test_engine_branching.py::TargetTests/FinishTests/HotfixTests`, `test_engine_defaults.py::DefaultComparisonTests`, `test_engine_capabilities.py::RequiresTests` |
| Supplementary summaries | `release_summary.py` at `4ff4e3f…` | `test_engine_release_summary.py` at that same snapshot |

Before submission, replace any family-level evidence in the paper with the exact class/test names that support its wording; unresolved claims are labelled open audit questions, weakened or removed.

Preparation ran 56 focused local tests against an immutable c455 archive: shrink budget, frontier, action truncation and real-Git CLI determinism; all passed. Two production-function reproductions show why a clean test suite does not prove universal size bounds: a large `previous` card stays at 8,122 canonical bytes, and one held goal plus 150 dependents produces an 11,270-byte `next` with 150 waiting entries and no actions/human items left to trim. The source targets 4,096 for cards; SPEC §3.14's hard-bound heading overstates it. `render_next` trims actions/human items and some advisory detail, but does not universally enforce SPEC §3.15's 8,192-byte bound. Record both as current discrepancies, with reproduction parameters, not cost/performance evidence. Do not fix the engine in this goal.

Test-design work should implement only the proportionate manual checker and select existing behavior tests; implementation writes the documents against it. Validate links/anchors, immutable citations, evidence classification, all required behavior families, byline/status wording, privacy and print readability. Run the actual pinned-source boundary reproductions and focused existing tests locally before remote gates. Inspect the rendered paper/blog and review every purported guarantee against its scope. No requirement to rerun the entire engine suite for prose alone; preserve configured integration/approval gates.

## Risks and boundaries

The main risks are thesis dilution, stale claims, conflating identity with correctness, and stronger assertions than the code supports. The narrative order, explicit authority labels, immutable ledger and boundary examples address them. Known limits also include declared-edge incompleteness, prompt changes needing deliberate invalidation, shared credentials/labels, remote availability, external side effects and administrative Git changes outside engine checks. These are audit questions and constraints, not assurances of autonomous safety.

Out of scope: runtime/policy/template/schema changes; repairing SPEC discrepancies; a dogfood report, case study or evaluation; private project identifiers or transcripts; official release or deployment claims; external publishing; telemetry; permanent CI guards; and a new orchestration/test framework. The only interfaces changed are documentation, README navigation and the explicitly manual local checker.
