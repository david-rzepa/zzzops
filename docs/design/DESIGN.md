# ZzzOps design reset: DESIGN

**Status:** Revision 6.3, approved 2026-10-31 and implemented in #740. Amendments since then: [HISTORY.md §4](HISTORY.md#4-amendments-after-approval); pending amendments: [README](README.md#pending-amendments).

The revision history (revisions 1 to 6.3) is in [HISTORY.md §1](HISTORY.md#1-revisions); §11 below maps each change to its source.

**Audit revisions:**
- **Pinned baseline:** `21e5021f9dd384c828e2a4eb5a32bc96a68f24a1`.
- **Supplemental #566 pin:** `692b7f973308e09384240806e11df3876740049b`.
- **Both pins are contained in `origin/dev` = `64d5196f6f4f91e4d7b5ca773cd6c821c694c0ea`.** That commit is the #739 integration, and the user confirmed all unintegrated work was merged into dev.
- **Citations:** every source citation is a path and line in `64d5196`.
- **Implementation starting point:** `origin/dev @ 64d5196`. No reconciliation of the pins is needed (audit report G §F1).

**Supporting evidence:**

| Source | Contents |
|---|---|
| Audit reports A–G | Seven read-only audit reports, with full per-finding tables and measurements. |
| Design reviews | R0–R2 (first pass), R3–R9 (second pass: prototype, prior art, implementability, deletion, blast radius, and two agent walkthroughs), and the revision 5 and revision 6 decision records (REV5, REV6). The third-pass reports are cited by lens: `cons`, `model`, `harn`, `gen`, `econ`, `evo`. The fourth-pass reports (revision 6.1) are cited as `x` (cross-check) and `m4` (model check), the final cross-check (revision 6.2) as `x2`, and the model check of revision 6.2 (revision 6.3) as `m5`. |
| [SPEC.md](SPEC.md) | The companion specification: every schema, algorithm, CLI flag, output and exit code, and the default data files. This document cites it as "(SPEC §x.y)". |

The reports themselves are not in the repository; [HISTORY.md](HISTORY.md) summarises each source and indexes every amendment id.

This document contains the decisions. Where it disagrees with a supporting report, this document wins. SPEC.md wins on exact names, formats and algorithms that this document does not state; a disagreement between the two is a bug.

---

## 1. Summary

ZzzOps today is a provenance and authority system that happens to contain a workflow engine. The reset keeps the engine and removes the rest.

**What exists (measured).**
- **Goal state is not readable.** A goal's current state is an unbounded journal: compressed envelopes in GitHub issue comments, replayed on every invocation. #566 holds 1,832 comments (73 MB), and one full read takes 26 s.
- **Bookkeeping costs more than the work.**
  - A worker phase needs `start`, `bind` and `submit`.
  - Every write takes a repository-wide GitHub-label lock.
  - Live measurement: about 342 s of CLI time per delegated phase, and at least 54 CLI responses per producing phase.
- **Corrections inflate the graph.** A compiler expands the authored 16-node graph into 34 nodes plus 150 task sets, copied into every goal. One correction costs about 7 extra mutations.
- **Policy edits stale everything.** 20 of the last 23 policy commits staled all open work. Policy is read from whatever worktree runs the CLI: 9 different policies are live across 307 worktrees.
- **Git work runs outside the graph.** Ten Git and publication state machines run beside the DAG.
- **Most recent goals are about the machinery.** 77% of the newest 30 issues concern ZzzOps administering itself.

**What replaces it.**
- **A small engine.** It has five parts:
  1. A coordinator that reads policy, workflow and prompts from the latest remote `dev`, and blocks new work while a policy branch (`zzzops/policy/*`) exists that has not landed.
  2. One bounded JSON document per goal, on that goal's own branch `zzzops/goal/g<id>`, written with compare-and-swap pushes. Writes to different goals never contend.
  3. A pure frontier function.
  4. A two-step phase lifecycle: `start` creates a lease (an empty commit on its own branch), and `submit` finishes it with one atomic push.
  5. A few idempotent operations (`base`, checks, `integrate` with CI, `merge`) that run as ordinary DAG nodes.
- **Two stages.** The graph has a *discovery* stage (design, design review, human design approval) and a *delivery* stage. Discovery runs ahead across all goals, does not wait for dependencies to merge, and needs no worktree. Human gates are batched. Adding a goal flows straight into its discovery: the conversation that captured the goal dispatches its `design` to a worker and goes on capturing.
- **Stacked delivery.** A dependent does not wait for its dependency to merge. Once the dependency has a reviewed PR (for the root of a chain, with its required checks passed), the dependent's work is stacked on that PR's branch, and its own GitHub PR targets that branch, so the PR shows only the dependent's code. Merges still happen in dependency order, and each one restacks its dependents onto the integration branch (§3.16).
- **Reviews.** A review, human or agent, is an ordinary node. Its report is a `docs(review):` commit on the goal's work branch. Its findings reopen the node they target. Every record says whether it is `ok`; a producer satisfies its consumers only when it is current and ok.
- **Integration.** Integration builds a separate PR branch by squashing frozen tests then implementation on the last recorded base, excluding review commits, and then reads the PR's required checks when the PR targets the integration branch. Code has two identities. Its **tree** (the commit's tree without the review directory) says what the code is, and checks bind it. Its **change** (the patch id of the goal's own diff) says what the goal changed, and reviews and approvals bind it. Review commits never stale code identities. A changed real tree re-runs tree-bound checks; an unchanged carried change preserves change-bound judgments, while a configured base edge separately re-runs semantic review after a sync (G1039). Commit-only movement with the same tree is not itself a test trigger.
- **Carry-forward.** A policy requiring `merge_sync` makes `base` merge the target into work history and carry each eligible node to the actual merge commit when its scoped change remains identical. Without the capability, legacy per-commit replay-map carry remains. Tree-bound checks re-run; unchanged change-bound reviews stay current (§3.16).
- **The merge approval is answered early.** `approve_merge` needs only an approved implementation review, not the goal's own CI, so a whole dependency chain's merge approvals can be answered in one sitting. It stays required in the default graph (D3).
- **Unattended runs.** `next` reports `wake_at`, the earliest time a wait ends. An unattended driver sleeps until then with the harness's own scheduling, instead of stopping (§3.12).
- **Bounded mistakes.** A correction budget on agent re-runs, a crash-loop cap and a repeat cap hand runaway loops to the human. A floor of declared engine capabilities stops engines that lack a format from writing.
- **Stated requirements.** The harness must give the CLI and the agents network access to the Git remote and write access to the Git directory; the CLI refuses with a clear `environment` error otherwise. Bootstrap is a skill checklist over `validate`, shipped templates and plain `git`/`gh` (§3.17).
- **One invariant for agents:** every open goal shows an action, a question for the human, or a named wait (a time, a running phase, a release gate, another goal it depends on that is open or held, dependencies that conflict with each other, or an engine upgrade). There are no silent dead ends.

**Estimated scale.**
- **Source:** about 35k lines of package code shrink to about 5–7k.
- **Tests:** about 48.5k lines shrink to about 9–12k.
- **Default DAG:** 12 nodes in revision 6.3 (26 after G1000, §4.1), with no generated topology.
- **CLI:** 11 verbs.

---

## 2. Audit findings and decisions

Each row is one decision.
- **Source:** where the mechanism lives today.
- **Decision:** one of **Remove**, **Replace**, **Simplify**, **Derive**, **DAG** (express as an ordinary DAG node) or **Retain**.
- **Consequence:** what capability or protection changes.

Full fields and measurements are in the cited report sections. Paths are relative to `plugins/zzzops/zzzops/` unless rooted.

### 2.1 Goal persistence (A)

| # | Mechanism (source) | Value it served | Conflict and cost | Decision → consequence |
|---|---|---|---|---|
| P1 | **Current state lives in comment envelopes.** The issue body holds only a payload pointer. Sources: `goals.py:96-110`, `comment_store.py`, and `workflow.py:77-233, 857-988, 2385-2448`. | Work around the 65 KB body limit; immutable records. | §3.4, §3.5. The state cannot be read or edited. #566 needs 19 requests, 76 MB and 26 s per read, and the cost grows with every mutation. | **Replace** with the goal document (§3.2). Normal reads touch no comments. The comment-immutability tamper evidence is lost, which the trust model accepts. |
| P2 | **The payload accumulates history.** One receipt is added per mutation, `evidence[]` keeps every Result, and each goal stores a compiled-graph copy and a policy copy. Sources: `workflow.py:9020`, `:9013`, `capture_v2.py:84`. | Idempotency; proof of CLI custody; cutover detection. | §3.4, §3.3. The #566 payload is 448 KB (77% receipts); 194 MB is reachable from it. | **Remove.** Keep one record per node. A retried submit with the same lease and output is a no-op. History is `git log` of the document. |
| P3 | **Every write performs several full-history reads.** Sources: `fresh_mutation_boundary` (`workflow.py:11494-11545`), `node_persist` (`:9039`, `:9139`) and `zzzops.py:43-82`. | Uncertainty handling for multi-comment transactions. | §3.0, §3.8. At least 300 MB and 100 s per #566 submit (estimate). | **Remove.** A Git push either lands or it does not. Recovery compares one ref. |
| P4 | **Repository-global label lock** `zzzops:lock:workflow`. Sources: `workflow.py:1292-1410`, `reservation.py:641-760`. | Conflicting-write detection (GitHub issues have no compare-and-swap; verified in A §1.5). | §3.0. 8–10 requests per write, and it serializes all goals. | **Remove.** A push to the goal's own branch is the compare-and-swap; different goals never contend. |
| P5 | **Four cache layers.** Materialized state, hydration checkpoints published as frontier steps, comment tails, and portfolio caches. Sources: `state_cache.py`, `workflow.py:990-1117`, `zzzops.py:2221-2316`. | Mitigates P1. | §3.0, §3.8. The #566 tail costs 4 MB on every call; the cache is invalidated by every write. | **Remove.** The local clone is the cache. |
| P6 | **Labels compete with the payload as a source of truth.** Status, schema and priority labels, and v2 portfolio placeholders such as `depends_on: []`. Source: `goals.py:466-480`. | Cheap filtering. | §4.1. Labels contradict the state: #566 still says `status:new` and `schema:v1`. | **Remove** the labels as authority; the frontier reads documents. The only GitHub projection kept is closing the issue when the goal finishes. |
| P7 | **v1 history and v1→v2 converters.** Sources: `goals.py:299-424, 895-1399`, `migration_batch.py`, and one migration per checkpoint inside the frontier (`workflow.py:11300-11318`). | Lossless conversion. | §3.4, §3.0. | **Remove.** Migration is documentation only (§7). |
| P8 | **Archived-prerequisite adoption protocol.** Source: `archived_prerequisites.py`. | Depend on goals closed under older schemas. | §3.5, §3.3. | **Derive.** A dependency is merged when the dependency's document is done with a merge commit that is in dev. Before that, a dependent may stack on it (§3.16). |

### 2.2 Graph engine (B)

| # | Mechanism (source) | Value it served | Conflict and cost | Decision → consequence |
|---|---|---|---|---|
| G1 | **Correction-route compiler.** Generates `gc_interpret/admit/retain/resolve(+batch)` nodes per review, applicability families, and `sw_review_*` late-event task sets. Sources: `graph_compiler.py` (957 lines), `static_workflow.py` (573), `resolution_lifecycle.py` (275). | Rejected reviews lead to rework; findings are not forgotten. | §3.6, §3.2, §3.1. The graph is 21× larger than authored. One correction costs +7 mutations. Six vestigial `gc_retain_*` root steps appear in the happy path. | **Remove.** The generic findings rule reopens the target node (§3.6). No extra phases. |
| G2 | **The evaluator folds all history.** Sources: `phase_evidence.py:1273-1303`, `resolution_lifecycle.fold`. | Obligation persistence. | §3.4, §3.8. | **Remove.** Records hold current state only. |
| G3 | **Contract hash includes nearly all policy.** Sources: `phase_evidence.py:1844`, `:23-55`, and four projection forms (`policy.py:1421-1467`). | Don't reuse work done under different rules. | §3.7, §3.9. Editing one sentence of `documentation_style` stales all 16 nodes (measured). | **Replace** with declared per-node policy inputs (§3.5). |
| G4 | **Identity inputs hash producer attempt and provenance.** Source: `workflow.py:10619`. | Exactness. | §3.9, §4.2. Re-running a review with the same verdict stales 9 nodes; identical implement bytes stale 8. | **Simplify.** Fingerprint by content; code by its `tree` or its `change` (§3.4). |
| G5 | **Policy-DAG cutover ceremony.** Prepare → independent review → apply. Sources: `workflow.py:2513-2539`, `9776-9975`. | Old results must not satisfy changed contracts. | §3.5. Every graph edit blocks every goal that has evidence. | **Remove.** Graph change shows ordinary stale, new or missing nodes. |
| G6 | **Per-snapshot compilation; compiled graph stored per goal.** Sources: `workflow.py:2476`, `:9013`. | Pinned graph for comparison. | §3.4, §3.7. 646 KB to 1 MB per goal. | **Remove.** Goals reference a graph by name; the graph is read from dev. |
| G7 | **Default node ids are hard-coded.** Cross-goal gating (`phase_evidence.py:1897`: `'observe_merge' if publication_gate else 'review_implement'`), delivery and compaction (`workflow.py:6672, 7952-8175`), `git_phase_state.py:455-782`, `managed_worktrees.py:183-186`, `heartbeat.py:445`, and `TRUSTED_TARGETS` fingerprints (`graph_compiler.py:71-85`). | Dependencies, delivery, cleanup. | §3.1, §7. | **Derive.** Generic selectors and node attributes. Validation fixture: rename every node and the full journey still works. |
| G8 | **Executor authority, allocation and permit typing.** | Writer isolation; second assessment. | §3.3. | **Simplify.** Independence becomes one rule: a review's holder label differs from its subject's holder. Isolation comes from worktrees. |
| G9 | **Phase lifecycle:** start/bind/renew/submit/recover/release/block (`workflow.py:10280-10659`). | Duplicate avoidance, changed-input detection, recovery (all genuine). | `bind`, policy receipts and "observed stopped" evidence are ceremony. | **Retain, simplified:** `start`/`submit`/`renew`/`abandon` with a compare-and-swap lease (§3.7). |
| G10 | **Nondeterministic frontier rendering.** `uuid4` request ids (`workflow.py:6262` etc.), clock, local capacity. | — | §3.2. | **Simplify.** No random ids; `now` is an explicit input. |
| G11 | **Applicability, task sets, generations, event placeholders.** | Leaf vs composite goals; N reviewers. | §3.0. | **Simplify.** A per-goal `skip`; no fan-out. Parallel reviewers are separate review nodes. Decomposition creates child goals. |
| G12 | **`working_inputs.py` local request store** (620 lines). | Retry the same request bytes. | §3.0. | **Remove.** Lease-scoped submits plus compare-and-swap make retries no-ops. |
| G13 | **Legacy v1 phase model.** Sources: `workflow.py:1409-2065`, `phase_evidence.py:91-823`. | — | Dead or legacy. | **Remove.** |

### 2.3 Trust, approvals, evidence, administration (C)

| # | Mechanism (source) | Value it served | Conflict and cost | Decision → consequence |
|---|---|---|---|---|
| T1 | **Independence and identity checks.** Self-declared actor strings, plus `CODEX_THREAD_ID == actor != root` for five administrative reviews (`workflow.py:3509, 4103, 9390, 9659, 9708`). Root-only enforcement (`:11097`). | A second assessment. | §3.3. Codex-only: Claude Code cannot run these reviews, which breaks the charter's Codex/Claude Code parity. | **Simplify.** The holder label must differ from the subject's holder. No environment-variable attestation. |
| T2 | **`bind` plus policy receipt.** The agent copies a policy hash back to the CLI; the file is up to 178 KB. Sources: `workflow.py:6173`, `:10339`, `:10541`, `policy_context.py`. | Proof that the agent read policy. | §3.3. One extra transaction per phase; the receipt rotates on every policy change. | **Remove.** Relevant instruction text is inlined in the task card. |
| T3 | **Workspace allocation as a file-edit grant.** `understand` lists files; reviewer and root authorize; commits outside them are rejected. Sources: `git_phase_state.py:259`, `workflow.py:4596-4628`. | Implementers must not weaken accepted tests; scope visibility; non-overlap. | §3.3, §3.2. One unforeseen file forces re-understand, re-review and fresh human approval. | **Remove** the grant. **Derive** the one real rule as the *test-freeze* check (§3.9). |
| T4 | **In-payload lease** with a 600 s TTL, renewal as a full transaction, and no takeover on expiry. | Duplicate avoidance (genuine). | §3.8. | **Simplify.** 2 h default TTL, reclaim after expiry, fencing by attempt (§3.7). |
| T5 | **Heartbeat daemon, local capacity ledger, label phase leases, `reserve` CLI.** Sources: `heartbeat.py` (852), `reservation.py`. | Automatic renewal; per-machine limits. | §3.0, §3.1. A second local orchestration system. | **Remove.** Capacity is the count of running records (§3.7). |
| T6 | **Receipts, provenance wrappers, hash-chain "authentication"** (97 uses of "authenticated" in `workflow.py`). | Retry safety; tamper evidence. | §3.4, §3.3. | **Remove.** Lease-scoped submits replace them. |
| T7 | **DAG authorization nodes.** `approve_understanding`, `authorize_repository` and `authorize_publication` record hashes with no human identity or words. `explicit_approval()` accepts any string (`workflow.py:281`). | Scope and publication decisions. | §3.9. | **DAG.** Human decision nodes with inline decision records (§3.13). Ceremonial nodes are dropped. |
| T8 | **Admin protocols.** Dependency, blocker, archived-prerequisite, checkpoint-reconcile and graph-repair prepare/review/apply: about 1,490 lines in `workflow.py`. Meta-goals exist only to repair other goals (#606, #610, #618, #623, #631). | Safe relationship edits. | §3.5. | **Replace** with direct edit, validation and an impact preview. Relationship edits get no independent review. |
| T9 | **Policy approval digest, bindings, history, default provenance.** Sources: `policy.py:1711-1800, 2013`, `workflow.py:11392-11450`. Any hand edit of POLICY.json or PROJECT.md disables the CLI. | The human sees policy changes. | §3.7, §3.9. 27 ceremonies; about 45 KB of metadata. | **Remove.** Policy changes land on dev from a `zzzops/policy/*` branch, reviewed by whatever route the repository requires (§3.10). The CLI validates structure only. |
| T10 | **Model inventory gates.** 55 reviewed GPT-only pairs, a 7-rule assessment tree, a new-model gate that blocks every start, bind-time pair checks, and Codex session scraping. Sources: `routing.py`, `policy.py:1206-1404`, `workflow.py:6179-6270`, `zzzops.py:2505`. | Cost and capability routing. | §3.2, §3.3, §3.7. Claude Code apparently cannot start phases at all (inferred). | **Simplify.** Advisory `routing.tiers`, shown in the task card. No gates. |
| T11 | **Host-run verification proofs.** | Tests are actually run against the exact commit (genuine). | Bloated by embedded acquisitions and log hashes. | **Retain, simplified** as the `checks.run` operation (§3.9). |
| T12 | **Feedback public-write confirmation.** Source: `workflow_admin.py:52-111`. | A genuine publication decision. | — | **Remove for now** (D9). The human plans a transcript-based replacement. |

### 2.4 Git, worktrees, publication, dependencies (D)

| # | Mechanism (source) | Value it served | Conflict and cost | Decision → consequence |
|---|---|---|---|---|
| W1 | **Worktree preparation is a side effect of `start`.** Base selection takes about 900 lines (`workflow.py:4523-5748`), starting from the caller's `HEAD` (`:4550`). There is one worktree per (node, attempt), even for read-only reviews. | Isolation; resumable attempts. | §3.1, §3.7, §3.2. 188 managed worktrees (2.7 GB); 307 registered. | **DAG.** The `base` operation node. The work branch is created by the first artifact submit, and discovery needs no worktree; one work branch and worktree per goal (§3.9). |
| W2 | **Per-file hash inventories.** Legacy `repository_workspace` (`workflow.py:1560-1947`) is still selected by this repo's policy. | Drift detection before worktrees existed. | §4.2 explicitly. 7 MB hashed per projection. | **Remove.** `code_tree` replaces it. |
| W3 | **Commit identity, single-commit topology, finish-intent journal.** Source: `git_phase_state.py:109-275`. | Exactly-once engine-authored commits. | §3.3, §4.2. Agents cannot commit normally. | **Simplify.** Agents commit normally. Submit records the checkpoint `{commit, base, tree, change}`. |
| W4 | **Retained remote attempt refs**, with an `ls-remote` per proof. Source: `git_phase_state.py:294-343`. | Reachability across machines. | §3.4. | **Remove.** The goal's work branch is pushed. |
| W5 | **RED/GREEN compaction.** Sources: `git_phase_state.py:345-894`, `workflow.py:7939-8371`. | Curated history. | §4.3, §3.1. Forces re-review. | **Remove.** Review commits are dropped instead. Squashing is not engine work. |
| W6 | **Restack sub-machine and base-transition proposals.** | Carry work forward when dev moves. | §3.1, §3.0. | **Remove.** A rebase is a re-run of the `base` node using plain `git rebase` (§3.9). |
| W7 | **Publication topology / one linear stack of all goals**, with `trunk='dev'` hard-coded (`workflow.py:2069`). | Avoid bypassing open ancestors. | §3.2. It serializes goals the DAG does not order. | **Remove.** Each goal reads only its own PR. A dependent's PR stacks only on its own dependencies' PRs (§3.16). |
| W8 | **Publication certificate and terminal merge reconciliation.** Sources: `workflow.py:8535-8815`, `merge_reconciliation.py`. | No double merge, no false merge claim (genuine). | §3.3, §3.1. | **DAG.** The `merge` operation observes, then acts, with `--match-head-commit`. |
| W9 | **Stack integration planner:** a B+ tree stored in issue comments, about 1,400 lines. | Ordered multi-PR merge. | §3.1, §3.0. | **Remove.** Dependency edges between goals provide the ordering. |
| W10 | **Release-plan control issue #695**, with a lock, receipts and a coordinator. Source: `releases.py`. | Numbered releases. | §3.4, §3.8, §3.3. | **Simplify.** A `release` field on each goal, `releases.current` in policy, and a gate. |
| W11 | **Goal dependencies via payload journals and transitive full hydration.** The node names are hard-coded. | Ordering (genuine). | §3.4, §3.8, §3.5. | **Derive.** `depends_on` in the document plus the generic `deps.<node>.<output>` selector. |
| W12 | **Four post-merge cleanup variants.** Source: `managed_worktrees.py:131-309`. | Never delete unmerged work (genuine). | §3.0. | **Simplify.** One `remove_if_safe` helper. |

### 2.5 Policy and coordinator (E)

| # | Mechanism (source) | Value it served | Conflict and cost | Decision → consequence |
|---|---|---|---|---|
| C1 | **Policy is read from the invoking worktree.** `--repo` defaults to cwd (`zzzops.py:4599`). The historical walk starts from that worktree's `HEAD` (`workflow.py:705`). | Simplicity. | §3.7, §3.2. 9 policies live across 307 worktrees, only 41 at dev. Goal branches merge policy commits as a workaround. | **Replace** with the coordinator (§3.10). |
| C2 | **Whole-policy invalidation plus about 1,180 lines of #723-era special cases.** Sources: `workflow.py:623-760`, `phase_evidence.py:2003-2135`. | Avoid over-invalidation. | §3.7. | **Replace** with declared policy inputs. |
| C3 | **The 160 KB POLICY.json.** About 14 KB is actual configuration and instructions; the rest is the DAG (68 KB) and ceremony (about 45 KB). | — | §3.0, §3.4. | **Simplify** to about 4 KB of policy plus a separate workflow file (§3.10). |
| C4 | **Installation validation gate.** Any plugin byte change re-gates every repo. Sources: `installation.py`, `zzzops.py:640-652`. | One-time legacy cleanup. | §3.0, §3.8. | **Remove** the gate. Keep the `package_status` self-check. |
| C5 | **`plugin_freshness.py`.** Its cache is never written, so it always reports "due". | — | Dead. | **Remove.** |
| C6 | **PROJECT.md and PROJECT_AUDIT.md are generated and digest-bound.** | Human-readable charter. | §3.5. | **Simplify.** PROJECT.md becomes hand-edited and unbound. PROJECT_AUDIT.md is deleted. |

### 2.6 CLI and disclosure (F)

| # | Mechanism (source) | Value it served | Conflict and cost | Decision → consequence |
|---|---|---|---|---|
| F1 | **One `--intent` entrypoint multiplexes 52 JSON operations.** Sources: `workflow.py:216-231, 11362-12061`; the dispatcher alone is 699 lines. 28 of the operations are self-administration. A legacy `_private_main` is reachable only from tests (`zzzops.py:3883-4360`). | — | §3.8. | **Replace** with 11 verbs (§3.15). |
| F2 | **Frontier output is mostly waiting steps.** Median 27 KB, max 449 KB; 78% of the bytes are "dependency" steps; inputs arrive only after `start`, in a step averaging about 89 KB. | Completeness. | §3.8. | **Replace** with a bounded `next` (≤ 8 KB) that includes inputs. |
| F3 | **Response store, context references, intent/skill routing.** Source: `zzzops.py:432-910, 4374-4565`. | Compensates for oversized responses. | §3.0. | **Remove.** |
| F4 | **Prompt budget counts static prompts only.** | Prompt cost control. | It misses responses (about 6.7k tokens) and policy reads (about 45k tokens). | **Retain** `prompt_stats.py`. **Add** request/byte budgets for responses (§3.15). |

---

## 3. Target architecture

### 3.1 Engine boundary

```
                 ┌─────────────────────────── installed ZzzOps plugin (engine code) ──────────────────────────┐
 any worktree →  │ coordinator ─► goal store ─────► evaluator (pure) ─► scheduler ─► CLI verbs ─► operations    │
   `zzzops …`    │ one fetch:     zzzops/goal/g<id> frontier per goal   portfolio     next/show/    git.base      │
                 │ dev, goals,    + lease branches; (graph, docs,       order:        new/start/    checks.run    │
                 │ leases,        per-goal CAS push leases, settings,   stage first,  submit/renew/ git.integrate │
                 │ policy branches                  now)                capacity      abandon/      github.merge  │
                 │                                                                    answer/reopen/              │
                 │                                                                    edit/validate              │
                 └──────────────────────────────────────────────────────────────────────────────────────────────┘
 Repository data, read by object id at the coordinator commit (the fetched origin/dev):
   .zzzops/POLICY.json     settings + per-section instructions (~4 KB)
   .zzzops/workflow.json   named graphs; the default graph is in §4
   .zzzops/prompts/*.md    node prompts
   .zzzops/reviews/        review artifacts on work branches only (a constant path; never reaches dev)

 Branches on origin (the "zzzops/" namespace; SPEC §2.1):
   zzzops/goal/g<id>             goal.json, the goal document; history = this branch's log; never deleted
   zzzops/work/g<id>             code commits + docs(review): artifact commits; created by the first artifact submit,
                                 or by `base` at the stack base;
                                 kept by default, deletable once no open goal depends on it
   zzzops/pr/g<id>               review-free PR head built by `integrate`; a stacked dependent's base
   zzzops/stack/g<id>            combine commit of a goal's stack set (dependency PR heads, and I when needed), only when it has two or more commits (§3.16)
   zzzops/lease/g<id>/<node>     one empty commit per phase in progress
   zzzops/policy/<topic>         an open policy change; its existence blocks new work

 GitHub API: used only by the integrate (PRs and required checks) and merge operations, and by base
 to retire a stack PR it no longer needs. Normal work (next/new/start/submit/answer/edit) talks only to the Git remote.
```

**The engine knows only generic concepts:**
- **Node kinds:** `agent`, `human` and `op`.
- **Node attributes:** `stage`, `inputs` and `outputs`, `review.subject`, declared `policy` keys, `instructions`, `workspace`, `preserve`, `release_gate`, `rev` and `timeout`, plus the advisory `root` and `capability`.
- **Goal fields:** `skip`, `state` and `budget`.
- **Engine rules:** the cross-goal selector `deps.<node>.<output>`, the findings rule, `ok` semantics, leases, fingerprints, the generic close, the portfolio stuck rule and the runaway budgets.

**Operation details stay inside operation implementations.** Git commands, `gh` calls and rebase todo generation live there, each about 50–150 lines, idempotent and observe-first. An operation's only durable state is its node's record.
- **Ops are parameterized by their inputs, never by node names.** For example, `integrate` reads its `code` and `review` inputs, and a finding it raises targets the producer of the named input (R5 C6).
- **Ops know nothing of goal lifecycle.** Closing a finished goal is a generic engine rule (§3.11), not something `merge` does (R6 F11).

**The engine contains no default node id.** The default graph is data in `.zzzops/workflow.json`. A test graph with every node renamed must pass the full journey.

**Agent judgment, not engine logic:**
- requirements, design and review content;
- whether a finding is valid;
- model choice;
- proposing child goals (created with `new` only after the design is approved; §3.12);
- rebase conflict resolution;
- what to ask the human.

The engine records these judgments and applies the declared rules.

### 3.2 The five kinds of state, in plain terms

| Kind | Where it lives | Who writes it | How it is read |
|---|---|---|---|
| **Authoritative goal state** | `goal.json` on the goal's own branch `zzzops/goal/g<id>`. One small JSON file per goal (≤ 64 KB): spec, priority, dependencies, release, `skip`, `state` (`open\|held\|closed`), an optional correction `budget`, and the latest finished record of each node (holder, `ok`, input fingerprint, output, findings). Work in progress is a **lease branch** `zzzops/lease/g<id>/<node>` holding one empty commit. Together the `zzzops/goal/*` and `zzzops/lease/*` branches are the single place to look for global state. | The CLI, with one compare-and-swap push per goal; a multi-goal edit is one atomic push of several goal refs. Humans and agents may also commit to a goal branch directly; the CLI validates documents on read. | Each invocation runs one `git fetch` (integration branch, goal refs, leases, policy branches), then reads the goal documents in one `cat-file --batch` session (SPEC §4.2, §4.3). A `State:` trailer on each goal commit says whether the goal is closed, so only open and held goals, and the goals they depend on, are read and parsed. History is the goal branch's log (`git log -p`; `show` prints the command). |
| **Phase artifacts** | Long text (design document, review reports) is a file under `.zzzops/reviews/<id>/` committed on the work branch as a `docs(review):` commit. The first artifact submit creates the work branch at the fetched integration tip. The record keeps the summary, decision and findings, plus `{path, blob, commit}`. | The CLI, during `submit`, using plumbing only, with no worktree or index (§3.8). | Task cards show summaries. Full text comes from `git cat-file -p <blob>`. The blob survives rebases, and work branches are kept by default and deleted only once no open goal depends on them, so it stays reachable for dependents; the commit is only a hint. A task card whose blob is gone says "full text no longer available". |
| **Code identity** | Two identities per checkpoint `{commit, base, tree, change}` (§3.4): `tree` is the commit's tree with `.zzzops/reviews` removed; `change` is the patch id of the goal's own diff from `base` (the integration tip or, when stacked, the stack base), review files excluded. | The CLI, at submit. | Checks bind `tree` and re-run whenever the code differs. Reviews and approvals bind `change` and re-run only when what the goal changed differs. |
| **Effective policy** | `POLICY.json`, `workflow.json` and `prompts/` at the fetched `origin/dev`, read by object id. A best-effort coordinator worktree mirrors them for agents to browse. | A `zzzops/policy/<topic>` branch, landed on dev by whatever route the repository requires (here a PR, because of the dev ruleset). While such a branch exists, new work is blocked (§3.10). | Each node declares the settings it depends on; only those enter its fingerprint. Each node also selects the instruction sections shown in its task card. |
| **External observations** | PR, CI and merge state, observed only by the `integrate` and `merge` operations and recorded as their outputs. | Operation nodes. | As ordinary outputs. Re-running an operation re-observes. |

### 3.3 Workflow definition (`.zzzops/workflow.json`)

```jsonc
{ "schema": 1,
  "graphs": { "default": { "terminal": ["merge"], "nodes": { /* §4.1; full file: templates/default/workflow.json */ } } } }
```

The review directory is the constant `.zzzops/reviews`, the only path `docs(review):` commits may touch. It is not configurable: changing it with goals in flight would break every one of them (`evo:M4`).

Node ids match `[a-z][a-z0-9_]*`. Every field, type, default and range is in SPEC §3.1; this table gives the meaning.

**Node fields:**

| Field | Meaning |
|---|---|
| `kind` | `agent`, `human` or `op`. Human nodes are always review nodes; other human input goes through blocked records (§3.13). |
| `prompt` | Agent and human nodes: a file under `.zzzops/prompts/`. For a human node its first line is the question. Prompt edits never invalidate. |
| `root`, `capability` | Agent nodes, advisory: `root: true` means the root (conversational) agent does it; otherwise a worker. No default node is a root node. `capability` names a `routing.tiers` entry. |
| `op` | Op nodes: the registered operation (`git.base`, `checks.run`, `git.integrate`, `github.merge`). |
| `workspace` | The node uses the goal worktree. It is a node-level flag for agents and ops alike, and at most one live workspace lease per goal is allowed, ops included (R6 F12). |
| `stage` | `discovery` or `delivery`. Scheduling only (§3.12); not fingerprinted. |
| `inputs` | `{name: {from, optional?, context?, pending?}}`. `from` is a selector: `goal.<field>`, `<node>.<output>[.<key>]`, or `deps.<node>.<output>[.<key>]` (for each dependency goal, that node's current value; §3.11). Checkpoint keys are `commit`, `base`, `tree` and `change`, so a consumer chooses which code identity it binds (§3.4). `optional: true` means the input is satisfied with `null` when its producer is skipped. `pending: true` (`deps.` selectors only) means a dependency that is open or held and has no current value yet gives `null` instead of a miss; `git.base` uses it to read "merged or not yet". `context: true` means the value must still resolve (so it gates readiness) and is shown in the task card, but is not fingerprinted, and the edge itself is not part of the node's definition fingerprint (§3.5). |
| `outputs` | `{name: type}`. Types: `text`, `string`, `sha`, `int`, `bool`, `strings`, `object` and `list` (schema owned by the operation), `checkpoint` (`{commit, base, tree, change}`, filled by the CLI) and `artifact` (`{path, blob, commit}`, filled from `--artifact`). A node with a checkpoint output declares an input named `base`. |
| `review` | `{subject: <node>}`. Makes this a review node; agent and human nodes may both be reviews (§3.8). Review outputs are implicit: `decision` and `summary`, plus a `report` artifact (agents) or `decided_by`, `quote` and `decided_at` (humans). |
| `policy` | Dotted keys under `settings` whose values enter this node's fingerprint. |
| `instructions` | Keys of POLICY.json `instructions` whose texts are shown in this node's task card or human item. This is how policy stays progressively disclosed: each node sees only the sections it names. Not fingerprinted. |
| `preserve` | `<node>`. Test-freeze rule (§3.9). |
| `release_gate` | `true`: waiting while `goal.release > settings.releases.current`. |
| `rev` | Integer. Bump it to force-invalidate this node's records. |
| `timeout` | Lease timeout in minutes, written into each lease. Defaults: agents use `settings.leases.ttl_minutes` (120); ops use 15. Ranges are validated: 10–1440 for agents, 2–240 for ops. |

**There is no `require` field.** Every record carries `ok`, and a producer satisfies its consumers only when it is current and ok (§3.6). So "approved" or "passed" never has to be spelled out on an edge.

**Graph validation** (full list in SPEC §3.1):
- Producers must be upstream, and the graph must be acyclic.
- Review subjects must be other nodes upstream.
- Every declared policy key, instruction key, capability and prompt must exist.
- `op` names must be registered, and each op validates the node's inputs and outputs.
- A delivery node must not feed a discovery node, including through `deps.` selectors.
- Selectors must parse and name declared outputs.
- Every node is terminal or a transitive producer of a terminal node, so a newly added node is never silently optional (`evo:M3`).

### 3.4 Code identity

Code has two identities, and each consumer chooses which one it binds (A4).

**`tree`: what the code is.** `code_tree(C)` is the tree of commit `C` with `.zzzops/reviews` removed. It is computed by rewriting tree objects with `ls-tree`/`mktree`, never through an index or a worktree (SPEC §4.7).
- **Why this form.** It costs a constant time regardless of repository size: 6–7 ms on 50k files, against 80 ms and growing for the temporary-index method (R1 A3). The temporary-index recipe in revision 2 was **wrong**: `git rm --cached` checks the shared worktree, so it silently returned the unfiltered tree (R1 H1). Artifact commits use the same tree rewrite to add a file.
- **Locality.** Trees written by `mktree` may exist only in the clone that computed them. Recorded `tree` values are compared as ids; any check that needs the objects recomputes them from `commit` on the local machine (R3 F12).

**`change`: what the goal changed.** `change` is the `git patch-id --verbatim` of the diff from the checkpoint's `base` to its `commit`, with the review path excluded: the goal's own diff (exact diff flags in SPEC §4.7).
- It is **stable** when review commits are dropped, when `integrate` rebuilds the PR branch, and across a clean rebase or restack.
- It **changes** when a rebase alters the diff, for example by resolving a conflict.
- This is the identity code-review systems converged on: Gerrit's Change-Id and patch-id equivalence (R4 H2).
- **It is the same on every machine.** Identity commands ignore system and user Git configuration and attributes, and pin the diff options that would otherwise change the patch id (submodule display, blank context lines). A failed `git diff` is an error, never an empty diff. Only `$GIT_DIR/info/attributes` cannot be disabled, so `validate` warns when it exists (`harn:H2`, `gen:S1`, `gen:M1`; exact commands in SPEC §4.7).

**Checkpoints.** A checkpoint output is `{commit, base, tree, change}`. `commit` is a locator only, never identity. `base` is the node's `base` input (in the default graph, `base.base_commit`), so `change` is the goal's own diff from its base: the integration tip, or the stack base when the goal is stacked on unmerged dependencies (§3.16). A dependency's code is never part of a dependent's `change`.

**Selectors choose the identity.** A consumer writes `implement.code.tree` or `implement.code.change`. When a fingerprint covers a whole checkpoint, such as a review fingerprinting its subject's output, the checkpoint is identified by its `change`.

**Default bindings** (full table in §4.1):

| Consumer | Binds | Re-runs when |
|---|---|---|
| `run_tests`, `integrate` | `tree` | the code actually differs, including after any rebase or restack |
| `review_tests`, `review_impl` | `change` | the goal's own diff differs, not after a review-commit drop, a clean rebase or a clean restack |
| `approve_design` | the design artifact's blob | the design text changes; never because of a rebase |
| `approve_merge` | `implement.code.change`, with the review summaries as context; **not** the PR head, and nothing from `integrate` | the goal's own diff differs |

**Invariants, checked at `submit` and `integrate`:**
- **I1:** every `docs(review):` commit changes only `.zzzops/reviews`.
- **I2:** no other commit changes `.zzzops/reviews`.
- Work branches are linear; `submit` rejects merge commits.

**Dropping review commits changes neither identity.** Under I1 and I2, rebasing to drop review commits leaves `tree` unchanged, even though commit ids change. This was verified by experiment, including the correction-cycle case `base─i1─r1─i2─r2` (R1 A1/A2). `change` excludes the review path, so it is unchanged too.

**Testing the identities.** The fixtures that pin `code_tree`, `change` and the input fingerprint are ordinary unit tests in CI, including a run under a hostile global Git configuration and attributes file. There is no runtime self-test (A5).

### 3.5 Fingerprints and staleness

A node's **input fingerprint** is a hash over four parts (SPEC §4.8):
- **`def`:** the node definition, restricted to an **allowlist** of semantic fields: `kind`, `op`, the op's implementation version, the non-context `inputs` (with their `optional` and `pending` flags), `outputs`, `review`, `preserve`, `workspace` and `rev`. Advisory and scheduling fields (`timeout`, `capability`, `root`, `stage`, `release_gate`, `instructions`, `prompt`) are left out, so editing them stales nothing (R4 M3, R7 M2). Context edges are left out too: a context edge is a readiness gate, and readiness is re-evaluated on every pass, so adding or removing one holds or releases immediately without staling anything. An author who wants a human re-asked bumps that node's `rev` (`evo:H3`).
- **`inputs`:** the fingerprint of each non-context input value. A whole checkpoint is fingerprinted by its `change`, an artifact by its blob, and every other value, including a selected `.tree` or `.change`, by a hash of its canonical JSON. A `deps.` input is a map over the dependency goals.
- **`subject`** (review nodes only): the fingerprint of the subject's recorded output **without its `responses`**, with checkpoints as `change` and artifacts as blob.
- **`policy`:** the current values of the declared `policy` keys.

Canonical JSON is RFC 8785, and every fingerprint string starts with a version, `v1:` (R4 L1, L2). Each record stores its four parts, so a stale node can say exactly what changed (`stale_because`).

**Fingerprint versions** (D4). A record's fingerprint is compared only in the version it carries. An engine computes only its own version, so a record in another version is stale. A version is bumped only when the old one is unsafe (it missed changes), and always together with a new capability (§3.10). The cost is stated with the bump: every open goal's nodes re-run. There is no multi-version support.

- **Provenance is not identity.** Holder, attempt, timestamps and the prompt blob live on the record but never in a fingerprint. The prompt blob id is kept as provenance, so a prompt edit is visible without staling anything (R4 L5).
- **A review's subject part leaves out `responses`** (`econ:H2`, `cons:H1`, `model:H1`). A dispute still reaches the reviewer: it changes the target's full output, so the reviewer's finding dies (`target_fp` keeps the full output), and the reviewer's non-ok record becomes `ready (not_ok)` (§3.6). A `fixed:` response that changes the code changes `change` anyway. What this removes is a re-review, or a re-asked merge approval, when a producer re-runs after a rebase and simply no longer carries its earlier `responses`.
- **Findings and answers are never inputs.** They act through the findings rule (§3.8).
- **The previous review is context.** Its own previous findings are shown to a re-reviewer but not fingerprinted (R1 H4a).
- **Operation outputs consumed by others must be deterministic.** Consumers use `run_tests.result` only as a gate (a context input); durations and logs sit under `details`, which nothing fingerprints (R1 M7). `integrate` rebuilds identical code into the identical PR head (§3.9).
- **Graph changes follow the same rules.** A changed node definition stales that node and its consumers. An added node appears as ready or blocked. A removed node's record is ignored, and its findings are not live. When a node is stale only because of `def`, its task card includes the previous output with "if it still holds, resubmit it"; an identical artifact blob makes no new commit, so the cascade stops there (`evo:H3`).

### 3.6 Frontier algorithm (pure, per goal)

The frontier takes the graph, the goal document, its dependencies' views, its leases, the settings and `now`, and returns one state per node. It is pure: no I/O, no clock reads, and identical arguments give byte-identical results. The pseudocode is in SPEC §4.9 and §4.10. It runs in **two passes** (R5 C1, R3 F8):

1. **Liveness.** From recorded outputs only, decide which findings are live (§3.8). This pass never looks at the states the second pass computes, so liveness cannot be circular.
2. **States**, in topological order. Each node gets exactly one state:

| State | When |
|---|---|
| `skipped` | The goal's `skip` names the node. |
| `blocked` | An input, the review subject, or a dependency is not current, or the node's own non-ok record still has live findings (its targets are reopened instead). Each missing item names its producer and why. A dependency miss has one reason, `dependency`, plus the dependency's state (`open`, `held`, `cancelled`, `invalid`, `merged` or `stuck`), shown in the item. |
| `waiting` | A time wait (`retry_after`), a `deps_conflict` record, or a release gate. A ready workspace node whose goal worktree is busy is rendered as waiting. |
| `running` | A live lease. It is checked before inputs, so a phase in progress always shows as running, even if its inputs went non-current meanwhile. It also carries the node's input fingerprint, computed from the recorded values as for liveness, else `null` when they do not resolve, so a finding submitted by the running phase can be fenced (§3.8; `x:C1`), even while a dependency's CI poll makes the node's inputs non-current (`x2:L1`). |
| `reclaimable` | An expired lease below the crash-loop cap. |
| `ready` | It should run: `new` (no record), `stale` (the input fingerprint changed), `reopened` (live findings target it), `retry` (an agent-wait blocked record), or `not_ok` (a non-ok record whose findings no longer apply). **Every ready node carries every live finding targeting it**, whatever the reason, so a stale and reopened node is still asked to answer them (R3 F1). |
| `needs_human` | A human node ready for its answer, a blocked record waiting for a human, an escalated dispute, or a crash or repeat loop (`crash_loop`). |
| `current` | Done, the fingerprint matches, `ok`, and nothing reopens it. Only current nodes feed their consumers. |

**`ok` semantics** (R6 F4, R5 C10, R3 F9). Every record carries `ok: true|false`:
- review and human nodes: `ok` means `decision == approved`;
- ops: the op sets it (for example, checks passed);
- other agent producers: always ok;
- blocked records: never ok.

A producer satisfies its consumers only when it is current **and** ok. A non-ok record whose own findings have all died is `ready (not_ok)` and runs again. This one rule replaces three revision-4 mechanisms: the `require` input field, the special case for review decisions, and the separate rule that released a non-approved record.

**The stuck rule is portfolio-aware** (R6 F1, R3 F2, R5 C5). A goal is **stuck** iff none of its nodes is ready, running, reclaimable, waiting or needs_human, **and** none of its blocked reasons is a named wait on another goal. The named waits are:
- a dependency that is open and not stuck ("waiting: G1001 integrate", "waiting: G1001 merge");
- a dependency that is held ("waiting: G1001 held"): holding a goal is the human's own decision, so its dependents are not asked about it again (`econ:M5`);
- dependencies that conflict with each other, until the stack set combines cleanly, which the dependencies' own progress brings about (`deps_conflict`, §3.16);
- a dependency whose goal schema this engine does not know ("waiting: engine upgrade", §3.10).

So a goal that is simply waiting for another goal is not stuck. A stuck goal produces one human item that names the first blocked node and its reason, with exact commands for the options: for a dependency that is stuck, cancelled or invalid, or closed done without the node a dependent reads, **drop** it, **retarget** it, or **cancel** the goal; for other reasons, reopen or unskip the producer, or cancel. This replaces the separate cancelled-dependency and invalid-dependency rules of revision 4.

**A closed dependency never looks open** (`evo:H1`). Only an open dependency gives an open wait. For a dependency closed as done, a node it has no record for resolves as if skipped: `null` when the input is optional, otherwise a stuck reason with drop and retarget commands. `base`'s dependency merge commits are optional, and `base` treats only an open or held dependency as unmerged, so a goal closed done without a merge never holds its dependents back and is never stacked on.

**Closed `done` means delivered** (`m4:F1`). A goal may be closed with reason `done` only when every terminal node is current; otherwise the reason is `superseded` or `cancelled`, and its dependents get the ordinary stuck item.

**An open goal whose terminal nodes are all current** (possible after a change to `terminal`) gets one item with the command that closes it (`evo:M3`).

**Runaway guards** (per goal, SPEC §4.10):
- **Correction budget.** With required round_budget (G1039), each actor stage has a default limit 10 on done agent rounds that add a new material finding, excluding narrowings/notes and pure semantic-free redefinitions. Reaching the stage limit blocks its agent starts/reclaims, while the other stage, ops and human items continue. Base-only stale runs with no checkpoint output are exempt even when they raise a finding; checkpoint producers are not. Counters keep inherited values. Without the capability the legacy total 3×agent-count re-run rule/shape remains (SPEC §4.10).
- **Crash-loop cap.** An expired lease whose attempt is at least the record attempt + 3 becomes a human item instead of reclaimable: one more try with `--force`, skip (not offered for a terminal node), or cancel (R4 M1, `x2:L8`). Abandons count too, because `abandon` leaves an expired lease rather than deleting it (§3.7).
- **Repeat cap.** When a node's last three records are blocked waiting for an agent, whatever reason the agent gives, the node is `needs_human (crash_loop)` instead of `ready (retry)` (`model:M3`, `m4:F4`). This stops, for example, a `base` that is run again and again while a rebase is still in progress, or an agent that rephrases the same blocker. The cap covers `waiting_for: agent` only: time waits have their own timeout (§3.9), and dependency waits, `deps_conflict` included, end through their inputs (`x:M10`). Likewise, when an op's last three done records carry an open finding with the same id and its inputs were unchanged across them, the op is `needs_human (crash_loop)`, which bounds any op-to-op loop in which nothing changes (`m4:F1`, `x2:L5`). A finding that recurs after the op's inputs really changed starts the count again, so a check that fails again after a fix, or `dev` moving again during the merge window, is not a loop (`x2:M2`). One more try is `start --force`; for an agent node of a goal over its correction budget, the item prints the budget raise first, so its option is never refused (`m5:N4`).

**Properties.**
- **Pure:** no I/O, and identical arguments give byte-identical results.
- **No dead ends:** every open, non-held goal yields an action, a human item, or a wait that names a time, a release gate, a running phase, a goal it depends on that is open or held, dependencies that conflict with each other (`deps_conflict`), or an engine upgrade.
- **Held goals** are evaluated and reported, but offer no actions or human items; their running phases may finish.
- **Closed goals** are not evaluated; dependents read their final records.
- **Scheduling across goals** is §3.12.

### 3.7 Phase lifecycle and leases

**A lease is an empty commit** (empty tree) on the branch `zzzops/lease/g<id>/<node>`. Its committer date is the claim or last-renewal time, from the local clock; engine-written dates use Git's `@<seconds> +0000` form (SPEC §1.4). Its message carries the goal, node, attempt, holder, timeout, start reason, a random nonce, the work-branch tip at claim, the input fingerprint (with its parts) and the prompt blob (SPEC §3.8), for example:

```
zzzops lease G1002 implement

Attempt: 3
Holder: claude:0a0a0a02/implement-1
Timeout: 120
Reason: reopened
Nonce: 4f0a91c2e6b7d853
Work: 8c2e5a1…
Input-Fp: v1:sha256:5b1e…
```

- **The lease fields are trailers.** Unknown trailers are ignored, so a later engine can add one without older engines misreading the lease. An unparsable lease is excluded from the frontier and reported by `validate`; it is never deleted automatically (`evo:M6`).
- **The nonce makes every claim unique.** Two claims built from the same bytes in the same second would otherwise be the same commit, and both create-only pushes would report success. With the nonce, exactly one wins (`harn:H1`).
- **The lease carries its own `Timeout`.** Staleness always uses the lease's value, so a later policy or graph edit never retroactively expires or extends a live lease (R4 M9).
- **The lease handle is the attempt number**, `--attempt N`, which survives `renew` (a renewal is a new commit with the same attempt). The CLI checks it against the lease tip from its own fetch (R6 F2, R5 C3).

**The lease prefix makes fetches small.** Every lease name starts with `zzzops/lease/`, so the coordinator fetches exactly the leases with one glob. Measured: 3 refs advertised, against 364 for a `zzzops/*` glob (R1 M1).

**Every push names its expected old value explicitly.** It is taken from this invocation's own `git fetch --porcelain` output, never from shared remote-tracking refs that other processes update. The bare `--force-with-lease` form destroyed a concurrent reviewer's commit in experiment (R1 H2).

| Verb | Precondition (on freshly fetched refs) | Effect |
|---|---|---|
| `start G X [--as L] [--reclaim] [--force]` | X is `ready`; or `reclaimable` with `--reclaim`; `--reclaim --force` also takes a live lease or one at the crash-loop cap; `--force` alone gives a repeat-cap `crash_loop` node one more try. Review nodes: L ≠ the subject record's holder. Workspace nodes (agents or ops): no other workspace lease is live on this goal, and with `--reclaim` the local goal worktree is clean unless `--force`. Agent nodes: capacity is available and the correction budget is not exhausted. No blocking policy branch exists; the engine's version is within the allowed range (§3.10); during a mass expiry, reclaims need `--force`. The full refusal order is in SPEC §6. | Create-only push of the lease commit (attempt = max(record attempt, lease attempt) + 1). Workspace nodes: ensure the goal worktree and sync it (§3.9). **Agent nodes** get the task card (below). **Op nodes** run to completion in the same process: claim, run the operation while renewing its own lease every quarter of its timeout, and finish exactly like `submit` (SPEC §5.1). |
| `submit G X --attempt N [--as L] (--output F [--artifact F] \| --blocked F)` | The valid lease has attempt N and was not abandoned (an abandoned lease, `Timeout: 0`, refuses with `superseded`: "this phase was abandoned"; `x:M5`). The output passes schema and structural checks: `responses` for every live finding targeting X, review coverage (§3.8), I1/I2, `preserve` for checkpoints, and no single output text over 4 KB (`too_large`: "put long text in the artifact"; `evo:M8`). A checkpoint left out defaults to HEAD, even when the phase added no commit. The preserved node's change is scoped to its frozen paths, derived before identity calculation, so test fixes can follow implementation without a rewrite. Explicit full-sha ancestor overrides remain. New agent commits cannot be merges, must have conventional subjects, preserved-node commits must be test:, and preserving-node commits may not touch frozen paths even transiently (G1038; SPEC §4.14–§4.16). | **One atomic push**, each ref with an explicit expected value: the work branch (code commits and/or the artifact commit; the first artifact submit creates the branch at the fetched integration tip, create-only), the goal ref (the record `{status, ok, attempt, holder, input_fp and its parts from the lease, output, findings, prompt, finished_at}`), and deletion of the lease. **`--blocked F`** records a blocked outcome instead: `{waiting_for: human\|agent, question\|instructions, options?, recommendation?}` (R5 C7). If the lease was reclaimed meanwhile, the whole push is rejected and the late work stays only in the local worktree; the error is `superseded`, with the salvage commands (§3.9). A server-side refusal is not contention: see "Goal writes" below. Any other rejection is contention: the CLI re-fetches and re-applies the whole submit. A lost response is detected (lease gone, record attempt = N, record holder = the caller's label) and reported as applied. Returns `next --goal G`. |
| `renew G X --attempt N` | The valid lease has attempt N and was not abandoned (else `superseded`). | Pushes a child empty commit. Nothing else: work in progress is pushed only by `submit` (or by hand, `REPAIR.md`). |
| `abandon G X (--attempt N \| --force --note T)` | The valid lease has attempt N, or `--force` by anyone. | Pushes an expired renewal (`Timeout: 0`); it never deletes the lease. The next `start` is therefore a reclaim with a new attempt, and abandons count toward the crash-loop cap (`model:M3`, `cons:H3`). A forced-off agent's late `submit` or `renew` is refused with `superseded` at once, even before anyone reclaims (`x:M5`). The previous record, if any, is untouched. `--force` records the note in the goal's history. |
| `answer G X --fp P --file F` | X is a human node awaiting its decision, X has a blocked record waiting for a human, or X carries an escalated dispute; and P equals the item's current input fingerprint. | Records the decision (§3.13), the answer to the blocked record, or the dispute decision (uphold or waive; for a finding carried by an op: uphold, skip or cancel, never waive, because waiving cannot make a check pass; the item also offers `reopen G <op>`), with no lease. If the fingerprint changed, it refuses with `fp_mismatch` and shows the current question (R4 H1). |

**The task card** is the `start` output for agent nodes, at most 4 KB (SPEC §3.14, §4.20). It contains the prompt, the node's selected instruction sections, its inputs and context (values inline when short; longer values by blob with a summary), every live finding targeting the node, the workspace path, the output schema, commands for reading `dev` without a worktree, and the exact `submit`, `submit --blocked`, `renew` and `abandon` commands.
- **Renewal:** one number, stated as "renew every N minutes (timeout T); after any pause, renew first" (R8 #7).
- **Commands to run:** a workspace node's card lists its command inputs with "run these before you submit"; for `implement` that is `test_design.commands` (R8 #6).
- **Re-reviews** get previous findings with responses, plus a scoped interdiff: same base uses git diff, a moved merge-mode base uses a first-parent no-merges patch log, and legacy rebase mode uses range-diff. `previous.syncs` separately exposes each sync via remerge-diff, so its resolution is never hidden by range-diff skipping merges. An identical change omits interdiff; missing objects disclose the need to review in full (G1038; SPEC §4.20).
- **Size:** long inputs are referenced by blob with a summary, so the card stays within 4 KB (R8).

**Goal writes** (`submit`, op `start`, `answer`, `reopen`, `edit`, `new`) are compare-and-swap pushes to the goal's own ref (SPEC §4.4):
- **Build:** the new goal commit is built with plumbing on the fetched tip, with an `Engine: <build id>` trailer, a `State: <open|held|closed>` trailer, and one `Outcome:` line built from the record being written, for example `changes_requested: 2 findings → implement`, `waiting until 14:35: required checks pending`, or `closed: done (PR #1187, 5a1c2d3)` (`econ:H5`). So `git log` of the goal branches answers "what happened since T".
- **On rejection:** re-fetch. If every expected value is unchanged, nothing moved, so the rejection was a server-side rule or hook: the CLI refuses at once with `push_refused` (exit 2), printing the remote's messages and the refused refs (`gen:H2`). Otherwise it is contention: re-apply the *operation* (not the file), re-check preconditions, and retry with jittered exponential backoff up to a 30 s deadline. A whole-document edit is never re-applied over a concurrent change (§3.11).
- **Hooks** (`gen:M5`, `harn:M4`; SPEC §4.1): pushes whose refs are all goal, lease or stack refs use `--no-verify`, so a repository's `pre-push` hook does not run on every lease and goal write. Pushes that include a work or PR ref keep hooks, because git-lfs uploads its objects from `pre-push`; the repository's `pre-push` hook therefore runs on those pushes. Every other engine Git command runs with an empty `core.hooksPath`.
- **Throughput:** writes to different goals never contend, so the single-ref write ceiling measured for revision 4 is gone (R3 F13, R1 M3). Only concurrent writes to the same goal retry.

**Lease rules.**
- **Staleness:** `now − tip committer date > the lease's Timeout`.
- **Reclaim:** after expiry, anyone may `start --reclaim`, which creates a new attempt.
- **Late submits** are fenced out by the atomic push.
- **No liveness evidence:** no heartbeat daemon, no "observed stopped" text.
- **Orphan leases** (node not in the current graph, a record with ≥ attempt exists, unparsable message, or goal closed) are excluded from the frontier and from capacity, and `validate` reports them. No write prunes them. The generic close deletes the goal's leases, and `REPAIR.md` has the one-line delete for the rest. **A held goal's leases are not orphans:** `hold` lets running phases finish (R7 H5).
- **Capacity:** `count(live agent leases) < settings.parallelism.max_workers`. Ops do not count. Best effort: concurrent starters can briefly exceed it.
- **Clock:** a lease tip dated more than 5 minutes in the future produces a warning, never a refusal. If at least three leases, and more than half of all leases in progress, look expired at once, reclaims require `--force` (R7 M5, R3 F14). The warning names a sleeping laptop as the likely cause, and the skill may reclaim its own session's labels with `--force` without asking (`econ:L3`).

**Holder labels** have the form `<tool>:<id>`. They are minted by the dispatcher, not discovered by each agent (`harn:H1`):
- the root's `--as` defaults to `codex:<CODEX_THREAD_ID[:8]>` or `claude:<CLAUDE_CODE_SESSION_ID[:8]>`;
- the dispatch skill gives each worker `<root label>/<node>-<k>` in its prompt, because a Claude Code subagent shares its parent's session id and cannot learn its own.

Uniqueness is not a correctness requirement: claims carry a nonce, every lease verb names the attempt, and lost-response detection requires the holder to match.

### 3.8 Reviews, findings and corrections

**Findings across a block (G1040).** With capability `blocked_findings` required, an agent's blocked record retains the replaced done output as `last_output` (copied through a second block). Only frontier pass 1 views it as done, for recorded inputs, subjects, filter fingerprints and target liveness; pass 2 still blocks consumers. A review that saw that output stays fresh, including op findings, while a genuinely changed spec or older reviewed output remains stale. The exact target fingerprint prevents old answered findings from returning. Older-mode writes and op Blocked records do not gain this key. Requiring the capability must be paired with the revised design step 4 so an answered owner question is answered as a correction rather than blocked again.

- **Findings are judged against their target, not their carrier (G1028).** An open finding of a review whose own inputs changed (a spec or `depends_on` edit, a sibling finding that reopened an upstream node) stays live while the output it names is unchanged, marked `stale_review` on the target's card; only op findings, which re-observe, are dropped. A partly fixed finding is resolved and followed by a new one (`follows`), which keeps the dispute count but never `upheld`.

**Review output** (agent or human): `{decision: approved|changes_requested, summary, findings: [...], report?: artifact}`. The record's `ok` is `decision == approved`.
- Agent reviewers also pass `--artifact report.md`.
- Human review nodes (`approve_design`, `approve_merge`) use the same shape, plus the decision record fields `decided_by`, `quote` and `decided_at`. So **a human rejection reopens the subject through the same rule as an agent review**, with the human's words as the correction (R2 #28/#29). Cancelling outright is an `edit` that closes the goal.

**Artifact commits** (`docs(review): <node> for G<id>`):
- **Plumbing only:** the CLI adds the file to the tree of the observed work-branch tip with mktree, runs `commit-tree`, and includes the result in the submit's atomic push. If the work branch does not exist yet, the commit's parent is the fetched integration tip and the push creates the branch (create-only).
- **Parallel reviewers write distinct paths** (`<node>.md`). On contention, the artifact commit is rebuilt on the new tip, then retried; four concurrent reviewers all landed in experiment (R1 D).
- **Identical blob already at that path:** no new commit is made.

**Finding:** `{id, target, target_fp, target_attempt, text, status: open|resolved|waived, response, rounds, upheld, note}` (SPEC §3.6). Findings live on the carrying record, never in its output.
- **Ids are fixed:** `<carrier>:<attempt>:<k>` for agent and human findings, `<carrier>:<key>` for op findings (for example `integrate:check-lint`), `<node>:reopen:<n>` for reopen findings.
- **`target`** defaults to the review subject and may be any ancestor of the carrying node; a reopen finding targets the node itself.
- **`target_fp`** is set by the CLI at submit to the fingerprint of the target's full recorded output, but **only if the submitting lease's input fingerprint equals the current one (the fingerprint carried by the node's `running` state, §3.6), and the target's record finished no later than the lease was claimed**. Otherwise it is `null`, never live, because a stale review must not reopen newer work (R1 H4d, `model:L2`).
- **`target_attempt`** is the attempt of that same target record (`null` with `target_fp`). It tells whether an op target has re-run since the finding was raised without comparing clocks across machines (`x2:M3`).
- **Any node's record may carry findings.** `run_tests`, `integrate` and `merge` raise them on failure, targeting the producer of the input concerned.

**Findings rule.** A finding is **live** iff all four hold, judged in the frontier's first pass from recorded outputs only:
- its carrying record is the latest record of a node in the current graph;
- that record's `input_fp` equals the node's current input fingerprint (skipped for a reopen finding, whose carrier is its own target, so a reopen of a stale node is not silently dropped; `model:M5`);
- its status is `open`;
- its `target_fp` equals the fingerprint of the target's recorded output, and, when the target is an op, that op has no later attempt than the one the finding was raised against (`target_attempt`; no clock comparison, `x2:M3`). An op answers by re-running, even when its output is byte-identical; the carrier then decides again, bounded by the op-finding repeat cap (H22).

A node with live findings targeting it is **reopened** (R2 R9). Its task card carries every one of them.

**Termination without new topology.**
1. A reopened node must submit `responses: {finding_id: "fixed: …" | "disputed: …"}` for every live finding. That is a structural check, so a resubmit cannot be byte-identical (R1 H4c). Ops and human nodes, which cannot write prose, get automatic `fixed:` responses when they re-run.
2. Its output therefore changes. `target_fp` no longer matches, so the findings die. The reviewer, now non-ok with no live findings, is `ready (not_ok)` and runs again. If the fix changed the code, the reviewer is also stale through `change`.
3. The re-reviewer receives its previous findings and the interdiff as context. It must give every prior open id a status, and `approved` requires none open.
4. **Findings that no longer apply release the carrier.** A non-ok record whose findings have all died is `ready (not_ok)` (§3.6). For example, a failed required check answered by `disputed: flaky` makes `integrate` run again.
5. **Persistent disagreement** (`cons:M1`, `cons:M2`, `model:M2`, `model:L4`):
   - A dispute the reviewer keeps open produces a human item: "uphold or waive F?". Precisely, a carried-over finding whose response is `disputed:` and whose `rounds` is at least 2. New findings start at round 1. Rephrasing a finding does not escape the bound, because the applicable correction budget remains the aggregate bound.
   - An op finding whose id recurs also escalates. Recurrence is read from the target's recorded `responses`: the target's current output answered the same id with `fixed:` or `disputed:`. That survives the blocked records an op writes between failures.
   - An op's blocked record carries the previous done record's findings unchanged and inert (only a done record makes findings live), so `upheld`, notes and rounds survive CI polls (`m4:F10`).
   - Only agent targets escalate. The engine's automatic `fixed: re-run by <op>` responses never count, so a routine second `dev` move during a merge does not reach the human.
   - Findings carried by a human node never escalate: a human re-raising a finding has already decided.
   - A dispute item for a finding carried by an op offers uphold, skip (unless the op is terminal; `x2:L8`), `reopen G <op>` (for a flaky check) or cancel, never waive.
6. **Total bound:** the applicable correction budget (§3.6) asks the owner to continue/hold/cancel: per actor stage at >=limit under round_budget, legacy per-goal totals otherwise. Per-finding dispute and crash/repeat caps remain separate.

**Manual corrections.**
- `zzzops reopen G X --note "…"` writes a reopen finding on X's record. It also sets X's **own** open findings to `waived`: re-running X from scratch withdraws what X last said (`econ:H3`).
- Waiving is `zzzops edit` (status `waived` with a note).
- Re-running a single op, for example to re-read flaky checks, is `reopen G integrate --note "…"`. Because the reopen waives `integrate`'s own check findings, `implement` is no longer reopened, and `integrate` runs again without an `implement` run. The skill says: if an `implement` card's only corrections are `integrate:check-*`, read the failed log (`gh run view --log-failed`) first; if it is a flake, reopen `integrate` instead of editing code.

All of these are visible edits, not ceremonies.

**Lenses, the filter and notes (G1000, G1020).** The default graph reviews each subject with seven independent lenses (§4.1), and a filter node per subject joins them. A lens gives every finding `impact` (what goes wrong if it is ignored) and its own `material` claim. A finding reopens its target if the lens claims it is material **or** the filter keeps it. So the filter may promote a note but never demote a material claim; demotion goes through the existing dispute path. The filter has no demotion power because, in the lens experiment, a blind filter with that power dropped 9 of 16 harmful issues, which would recreate the failure mode of an authority that drops findings. Self-labelling alone also lost harmful issues (2 of 16 on the draft, 3 of 8 known defects on the replay), so the filter judges every note.
- **The filter is the join.** Lens findings go live only once the filter has a fresh record, so the subject reopens once per round, with every finding. The filter's freshness covers the candidates themselves, not only the lens summaries: a lens that re-runs and adds, closes or relabels a finding stales the filter even when its summary did not change.
- **Notes** are non-blocking: they never reopen work or count against the budget, the target's card lists them, and approval items show them grouped by lens. A lens whose only open findings are notes answers `approved` (G1020), because "approved plus non-material findings" is exactly a notes-only lens.
- **Skips:** a node field `skippable` (default true) protects the intent and simplicity lenses, the filters and `approve_merge`. A lens cannot be skipped while it has an open finding that is not a note, so the objecting lens is never skipped silently; its findings must be waived visibly first.
- **Project intent** is `settings.intent`, a declared policy input of the intent lenses, so a change to it stales their reviews.

**One reviewer, several lenses (G1022).** The shipped graph no longer runs one agent per lens. Each subject has one multi-lens reviewer that works through its lenses one pass at a time (`lenses` on the node, SPEC §3.1), because every separate lens agent repeated the same discovery reading. On G1016 attempt 1 with 6 planted defects and 1 real one, a single reviewer with the lenses compliance, correctness, missing, tests and craft found 7, 7 and 6 of 7 at 82–87k tokens. Five separate lenses found 6 of 7 for 337k, and the seven design lenses copied to code found 6 of 7 for 436k. Only the multi-lens reviewer found the real defect, which lay outside the diff, through its Missing lens (2 of 3 runs). At design the evidence differs: one multi-lens reviewer found 4 of 12 known defects per run, against 7 of 12 for seven separate lenses. One multi-lens run plus a separate `adversary_design` reached 7 of 12 for about 76k tokens instead of about 245k. So the design subject keeps the Adversary as its own node (G1000's lens node, unchanged), and the implementation subject has no second reviewer.
- **Lens selection reuses skips.** A goal removes a lens with `skip["<node>:<lens>"]`, so a reason is required, non-skippable lenses are refused, and approval items and the PR body list it. The reviewer node still runs, so a lens skip drops no finding and needs none of G1000's open-finding refusal. The node and lens names are the project's; the engine names none.
- **Freshness.** The applied lens list is a fingerprint part (`lenses`), so un-skipping a lens re-runs the reviewer; like `def`, it does not count against the budget. Compliance acts as the implementation stage's Intent lens; project intent is judged once, at design, so an intent change does not re-run the five-lens implementation review on every open goal.
- **Re-review:** `reviewed` also records the subject's artifact blobs, on a fresh submit only, and the card points at `git diff <old blob> <new blob>`.

**Owner questions (G1026).** Approvals may be delegated, but some choices still belong to the owner: those whose undoing, if they turned out wrong, would reach outside the goal's own change (other goals, users' repositories or installed policy, stored formats, names or outputs others consume, external systems) or would change what the product does or the project's direction, unless one option clearly dominates. The test is a POLICY instruction (`owner_questions`), so a project can tune it. A reviewer raises such a choice as a material finding on the design whose text starts `owner question:` (the engine refuses a non-material one from a filtered lens). The designer does not decide it: it submits `--blocked` with every owner question of the round, the root batches them across goals and asks the owner, and the answer comes back on the retry card. The revised design quotes the owner's words, and the re-review resolves the finding against `human_decisions` on its own card, which the engine reads from the goal's `answer` commits rather than from the designer's text. Approval items and the PR body list every human decision with who gave it, so a delegated approval still shows what the owner decided. Nothing new is stored, and delegation is unchanged.

### 3.9 Goal worktree, operations and outcomes

**One work branch and one local worktree per goal per machine**, at `<primary>/.zzzops/worktrees/g<id>`. Workspace nodes, agents and ops alike, use it, and at most one workspace lease per goal is live at a time.
- **The work branch is created lazily.** The first artifact submit (normally `design`) creates `zzzops/work/g<id>` at the fetched integration tip, create-only, in the same atomic push. `base` creates it at the stack base if no artifact has (`x:M9`).
- **Discovery creates no worktree.** Discovery agents read `dev` with `git show`/`git grep` on the fetched integration tip, or browse the coordinator mirror; the task card prints the commands. The first workspace node, normally `base`, creates the goal worktree. A backlog in discovery therefore costs no worktrees (R6 F5).
- **Reviewers never need a worktree;** they may read the work branch or make their own detached scratch checkout.

**Closed goals' worktrees are removed opportunistically.** After any successful mutating verb, the CLI removes at most one local goal worktree whose goal is closed in the snapshot, if it is safe: clean, and its local tip equals the remote work-branch tip. That rule does not depend on the merge method (`evo:M9`, `gen:H3`).

**Sync rule.** It applies at workspace `start` and `submit`, and inside ops that use the worktree. The fetch includes the goal's work branch; then, in order (SPEC §4.13):

| Situation | Action |
|---|---|
| No remote work branch yet | This verb's push creates it |
| Local and remote are equal | Nothing |
| Local is behind the remote | Fast-forward |
| Local is ahead of the remote | Push (fast-forward), in this verb's atomic push (R5 C2) |
| Every remote-only commit is `docs(review):` | `git rebase origin/<work>`. This is conflict-free under I1/I2 and preserves `tree` (R1 M5). |
| Every local-only commit is patch-equivalent to a remote one (for example after a `base` rebase elsewhere), judged with `git patch-id --verbatim` so a whitespace-only difference never counts as equivalent (R4 M4) | `git reset --keep origin/<work>` |
| Anything else | Refuse with `sync_refused`, listing the commits on each side. This is genuine divergence: someone's unpushed work. |

**Superseded local work.** The `sync_refused` error carries the exact salvage commands: save the local commits on a local branch `zzzops-salvage/g<id>-<node>-a<attempt>`, then `git reset --keep origin/zzzops/work/g<id>`, and tell the human what was saved. Nothing is pushed. `REPAIR.md` has the same recipe (R8 #1).

**Operation outcomes** (R2 R5). Every operation ends in one of three ways:
- **`done`** with an output and `ok`. Failures are `done` records with `ok: false` carrying findings.
- **`blocked`**, with `{category: conflict|external|decision|dependency|capability, waiting_for: agent|human|time|dependency, reason, instructions, retry_after?}`. The record is written and the lease released. The frontier shows `time` waits as `waiting` until `retry_after`, and `dependency` waits as a named wait on the dependency goals. `agent` and `human` waits become actions or human items with the instructions inline.
- **Every time wait times out** (`model:M3`, `evo:L2`). It carries `pending_since`, backs off to 30 minutes, and becomes a human question after `settings.verification.ci_timeout_minutes`. That covers CI, `merge`'s mergeability and GitHub-block waits, and `gh` errors alike.
- **Ops cap their own text:** `details` is at most 4 KB, with log tails cut first, so an op can never fail its own finishing push on the document size limit (`evo:M8`).
- **Crashed.** The process dies; its lease expires within the op's `timeout` (default 15 min); `start --reclaim` retries, and the crash-loop cap stops repetition. Every op is observe-first, so retrying is safe.

| Op (default node) | Inputs | Behaviour | Output |
|---|---|---|---|
| `git.base` (`base`) | Dependency PR heads/merge commits; design/approval summaries as context | Select the stack base as below. Require merge_sync to merge target into work with explicit old base; preserve conflict resolution in a fast-forward work update and carry eligible checkpoints in the same atomic push. Without it, retain legacy rebase/map carry. A branch with sync merges blocks before any rebase when the requirement is removed. Merge conflicts are edited against the recorded conflicted tree; agents do not commit them (§3.16; SPEC §5.2). | `{branch, base_commit, stack, replay_map, replay_pos}`; extra unfingerprinted `synced` in merge mode |
| `checks.run` (`run_tests`) | `code` = `implement.code.tree`, `commands` = `test_design.commands`; `policy: [verification.commands]` | Clean worktree, and `code_tree(HEAD)` equals the `code` input (tree equality, not commit equality; R1 H4f). Runs the goal's commands, then `verification.commands`, within `verification.timeout_minutes`. Commands run under a POSIX shell on every platform (Git for Windows' `sh` on Windows), in their own process group, and the worktree is cleaned however the run ends, so a timeout leaves no stray processes and no dirty worktree (`harn:M1`, `harn:M3`). On failure it raises a finding targeting the code producer, and `ok` is false (SPEC §5.3). | `result {passed, tree, details}` |
| `git.integrate` (`integrate`), includes CI | Code tree, recorded base and stack; reviews and design as context; required checks policy | Check exact code tree, identity rules and policy paths. Build tests then implementation commits on the recorded synced base by tree overlays; omit empty parts. Exclude review and prior dependency/base history, derive conventional release subjects from own implementation commits, and give the final head the newest date. Reuse an unchanged PR head before assigning new dates. Push only the engine PR branch, update conventional title/body/base, and enforce CI on PRs into the goal target. Stack checks remain informational; conflicts reopen base; failed required jobs rerun once before a finding, waits back off and reach the owner as before. Work history is untouched (§3.16; SPEC §5.4). | `pr {number, url, head, tree, base}`, `ci {required, passed, failed}` or `ci {stacked: true, checks}` |
| `github.merge` (`merge`), `release_gate` | `pr` = `integrate.pr`; approval, `base` and `goal.links.issue` as context | **Waits** until every dependency is merged and `integrate`'s record has the integration branch as PR base with required checks passed ("waiting: G1001 merge"). By then `base` has restacked onto the integration branch and `integrate` has re-run. If every dependency is merged but the PR still targets another base (as recorded, or as read on GitHub before merging, for a PR retargeted by hand; `x2:L9`), that is `blocked {waiting_for: human}`, not a finding, so `merge` and `integrate` cannot loop (`m4:F1`). **Observe** (reading the PR's `baseRefName`): if the PR is already merged (for example by the human on GitHub), record it, flagging a different head in the summary; merged code with a different tree, or a PR merged into a base other than the integration branch, is a question for the human (`evo:M1`, `x:M7`). A PR closed without merging, or whose head moved, is a question for the human. **On a merge conflict** (or a dev ruleset requiring an up-to-date branch): a finding on the producer of the `base` input, which reopens `base` and syncs in its selected mode. **GitHub blocks the merge** (required reviews, checks, signatures or a merge queue): `blocked {category: external, waiting_for: time}`, retried every 30 minutes, then a human question after `ci_timeout_minutes`; a PR already queued or set to auto-merge is waited on, never merged again (`gen:H3`). **Otherwise:** `gh pr merge --<settings.merge.method> --match-head-commit <head>` with a conventional subject/body for merge or squash (no message flags for rebase), then re-observe (SPEC §5.5). **Once the merge is observed**, whether this op merged it or the human did on GitHub, retarget every open PR whose base is `zzzops/pr/g<id>` to the integration branch (`gh pr list --base`, then `gh pr edit --base`), and close `links.issue` if set. Retargeting only after the merge means a refused or queued merge never leaves a dependent PR into the integration branch showing the unmerged dependency's code (`m4:F2`, `m4:F7`, `x:L13`). **`merge` deletes no branches:** GitHub's automatic head-branch deletion removes the PR branch, and the work branch is kept, so artifact blobs stay reachable for dependents (R7 H6, R6 F3, R4 M5). The goal closes by the generic rule (§3.11) in the same push that records the merge. (SPEC §5.5) | `{merge_commit, merged_at}` |

**Test-freeze (`preserve: test_design`)** (SPEC §4.16):
1. The `test_design` record carries `frozen`, a path list that is not fingerprinted (`model:H2`).
2. `frozen` is the previous record's `frozen` plus the paths changed by the commits this phase added. The lease records the work-branch tip at claim (`Work:`), and the added commits are those from that tip to the checkpoint. After a rebase the checkpoint is an ancestor of that tip, so nothing is added. So a tests fix made on top of `implement`'s commits never freezes `implement`'s own files.
3. `implement`'s checkpoint must leave each frozen path exactly as the tests checkpoint has it, and none of its new commits may touch that path, even if a later commit restores it.
4. A violation is a submit error (`test_freeze`) naming the files. The route: restore them; if a frozen test is wrong, keep it unchanged and raise a finding on `test_design`.
5. Carry-forward (§3.16) copies `frozen` unchanged. The preserved checkpoint's change and tests review view use only F; implementation review views exclude F, while code.change still binds all delivered code/tests. The scope is derived, not stored.
6. Default checkpoint is HEAD. A tests fix after implementation is a normal test: commit, accepted in place. Only paths from the test phase's own commit range join F. A no-commit test rerun does not change tests.change when F is unchanged (G1038).

**Measured verification (G1043).** checks.run still proves the exact recorded tree and runs every goal/repository command. Default ordering stays serial; optional verification.parallel_commands is an explicit declaration that two ordered lanes can share this checkout safely. It needs capability test_cost, and each checks node declares both verification.commands and verification as policy. A single parent-capped CPU total is divided before starting lanes; single-CPU/empty-lane cases stay sequential. A shared timeout kills/joins every child before one cleanup, and failure reporting keeps original command order. Third-party commands may ignore the exported worker budget; no OS enforcement or automatic shell coverage is claimed.

Durable command/total timing uses integer milliseconds. One bounded lookup of existing accepted goal evidence identifies the newest tested code tree actually merged onto the captured goal target's first-parent history. Independently qualify total workload and repository workload hashes/environment against that same source. Different targeted commands can leave the total comparison unavailable while preserving a useful repository delta; show each qualification/provenance and the machine/concurrent-workload caveat. Missing evidence is unavailable, not zero, and a newer mismatch never selects an older convenient source. Caps/deadline cover Git work too (SPEC §5.3), so informational history cannot hold successful checks indefinitely. No timing database/service/index or second trunk test run is added; timing never renews approval identity or gates regressions.

A command timeout has a fail-closed recovery boundary: group termination failures or pipes that remain open after bounded draining preserve the worktree and produce an external human block. A successful parent kill alone cannot justify resetting a checkout while descendants may still run.

### 3.10 Coordinator and policy

**Every invocation runs this preamble** (SPEC §4.2–§4.5). It talks only to the Git remote, never to the GitHub API.
1. **Read configuration and check the environment.** `remote = git config zzzops.remote || origin`; `integration = git config zzzops.integrationBranch`, else the remote's HEAD branch. POLICY.json `settings.integration_branch` must equal it, checked on every verb: a clone configured for the wrong branch refuses with `wrong_integration_branch`, naming the `git config` command to run (`evo:M5`, `gen:M2`).
   - Git must be at least 2.41 (for `fetch --porcelain`). `gh` is checked only by the ops that need it, with a version floor and `gh auth status` (R4 L3, `harn:M5`).
   - The harness must allow network access and Git-directory writes (§3.17). The CLI refuses with `environment`, not `remote`, when `CODEX_SANDBOX_NETWORK_DISABLED=1` is set or a write probe of the Git directory fails (`harn:C1`).
   - A shallow clone is refused with `environment`. A partial clone gets a `partial_clone` warning, and the docs say to use a full clone (`gen:M3`).
2. **Fetch.** One `git fetch -v --porcelain --no-tags` of the integration branch, `zzzops/goal/*`, `zzzops/lease/*` and `zzzops/policy/*`. A verb that touches one goal also fetches that goal's work, PR and stack branches in the same command, and `start G base` also fetches the unmerged dependencies' PR branches there, so `base` needs no second fetch (`x:M12`); no other goal's branches are fetched.
   - The porcelain output is this invocation's ref snapshot. `-v` makes it list every matching ref, so it is complete.
   - The benign `cannot lock ref` error, which concurrent fetches on one machine hit 7 times in 8, is retried up to 3 times with jitter (R3 F5).
   - If the fetch fails: mutating verbs exit 2 with the git error; read-only verbs (`next`, `show`, `validate`) run on the last fetched tips, marked `current: false`, and report leases and policy branches as unknown, because stale local copies of them would show phantom leases and blockers (`evo:L3`).
3. **Per-goal descendant check.** Goal refs are fetched with a refspec that has **no `+`**, into a private local namespace, so git itself refuses a non-fast-forward update of a goal branch. That refusal is reported: the goal is read at its last accepted tip with a warning, and writes to it are refused, while other goals are unaffected. A goal ref that disappears from the remote is treated the same way (R2 #36). The fix is a forward commit descending from both tips (`REPAIR.md`). Repositories should also add a ruleset blocking deletion and force-push on `zzzops/goal/**` (a setup step).
4. **Read and validate policy** by object id at the `<integration>` tip: `POLICY.json`, `workflow.json` and prompts.
   - When `<integration>:.zzzops/workflow.json` is missing, every verb reports `not_bootstrapped`, naming the bootstrap skill (§3.17), not `policy_invalid`.
   - `schema_version`, `settings.engine.requires` and the deprecated `settings.engine.min` are read tolerantly first. If the engine lacks a required capability, or the policy schema is newer than it supports, the only report is `engine_too_old` ("upgrade the plugin"), so an agent never "fixes" a new key by deleting it (`evo:H4`).
   - Otherwise invalid policy: mutating verbs refuse with the validation errors, while read-only verbs work and show a single global blocker.
   - The coordinator worktree `<git-common-dir>/zzzops/coordinator` is updated best-effort under a file lock, and never fails a verb. In experiment, 19 of 20 concurrent checkouts failed on `index.lock` (R1 H3).
5. **Engine capabilities** (R7 H3, `evo:H4`, `evo:M7`; G1027). Plugins are installed per tool and per machine, so engines of different builds meet as a normal state. A version number cannot describe them: builds from the integration branch all carried one hand-kept number, and goals in flight raced for the next one. So an engine declares named capabilities instead, one file each, and goals add theirs without ordering.
   - **Floor:** POLICY.json `settings.engine.requires` (capability names) is changed through a policy branch like any setting. An engine refuses writes when it lacks any of them, naming the missing ones. The deprecated `engine.min` still works through a fixed map from the numbered engines (1.0.0, 1.1.0, 1.2.0, 1.3.0) to their capabilities.
   - **Older engines** read `requires` as an unknown key and report `policy_invalid`, which pauses work and refuses writes, so they fail closed. That message invites the wrong fix `evo:H4` guards against (deleting the key). It is accepted because policy changes land only through reviewed policy branches, the numbered engines were never released, and MIGRATING, REPAIR and the policy branch's PR body say to upgrade and never remove the key. A high `engine.min` placeholder to get `engine_too_old` from them was rejected: the product's tags are already `v2.x`, and it would bring back a second version number.
   - **No ceiling:** the old compiled-in ceiling could never fire and was removed with `engine.min`. A future engine that cannot coexist with older ones designs that rule with capabilities.
   - **Goal schemas:** an engine reads every goal schema it has shipped and writes the newest when it writes a goal (G1025 refines this: schema 2 only adds the optional `flow`, so a write picks schema 2 for a document with `flow` and schema 1 otherwise, and older engines see only line and hotfix goals as newer; SPEC §4.5). A goal with a schema it does not know is `engine_too_old` for writes to that goal, and its dependents show "waiting: engine upgrade", never a stuck item that offers to drop the dependency.
   - **What ships with a new capability:** a new goal schema; a change to fingerprint, canonical-JSON, `code_tree` or `change` semantics (§3.5); any op `version`; the lease message format; any new POLICY or workflow key, field or op.
   - **Upgrade recipe** (`REPAIR.md`): push `zzzops/policy/requires-<name>` adding the capabilities, which pauses starts; wait until `next` shows nothing running; upgrade the plugins everywhere; land the branch. Rollback is the same procedure removing the names, plus reverting newer-schema documents from the last commit without the new build's `Engine:` trailer.
   - Every goal commit carries an `Engine: <build id>` trailer (plugin version and package revision), so a bad build's writes can be found and reverted (`REPAIR.md`).
6. **Policy-branch check.** If any `zzzops/policy/*` branch exists on the remote that has not landed (its tip is not an ancestor of the fetched `<integration>`, and its `.zzzops/` files differ from `<integration>`'s):
   - `start` refuses, for agent and op nodes alike;
   - `next` lists no actions and returns one global blocker naming the branch, its age, its last commit date and author, how many actions it is pausing, and how to resolve it: "land the branch on `<integration>` and delete it, or delete the branch to abandon the change" (R9, `econ:L1`);
   - everything else still works: `submit`, `renew` and `abandon` of running phases, `answer`, `reopen`, `edit`, `new`, `show`, `validate`, and the human items in `next`.

   A policy branch whose tip is already an ancestor of `<integration>` has landed, and so has one whose `.zzzops/` files equal `<integration>`'s (`git diff --quiet <tip> <integration> -- .zzzops/`), which covers a squash landing (`x:M4`). It does not block, and it is reported for deletion, so unblocking never depends on GitHub's automatic head-branch deletion (`gen:L3`).

   **Stated limitation** (`x2:L7`): the equality test holds only until another policy change lands. A squash-landed branch that was not deleted then fails both tests and blocks new work again, with the "policy change in progress" message. The deletion warning is the mitigation: delete a landed branch promptly.
7. **Report.** Every response carries `{coordinator: {commit, current, policy_branches}}`.

**Default provenance (G1024).** The repository still owns its explicit policy; installing a plugin never replaces it or introduces runtime fallback. Separate `.zzzops/TEMPLATE.json` records per-file last-reviewed normalized blob ids and removed-file tombstones, without a setting, capability or fingerprint. The append-only plugin `templates/history/` store retains old contents for working diffs and three-way merges. `next` gives a compact, non-blocking `policy_update`; every valid `validate` form expands the comparison, apply advice and exact reviewed/inferred record. Missing/invalid provenance is advisory; newer unknown bases are preserved and never offered as downgrades, and tombstones prevent old engines resurrecting removed defaults. All comparisons are local at the selected policy commit/directory, with no network cost/cache; computation failure drops the notice. Updates and record-only declines land through reviewed policy branches. Resolve `policy_merge_markers`, decide workflow.json before its prompts, and never edit TEMPLATE.json in a goal (SPEC §3.2, §3.15–§3.16, §8.3).

**How a policy change works (D11):**
1. Create `zzzops/policy/<topic>` from `<integration>`, edit `.zzzops/POLICY.json`, `workflow.json` or `prompts/`, and run `zzzops validate --policy --dir <checkout>`. Besides the structural checks, it prints the **impact** on in-flight goals: the frontier evaluated under the current policy and under the new one, over all open and held goals, summarized as agent phases staled (by node), human gates re-asked, live leases on changed or removed nodes ("land after these finish"), records and skips orphaned, goals with an unknown graph, and new dead ends or stuck items. The skill pastes this summary into the policy PR (`evo:H2`).
2. Push the branch. New work stops everywhere at the next invocation; pushing the branch *is* the signal.
3. Land it on `<integration>` by whatever route the repository requires. Here that is a PR, because the dev ruleset demands one; GitHub's "delete branch on merge", already enabled on this repo, then removes the branch. In a repository without such rules it could be a plain merge and push.
4. Landing the branch ends the block, since its tip is then an ancestor of `<integration>`, or, after a squash, its policy files equal `<integration>`'s; so does deleting it. The next invocation reads the new policy from dev, and only nodes that declare a changed key go stale.

**Two rules make the branch prefix the only path:**
- Policy edits are not goals: `integrate` raises a finding on goal diffs that touch policy paths, since such a goal would block its own merge.
- Repositories that want enforcement can add one small CI check that fails any PR touching policy paths from a branch outside `zzzops/policy/`. This is optional ordinary repository CI, not engine machinery; without it, a policy change made on a misnamed branch simply isn't noticed until it lands.

**Other rules:**
- The CLI never re-executes from dev.
- A POLICY.json `schema_version` older than the one the installed engine supports gets an explicit refusal; the pre-reset version points to `MIGRATING.md`. A newer one is `engine_too_old` (step 4).
- The per-invocation fetch and every write assume the harness requirements of §3.17.

**POLICY.json stays separate and progressively disclosed** (A2, D13). Its per-section `instructions` texts are selected per node through the node's `instructions` attribute and shown only in that node's task card or human item. Model routing stays an advisory `routing.tiers` table, which lists Claude model ids beside GPT ids in each tier, so Codex and Claude Code get equivalent guidance (`cons:M6`). Moving the instructions into AGENTS.md or CLAUDE.md was rejected, because those files load everything into every context, and per-node disclosure is the point.

**Minimal POLICY.json** (derived from revision 70; schema in SPEC §3.2, shipped template `templates/default/POLICY.json`, requirements in SPEC §8.1):
- **Kept:**
  - `schema_version`;
  - `settings`: `integration_branch`, `engine.requires` (`engine.min` deprecated), `verification.{commands, required_ci, timeout_minutes, ci_timeout_minutes}`, `merge.method` (`merge`, `squash` or `rebase`; default `merge`; advisory for the op, not fingerprinted), `releases.current`, `leases.ttl_minutes`, `parallelism.max_workers`, `scheduling.order`, `goals.first_id`, `routing.tiers` (advisory);
  - `instructions`: one text per former section.
- **Ranges are validated** (R7 M6): for example `max_workers` 1–50, `leases.ttl_minutes` 10–1440, op timeouts 2–240. An out-of-range value makes the policy invalid instead of stopping all work or removing the rate limit.
- **Dropped:**
  - approval, bindings, history, revision, charter, evidence;
  - per-section review and provenance fields;
  - the DAG, which moves to `workflow.json`;
  - `edit.confirm_threshold` (revision 6, A5).
- **Template defaults** (`gen:L6`): bootstrap fills `routing.tiers` for the harnesses in use and sets `goals.first_id` above the highest existing issue and PR number, so `G12` is never confused with `#12`.
- **Project files:** PROJECT.md becomes a hand-edited charter; PROJECT_AUDIT.md is deleted.

**Invalidation:** only nodes declaring a changed key go stale. In the default graph that is `run_tests` (`verification.commands`) and `integrate` (`verification.required_ci`).

### 3.11 Goal document, editing and dependencies

```jsonc
// origin/zzzops/goal/g1002 : goal.json            (validated; ≤ 64 KB; abbreviated: full schema in SPEC §3.3, §3.4)
{
  "schema": 1, "id": 1002, "title": "Add `release cut` command", "graph": "default",
  "state": "open",                       // open | held | closed
  "closed": null,                        // {reason: done|cancelled|superseded, note, by, at}
  "spec": "## Outcome\n…\n## Acceptance\n- …",
  "priority": "P2", "release": 1, "depends_on": [1001],
  "skip": {},                            // e.g. {"approve_design": "docs-only change; agreed with the owner 2026-10-30"}
  "links": {"issue": null},
  "budget": null,                        // overrides the default correction budget (§3.6)
  "records": {
    "design":        {"status":"done","ok":true,"attempt":1,"holder":"claude:0a0a0a01/design-1","input_fp":"v1:…",
                      "output":{"summary":"Tag the dev tip as release R; refuse while R has open goals.",
                                "doc":{"path":".zzzops/reviews/1002/design.md","blob":"c3d4…","commit":"a1b2…"}},"findings":[]},
    "review_design": {"status":"done","ok":true,"attempt":1,"holder":"claude:0a0a0a01/review_design-1","input_fp":"v1:…",
                      "output":{"decision":"approved","summary":"…","report":{"…":"…"}},"findings":[]},
    "approve_design":{"status":"done","ok":true,"attempt":1,"holder":"human","input_fp":"v1:…",
                      "output":{"decision":"approved","summary":"Local annotated tag only; no push.",
                                "decided_by":"A. Owner","quote":"Yes, local tag only.","decided_at":"…"},"findings":[]}
  }
}
// in progress: branch zzzops/lease/g1002/test_design → empty commit (Attempt 1, Holder claude:0a0a0a01/test_design-1, Timeout 120)
```

**Creating a goal** (`new --file F`; SPEC §3.13, §4.17).
- **Fields:** `title` and `spec` are required. Defaults: `priority` `P2` (values `P0`–`P3`), `release` = `settings.releases.current`, `depends_on` `[]`, `skip` `{}`, `links` `{issue: null}`, `graph` `default` (R8 #9).
- **Ids** (D10). The id is allocated by a create-only push of `zzzops/goal/g<id>` with `id = max(existing) + 1`, seeded by `settings.goals.first_id`; on collision the CLI retries with the next id.
- Goal branches are never deleted, and the recommended ruleset on `zzzops/goal/**` blocks deletion and force-push. Allocation also counts goal refs this clone has seen that have since disappeared. Ids are therefore never reused (R2 #44). Display form: `G<id>`.

**Editing.** `edit G… (--file F… | --set PATH=JSON…) [--base C]` covers setting fields, dependencies, holding, unholding and closing; `reopen G X --note T` adds a reopen finding (SPEC §4.18).
- **Atomicity:** a multi-goal edit is one atomic push of several goal refs, each with an explicit expected value.
- **Fencing** (R5 C9). With `--base <goal commit>` (from `show`), `edit` refuses if the goal has changed since. Without `--base` for every edited goal, `edit` is a dry run that prints the preview and the `--base` values to apply it with; a concurrent change is always refused (`goal_changed`), never re-applied. There is no confirmation threshold and no `--yes` (A5): the preview is always printed, and `--base` is the fence.
- **Repair:** `edit --file` accepts a document even if the current one is invalid.
- **Impact preview:** every edit prints which nodes become stale, reopened, ready or blocked, across the edited goals and their dependents. The preview is the frontier diff, computed by the pure function.
- **Direct edits:** a `git` commit on the goal branch is equally valid. `REPAIR.md` documents the recipe.
- **Validation:** schema, size, that dependencies exist, no dependency cycles (naming every member), `release(dep) ≤ release(goal)`, no `skip` key naming a terminal node (`model:L1`), `closed.reason: done` only when every terminal node is current, else `superseded` or `cancelled` (`m4:F1`), and no `state: open` on a goal closed as `done`: a post-merge correction is a follow-up goal (`evo:M1`). A cancelled or superseded goal may be reopened.
- **What edits never need:** a new goal, an independent review, or an approval ceremony.

**Generic close** (R6 F11, R5 C6). When every terminal node of a goal is current and ok, the same push that made it so sets `state: closed, reason: done` and deletes that goal's leases and its stack branch, if any. It runs inside every goal write, so ops know nothing of goal lifecycle; in the default graph it fires on the push that records `merge`. Local goal worktrees of closed goals are removed opportunistically (§3.9). Closing for any other reason is an `edit`. When such an edit closes a goal that has a PR, its output prints `gh pr close <n>` and, if `links.issue` is set, `gh issue close <issue>`, so a cancelled goal's code cannot be merged later by hand (`evo:L4`). If that goal has a stack branch, the close deletes it, and GitHub then closes the goal's own PR (its base branch is gone); for a cancelled or superseded goal that is the intended outcome (`m4:F10`; SPEC §4.18).

**Dependencies.** `deps.<node>.<output>` is satisfied when every dependency goal has that node current and ok. Closed `done` goals keep their final records, so their values stay stable. Delivery uses dependencies in two places: `base` stacks on them once they are integrated, and `merge` waits until they are merged (§3.16).

| Situation | Effect |
|---|---|
| A dependency is still in discovery | Only the dependent's `design` waits, for the dependency's design review; nothing else does |
| A dependency is open and progressing | The dependent waits with a named wait ("waiting: G1001 integrate" for `base`, "waiting: G1001 merge" for `merge`); this is never a stuck item. While a dependency's `integrate` re-runs or polls CI, the dependent's delivery waits the same way (§3.16) |
| A dependency is held | A named wait ("waiting: G1001 held"), not a stuck item (`econ:M5`) |
| Two dependencies conflict with each other | A named wait (`deps_conflict`) until the stack set combines cleanly: after a dependency's PR head changes or a dependency merges, at worst once the remaining dependency rebases onto the integration branch (§3.16) |
| A dependency has a goal schema this engine does not know | "waiting: engine upgrade" (§3.10) |
| A dependency is stuck, `closed` with a reason other than `done`, or invalid | The dependent is stuck: its human item names the dependency and offers drop, retarget or cancel (§3.6) |
| A dependency is closed `done` without the node a dependent reads | Optional input: `null`. Otherwise the dependent is stuck, with drop and retarget commands (`evo:H1`) |
| Any dependency read | One local document read, no history |

**A dependent's design** consumes `deps.design.doc` **gated on** the dependency's design review being ok (`deps.review_design.summary`), not on its human approval. So a whole chain's design approvals can be answered in one batch (`econ:M2`). The dependent fingerprints the dependency's design blob, so a dependency design rewritten after the human rejects it re-stales the dependent automatically. The cost is one wasted dependent design per rejected dependency design. `next`'s goal-id order presents the dependency first in the batch.

**Releases.**
- **Data:** each goal has a `release` integer, and policy has `settings.releases.current`. `merge` is release-gated.
- **Cutting** is a human decision plus `git tag`, then a policy change (`zzzops/policy/release-N`) that bumps `releases.current`.

**Trunk.** The integration branch comes from git config, or else the remote's HEAD branch, and must equal POLICY.json `settings.integration_branch` (§3.10). Nothing hard-codes `dev` or `main`. When the integration branch is switched on purpose, `integrate` retargets open PRs whose base differs.

### 3.12 Scheduling: discovery ahead, and capture flows into discovery

**Ordering.** With `settings.scheduling.order` (default `stage_first`), `next` orders actions and human items across all open goals by (SPEC §4.11):
1. stage (`discovery` before `delivery`);
2. release;
3. priority;
4. goal id;
5. topological order.

`goal_first` drops the stage key, so each goal finishes before the next one starts.

**What the ordering achieves.** Every runnable design, design review and design approval across the backlog surfaces before any delivery work. The human sees **all pending discovery gates next to each other**, for example the design approvals for G1002, G1005 and G1007, each with its summary and facts line, and can answer them in one sitting.

**Dependencies don't block discovery.** A dependent goal's `design` consumes its dependencies' reviewed design documents (§3.11), so it is designed in light of them. In delivery, `base` waits only until each dependency has a reviewed, integrated PR (for a PR into the integration branch, with its required checks passed), then stacks on it (§3.16); only `merge` waits for dependencies to merge. Design work is never redone because of a rebase.

**Capture flows into discovery** (`econ:H4`).
- **The CLI side:** `new --file F` creates the goal and returns `next --goal G`, discovery first: the `design` action. `design` is a worker node (`root: false`). No worktree or work branch is created yet.
- **The skill side:** the add-goal skill writes the spec with the human, then immediately dispatches `design` to a worker and continues capturing the next goal.
  1. The worker reads `dev` with the commands in the task card and writes the design.
  2. Design questions come back through `submit --blocked` as human items, batched with the others.
  3. `review_design` goes to another worker, and `approve_design` is presented when it is ready.
- **Intent check at capture (G1029).** Before `new`, the add-goal skill compares the goal with `settings.intent`. A goal that pulls against it is quoted back with three ways on: change the goal, amend the intent through a `zzzops/policy/*` branch, or proceed with the departure recorded. Only the owner chooses, in their own words. A chosen departure is recorded as a closing `Project intent:` spec paragraph with the owner's dated quote. The Intent lens honours it only with that quote, and `approve_design` shows it to the owner (when approvals are delegated, the owner sees it only if they answer or read the item). The skill never offers an `approve_design` skip for such a goal. With no owner present the goal is created without the paragraph and the Intent lens raises the departure. The engine is unchanged.
- **Co-design** with the human stays available when the human asks for it; `root` is advisory.
- **Tradeoff:** less live back-and-forth during design, so the spec must carry the human's nuances. In exchange, capture is not serialized behind each design, the design does not run in the long conversational context (the largest cost item in the economics review), and the root agent is not the overnight bottleneck.
- **Child goals.** There is no decomposition node. A design may propose child goals in prose; the agent creates them with `new` only **after** `approve_design` is ok, so an unapproved design cannot fan out discovery work (R7 M9).
- **Result:** a goal added in a conversation leaves it with its design under way; its design approval is batched with the others. Delivery can then proceed unattended.

**Agent guidance in the shipped skills** (from the walkthroughs, R8 and R9, and the third review pass). The shipped skills are bootstrap (§3.17), add-goal and execute.
- **Wait versus stop.** `next` has a top-level `wake_at`: the earliest `retry_after` or live-lease `expires_at` across the open goals in scope, or `null` (`econ:C1`, `harn:M2`). Release gates carry no time, so they do not contribute (`x:M1`).
  - **Unattended runs** sleep until `wake_at` using the harness's own scheduling (Claude Code `/loop` or a scheduled wake-up; Codex an outer loop around `codex exec`), and stop only when `wake_at` is null and nothing is running.
  - **Attended runs** report what is waiting and until when, then stop.
  - Neither busy-polls. No loop script is shipped.
- **Scope.** When the user scopes work to goals, the agent always passes `--goal`. `next` echoes the filter and shows `also_pending: {human: n, actions: m}` for the rest of the portfolio, so batched human items aren't invisible.
- **Compact items.** Unscoped `next` renders human items compactly (goal, node, kind, question, `since`, and the command to expand). `next --goal G` keeps the full items, and the skill presents human items through it (`econ:M6`).
- **Dispatch.** Workers do every agent node, review nodes included, launched with the harness's subagent tool. A reviewer must not be the subject's holder. The dispatcher mints the labels (§3.7). A `retry` action, such as a `base` conflict to resolve, carries its instructions and the advisory capability `reasoning`; the skill dispatches it to a worker together with `design.doc` and the conflicted files (`econ:M7`).
- **Running ops.** An op `start` can run for many minutes. The skill runs it with the harness's maximum timeout, or in the background, and waits for it to exit before ending the turn or the subagent; it prefers running ops from the root (`harn:M1`).
- **Since T.** "What happened since T?" is one local command, `git log --since=<T>` over the goal branches, which shows each commit's `Outcome:` line, followed by `next` for current human items. `next --all` gives each open goal's `last_change` (`econ:H5`).
- **Merges done on GitHub.** Before presenting `approve_merge`, the skill checks `gh pr view`. If the PR is already merged into the integration branch, it records `decided_by = <merger>` and `quote = "Merged PR #N on GitHub at T"`, so the PR list can serve as the human's merge inbox (`econ:L2`). A stacked PR merged on GitHub went into its dependency's branch, not the integration branch, so it is not recorded as an approval; `merge` or `integrate` raises it as a human item (`x:M7`).
- **Policy branches.** The skill warns before an attended session ends with a policy branch open, since it pauses all new work until it lands (`econ:L1`).

### 3.13 Human decisions

**Every `needs_human` item carries:**
- a plain-language question;
- the input summaries, never bare hashes: a checkpoint input is rendered as a diffstat plus the command that shows the diff, and an artifact as its summary plus a web link to the file on the work branch (derived from the remote URL, no API call);
- `since`, when the item became pending, and, when the node has an earlier human record, `previous: {decided_at, quote, stale_because, interdiff}`, so a re-ask never looks like a first ask;
- options, and a facts line computed from the records instead of a fixed recommendation: correction rounds per review, waived or disputed findings, and the CI result (`econ:M1`, `cons:M5`);
- for an item that records an answer, the exact `answer` command, including `--fp <input_fp>`. `answer` refuses if the item's current input fingerprint differs, so an approval can never land on content the human did not see (R4 H1). The crash-loop, budget and stuck items have no fingerprint; they print the exact commands for their options instead.

**The merge approval item** shows `implement.summary` (what was built, in the implementer's words), the review summaries, the diffstat, and the PR link when a PR exists. The link is read from `integrate`'s latest record for display only; it is not an input, so `approve_merge` does not wait for `integrate`. For a stacked goal the item says "stacked on G1001 (PR #n, not merged yet)".

**Human review nodes** are answered with the review shape plus `{decided_by, quote, decided_at}`. Validation requires a non-empty `summary` and `quote`.
- **What was approved.** The agent records what was approved, in its own words, in `summary`, and the human's words verbatim in `quote`. If the human's words contradict the design, the agent clarifies before recording anything (R8 #5).
- **Deferring.** A human saying "not yet" means nothing is recorded; the item stays pending (R8 #4).

**Blocked questions** from agents (`submit --blocked`) or operations are answered the same way. A blocked record whose inputs have since changed is no longer asked (R1 L8, R2 #48).

With `blocked_findings` required (G1040), an owner-question round's other live findings reach the retry card too, through `last_output`; the designer records the real answer, responds to answered owner questions and fixes the ordinary findings in that revision. Unanswered owner questions still block. Without the capability, G1026's re-review-only flow is unchanged. A response to an obsolete finding is refused with its reason and an instruction to drop it, separately from missing live responses. This avoids an unnecessary design/review round without giving a designer authority to invent an answer.

**Genuine human decision points:**
- goal scope at capture;
- design approval (on by default; `skip` per goal);
- the merge decision (D3; required in the default graph);
- release cuts;
- public external writes;
- branch-protection bypass;
- deployment, spending and destructive migration;
- agents' consequential blocker questions, including design questions from a `design` worker;
- persistent review disagreements;
- goals that exhaust their correction budget, and crash or repeat loops;
- op waits still pending after the timeout (required checks, a merge GitHub blocks);
- stuck goals, including dependencies that cannot finish.

### 3.14 Interruption and uncertain-outcome recovery

| Interruption | What the next invocation sees | Recovery |
|---|---|---|
| Crash before any push | The remote is unchanged | Re-run the same verb |
| Push sent, response lost | The fetch shows the update | Reported as applied when the record's attempt and holder match; no duplicate |
| Contention on one goal | Atomic or compare-and-swap rejection, with the lease unchanged | Automatic retry with backoff (30 s deadline) |
| Push refused by a server rule or hook | The re-fetch shows nothing moved | `push_refused` at once, with the remote's message and the refused refs; fix the rule (§3.17) |
| Agent dies mid-phase | The lease ages past its timeout | `start --reclaim`. On the same machine the worktree still holds its edits; elsewhere only pushed work survives (`renew` pushes nothing but the lease; `REPAIR.md` has the recipe for pushing work in progress by hand). |
| Phase crashes on every attempt | The lease attempt reaches the record attempt + 3 | A crash-loop human item: one more try with `--force`, skip or cancel |
| A node records three blocked outcomes in a row waiting for an agent, or an op raises the same finding three times with unchanged inputs | The repeat cap | A `crash_loop` human item instead of another retry |
| Session paused | The lease may have expired | Renew first; if superseded, see the next rows |
| Stuck agent that is still alive | The lease is live | `abandon G X --force --note …` (it leaves an expired lease, so the next start is a new attempt, and the stuck agent's late submit is refused with `superseded`) or `start --reclaim --force` |
| Two agents claim the same node | One create-only push wins; the nonce makes identical claims distinct commits | The loser is told the holder |
| Late submit after a reclaim | The atomic push is rejected | `superseded`; the late work stays local, nothing lands; the error prints the salvage commands |
| Local commits diverge from the remote work branch | The sync rule finds genuine divergence | `sync_refused` with the salvage commands (§3.9) |
| Op crashes | The lease expires within the op timeout (15 min) | `start --reclaim`; the op is observe-first |
| Required checks pending | `integrate` records `blocked {waiting_for: time}` | `next` shows it as waiting until `retry_after` (5, 10, 20, then 30 min); after `ci_timeout_minutes` it becomes a human question. Unattended runs sleep until `wake_at`. |
| GitHub blocks the merge | `merge` records `blocked {external, time}` | Retried every 30 min; after `ci_timeout_minutes` a human question |
| Rebase conflict | `blocked {category: conflict, waiting_for: agent}` with instructions, keeping the remote work tip it saw | A worker resolves the conflict, then `start G base`, which accepts the hand-rebased branch if the remote work tip has not moved |
| Dependencies conflict with each other | `base` records `deps_conflict` | A named wait until the stack set combines cleanly, through the dependencies' own progress (§3.16) |
| A dependency's PR head moves, or it merges | `base` is stale once the dependency's `integrate` is current and ok again | `base` restacks; each node whose commits replay with unchanged patch ids has its record carried forward (§3.16) |
| PR merged or closed by hand on GitHub | `merge` or `integrate` observes it, with its base | Merged into the integration branch: recorded, and dependents retargeted (other code merged: a human item). Merged into another base, such as a stacked PR merged into its dependency's branch: a human item. Closed: a human item. |
| Goal branch force-pushed or deleted | The non-`+` fetch refuses the update | Writes to that goal are refused; other goals are unaffected; repair with a forward commit (`REPAIR.md`) |
| Clock jump | Future-dated lease tips, or most leases expired at once | A warning; reclaims during a mass expiry need `--force` (the warning names sleep as the likely cause) |
| Engine too old for the policy | A capability in `settings.engine.requires` (or implied by the deprecated `engine.min`) that the engine lacks | Writes refused; reads still work; upgrade the plugin (`REPAIR.md` upgrade recipe) |
| Invalid goal document | Error on that goal only; its dependents get a stuck item naming it. An unknown schema is `engine_too_old` instead, and dependents wait for an engine upgrade. | `edit --file` or a direct edit |
| Invalid policy merged | Global blocker; read-only verbs still work. Keys an older engine does not know are reported as `engine_too_old`, not as invalid policy. | Fix through a policy branch |
| Harness sandbox blocks the network or the Git directory | The startup probe fails | `environment` naming the sandbox, not `remote` (§3.17) |
| Git remote unreachable | — | Mutations refused, reads marked `current: false`, leases and policy branches reported as unknown. A GitHub API outage affects only the ops that call GitHub, which return `blocked {waiting_for: time}`. |
| Policy branch pushed mid-phase | Global blocker | A running phase may still renew and submit; new starts wait |

### 3.15 CLI surface, repair reference and cost

Eleven verbs (flags, outputs and exit codes in SPEC §6, §3.14–§3.17):

```
next [--goal G | --all]          show G [--node X] [--json]
new --file F                     start G X [--as L] [--reclaim] [--force]    # op nodes run to completion
submit G X --attempt N [--as L] (--output F [--artifact F] | --blocked F)
renew G X --attempt N            abandon G X (--attempt N | --force --note T)
answer G X --fp P --file F       reopen G X --note T
edit G… (--file F… | --set PATH=JSON…) [--base C]                           # covers set/depend/close/hold
validate [G…|--policy [--dir D]]                                            # covers policy validate and doctor
```

- **`--policy-ref REF` (#742):** a global flag accepted by `next`, `show` and `validate` only. It previews the policy on a policy branch, a remote branch or a commit, read-only; `validate` adds the impact on current goals (SPEC §6).
- **`new` is idempotent (G1001):** the same request, identified by its `request_key` or by its title, spec and dependencies, returns the goal it already created, so a retry after an uncertain push never duplicates a goal (SPEC §4.17).

`status` (now `next --all`, which lists open and held goals only), `doctor`, `set`, `depend`, `close`, `hold`/`unhold`, `policy validate` and `run` are folded into the above. Every verb prints one JSON object, and errors share one envelope with exit codes 0–4 (SPEC §3.17). `show`'s text form is one line per node: state, reason, attempt, holder, since (`econ:L4`).

**Printed commands** (`harn:H3`):
- Commands are stored and emitted as verb-relative argv (`["start", "1002", "base"]`). The invocation prefix is rendered at print time, so a command stored in a goal document never points at an old plugin path or another machine's path. Output JSON carries `argv` next to `command`.
- Values that would need embedded quotes are passed in a file (`--file`), because PowerShell mangles quoted JSON. The skill tells PowerShell users to prefix `& `.
- The Claude Code plugin ships a `bin/zzzops` launcher, which Claude Code puts on the Bash tool's `PATH`. That gives a stable bare `zzzops` command and a stable permission rule `Bash(zzzops *)`.

**`references/REPAIR.md` (one page)** documents the git-level recipes instead of adding verbs (R2 R13):
- edit a goal branch directly;
- delete a lease by hand (one line);
- undo a goal change (`git show <commit>^:goal.json` on the goal branch, then `edit --file … --base`);
- revert all writes of one bad engine build, found by their `Engine:` trailer, with one multi-goal `edit` (`evo:L5`);
- upgrade or roll back the engine across machines (§3.10);
- rename a node: while the policy branch is open, copy `records.<old>` and `skip.<old>` to the new name and rewrite finding targets on every goal, closed ones included, in one multi-goal `edit`, then land the branch (`evo:M2`; also in `MIGRATING.md`);
- repair a force-pushed goal branch with a forward commit that has both tips as parents;
- salvage superseded local work (§3.9);
- seed a child goal's work branch from a parent;
- record a merge done on GitHub;
- close the PR and issue of a cancelled goal;
- delete the work branches of goals closed long ago that no open goal depends on (`evo:L1`);
- push work in progress.

**Cost per verb.** Estimates use the measured ~0.9 s per Git round trip to the GitHub-hosted remote and ~0.5 s per `gh` call (R1 H5). They are hard CI budgets on counts, measured from a trace of every network Git command and `gh` call with a metered fake provider seeded with 0 and with 2,000 archived comments; wall time is diagnostic only. The `next` embedded in a `submit` reply, and an op's finish, reuse the invocation's snapshot advanced by the refs just pushed; they do not fetch again (`cons:L1`).

| Verb | Git round trips | GitHub API | Comment reads | Output | Typical wall time |
|---|---|---|---|---|---|
| `next` | 1 fetch (4 ref patterns) (+1 `ls-remote` on a legacy check) | 0 (1 on a legacy check) | 0 | ≤ 8 KB | ~1 s |
| `validate` | 1 fetch + 1 `ls-remote` | its environment probes + 1 (`api graphql`; 0 when ignored, `gh` is unavailable, or the remote is not on GitHub); +1 repository-setting read with `settings.branching` and usable `gh` (G1031, 10 s timeout, warning only) | 0 | small | ~2 s |
| `start` (agent) | 1 fetch + 1 lease push | 0 | 0 | task card ≤ 4 KB | ~2 s |
| `submit` | 1 fetch + 1 atomic push | 0 | 0 | ≤ 4 KB (includes `next --goal G`) | ~2.5 s |
| `start base` | 1 fetch (including the unmerged dependencies' PR branches) + lease push + finishing push (+ 1 push of the stack ref when it retires one) | 0 (2–4 when it retires a stack PR) | 0 | small | ~3 s plus the rebase |
| `start integrate` (checks pending) | 1 fetch + lease push + finishing push (the PR push is a no-op when unchanged) | 2–3 | 0 | small | ~4 s, at most once per `retry_after` (5 min, backing off to 30) |
| Per useful phase | ≤ 4 | 0 | 0 | ≤ 8 KB | ≈ 4–5 s of bookkeeping (today about 342 s) |

A legacy check (G1015) runs in `next` only when its cache key (engine version, remote URL, local legacy signals) changes or its `retry_after` passes (24 h after a transient failure or while the item is active, 7 days after `gh` is missing or unauthenticated). It never runs in the `next` embedded in a write, offline, or when `settings.legacy.ignore` is true.

**Scaling** (`evo:L1`, `gen:L8`).

| Factor | How cost grows |
|---|---|
| Open goals | Linear: one document read and parsed per open or held goal and per goal they depend on (reading 1,000 documents in one batch took 57 ms). Closed goals' documents are skipped by their `State:` trailer. |
| Goals ever created | Linear, small: the fetch advertises every goal ref (about 0.37 MB at 5,000 goals), and every push receives the full ref advertisement, which includes the kept work branches (about 0.75 MB at 5,000 goals and 5,000 work branches). At this repository's rate of about 700 goals a year this stays tolerable for years; deleting old work branches (`REPAIR.md`) reduces it. |
| Goal history, repository size | Cost is independent of them. Goal branches are read at their tip only; work and PR branches are fetched only by verbs touching that goal; `code_tree` is constant-time. |
| Size of a goal's diff | `change` grows with the diff: seconds for asset moves of 100 MB or more. |
| Concurrent agents | Writes to different goals never contend; only writes to the same goal retry. Normal work makes no GitHub API calls, apart from the bounded legacy check. `integrate` and `merge` make a few per goal (and `base` two to four when it retires a stack PR), far below GitHub's 5,000/hour limit. |

Developer clones that should not carry every `zzzops/*` branch add the negative fetch refspec `^refs/heads/zzzops/*` (a bootstrap step); the engine uses explicit refspecs and is unaffected.

### 3.16 Stacked delivery (A1, D5)

**Why.** In revision 5 a dependent started delivery only after its dependency merged. In a chain G1001 → G1003 → G1007, each link then waited for the previous link's CI, merge approval and merge, so the chain advanced one link per human sitting. The human asked for GitHub stacked PRs instead, and for a combining "merge PR" when a goal has several dependencies.

**The idea.** A dependent starts delivery as soon as each dependency has a reviewed implementation on its PR branch. The dependent's own change is synced onto that branch (merge mode when required, legacy rebase otherwise), and its own GitHub PR targets that branch. So the PR shows only the dependent's code, and its reviews judge only its own diff. Merges still happen in dependency order. When a dependency merges, its dependents' PRs are retargeted to the integration branch `I`, and their work is restacked onto `I`.

**When a dependent stacks.** `base` is ready when every dependency is either merged, or has a current, ok `integrate` record: its PR branch exists with review-free code, and its implementation passed `review_impl`. `base` does not wait for the dependency's `approve_merge`. A dependency that is open but has not reached that point is a named wait ("waiting: G1001 integrate"), not a stuck item.
- **CI stays in `integrate`** (`x:H1`, `m4:F3`). For a dependency whose PR targets `I`, "current, ok `integrate`" means its required checks passed. A stacked dependency's `integrate` is ok without CI (below), so only the chain root's CI delays stacking.
- **While a dependency's `integrate` re-runs or polls CI** (after a correction, a restack or a `dev` move), it is not current, so the dependent's delivery is a named wait ("waiting: G1001 integrate"). The dependent's recorded approvals are kept, but its delivery items, `approve_merge` included, are not shown until the dependency is current again.

**What it stacks on.** `base` builds a **stack set** S:
- the PR head `zzzops/pr/g<dep>` of every unmerged dependency, that is, every open or held one (a closed dependency is never stacked on);
- plus the fetched integration tip `I`, when S would otherwise be empty, or when some merged dependency's merge commit is not an ancestor of every head already in S. Without this rule, after one of two dependencies merges, the goal would stack on the other's head without the merged code.
- Then every member that is an ancestor of another member is dropped, so a transitive dependency (G3 on G1 and G2, where G2 is stacked on G1) needs no combine commit (`m4:F6`).

| S | `base` stacks onto | The goal's PR targets |
|---|---|---|
| only `I` (no unmerged dependency) | the fetched integration tip `I` (as before) | `I` |
| one dependency's PR head | that head, `zzzops/pr/g<dep>` | the dependency's PR branch |
| two or more commits | a **combine commit** on a new branch `zzzops/stack/g<id>` | `zzzops/stack/g<id>`, plus a draft **stack PR** from that branch into `I` |

Below, "k = 1" means `base` stacks on a single dependency PR head, and "k ≥ 2" means S has two or more commits, so a combine branch exists.

- **The combine commit** is built without a worktree: `git merge-tree --write-tree` over S, then `commit-tree` with S as parents (`I` first if present, then the heads in goal-id order) and the conventional message `chore(stack): combine <names> for G<id>` (intermediate combines use `chore(stack): partial combine for G<id>`). It is pushed in `base`'s atomic push, with an explicit expected value.
- **A stack set that does not combine cleanly.** When `merge-tree` reports conflicts, `base` records `blocked {waiting_for: dependency}` with reason `deps_conflict`. The goal is a named wait until S combines cleanly: when a dependency's PR head changes, or a dependency merges, and the remaining heads then combine; in the worst case, when the remaining dependency rebases onto `I`, which its own merge requires. The wait therefore ends through the dependencies' own progress, and it is never a stuck item. v1 does not resolve conflicts inside S.

**Merge sync (G1038).** Require `merge_sync` through a reviewed policy branch after every writing engine has it. `base` then computes the goal's own old-base..work change onto the new target with an explicit merge base, rather than rewriting its commits. The merge has parents work/onto, subject `chore(sync): merge <target label> into G<g>` and trailer `Zzzops-Old-Base: <old base>`. The explicit old base also handles rewritten/dropped dependency heads and release-target changes. Work advances only by fast-forward, and later syncs preserve the prior resolution. An already-contained target records its new base without an extra merge only when old is also an ancestor of onto; a dropped dependency/older target still needs the explicit-base merge to remove its content.

**Conflict recovery.** `base` checks out merge-tree's conflicted tree with HEAD still at work. The agent edits only the listed paths, without committing. Resume compares changes/untracked paths against that conflicted tree, not HEAD, and creates the final tree in a temporary index from only the allowed files. It refuses leftover markers and other edited paths. The push preserves latest racing review commits; only after success does the worktree move to the sync commit. If onto moves meanwhile, reset/recompute and disclose lost pending edits. Legacy mode keeps its rebase recovery (SPEC §5.2).

**Sticky mode and rollback.** Once a branch has engine sync merges, a policy without merge_sync blocks base before a rebase, abort or push; restore the capability. An older engine cannot enforce this, so removing merge_sync is unsupported until every goal with sync merges has merged or been cancelled. Without the capability and without such merges, the old rebase path stays available; switching a linear branch into merge mode uses its recorded base. Release-to-dev sync and finish are unchanged.

**Restacking and carry.** Dependency PR heads and merge commits still trigger base, and G1025's scheduler retains its one-per-agent-attempt behavior. Merge mode records extra unfingerprinted `synced={old, onto, work, tip, merge, resolved}` while declared replay maps stay empty. Carry relocates each eligible done workspace node's checkpoint to the actual synced tip only if its old commit belongs to the synced work history, and compares old/new transient -U0 deltas within its scope and conservatively checks edited hand-resolution positions (G1039), retaining the old recorded -U3 identity. Frozen tests are the preserved node's scope; other nodes remain unscoped. Carry keeps the old change, frozen set and judgment provenance, recomputes base-fed inputs and prunes only obsolete responses; a node that fails the predicate re-runs. Tree-bound checks/integrate re-run when the actual tree changes, not merely because the checkpoint commit moved. The predicate widens context/line-number tolerance without changing the scope/relocation/writer signatures; SPEC §4.21 specifies the positional union guard and its conservative limitations.

Legacy rebase mode instead uses its identical per-commit patch-id map, and retains replay_pos only for compatibility. It no longer supplies checkpoint suggestions: all submits default to HEAD. Its stored-map goal-size limit remains (SPEC §1.8). Neither mode invents virtual checkpoint trees or skips tree-bound verification.

**Clean-sync judgment (G1039).** Transient -U0 deltas ignore only context/line numbers; actual stored change remains -U3 and is retained by a carry. For edited resolution paths in the node's scope, accept only a complete whole-file union of work/explicit-old-base/onto in one side order or the other. Reordered/interleaved/dropped/wrong-copy or unavailable/binary versions conservatively stale. diff(T,M) finds edited resolutions, not necessarily every listed conflict: unchanged modify/delete files can be omitted, but the old/new -U0 gate rejected the affected in-scope delta in ten scratch cases. Neither an empty edited set nor a same -U0 hash alone proves arbitrary hand edits safe. A contained unchanged checkpoint skips the historical union check; rebase mode retains its stricter replay map.

**Semantic review after sync.** The shipped implementation reviewer receives base as a non-context input and re-runs when that value changes, even when its code subject was carried. Frozen tests/design judgments retain their identities. The sync card prioritizes recorded resolutions, cross-file line/name interactions and shared paths; it is a reading aid rather than a staleness gate. Existing scoped portable diff/log/interdiff commands and remerge views stay intact. Its touching list blobs, then detail folds after ordinary blobs and before the 80-preview fallback; full evidence remains accessible. The review asks for semantic conflicts plus actual new goal commits, not a redundant whole-goal pass. If the base input leaves a card over target after the 80-character fallback, short instructions may use preview-free full blob/read references; instruction names and complete guidance remain accessible.

**Squash at integrate.** The work branch remains intact. On the trunk/stack commit of the last sync, integrate makes c1 containing the final frozen paths (`test: <title> (G<g>)`) and c2 containing the tested code tree. Empty parts are omitted. First-parent own-commit history excludes review commits, merges, every prior sync's second parent and old-base trailer, so dropped dependencies and old target history cannot pollute the title or release effect. c2's conventional type is the highest implementation release effect (feat, then fix/perf/revert, then the prevailing no-release type); breaking footers/bangs are retained. The PR title is its final commit's subject and changes with it. Part bodies keep subjects and breaking footers.

**Stable heads and truthful views.** Authors come from each part's newest own author, with a fixed committer. Both dates of c2 are later than c1 and any previous PR head, including after a late test fix. Compare candidate trees/parents/messages/authors before dates and keep an unchanged head, avoiding repeated pushes/checks. Views split frozen tests from implementation without excluding tests from the delivered code.change. Same-base interdiff uses git diff; moved merge-mode bases use first-parent no-merges logs and previous.syncs remerge-diffs, while legacy rebase retains range-diff (SPEC §4.20).

**Conventional commits (owner decision).** Every new agent commit on work, every engine work/stack/PR commit, PR title and engine-written trunk merge subject is conventional. Test writers use test:; implementation may not touch frozen paths even transiently. Goal/lease subjects keep their machine format, which never reaches trunk. Squash merges use c2's type/breaking text; merge commits use chore(merge); rebase keeps the two conventional subjects. Exact-head and authority gates remain (SPEC §4.14, §5.5).

**GitHub stacked PRs.** `integrate` opens or updates the goal's PR with the base from the table above.
- With k ≥ 2, `integrate` also opens or updates a **draft stack PR** from `zzzops/stack/g<id>` into `I`, titled `chore(stack): combine #<goal PR>, #<a>, #<b> for G<g>`, with a body listing the combined PRs. The engine never merges it.
- When the target changes, `integrate` retargets the PR explicitly with `gh pr edit <n> --base <target>`. ZzzOps never waits for GitHub to retarget a PR; the one place GitHub may do so first is after a merge (below), and both lead to the integration branch (`m5:N3`).
- When k drops below 2, `base` (only after its push succeeded) retargets the goal's PR to the new target, closes the stack PR (`gh pr close`), and then deletes `zzzops/stack/g<id>` (`m4:F9`, `x2:M1`). Deleting the branch first would make GitHub close the goal's own PR. The generic close also deletes it if present.
- A draft stack PR into `I` triggers the repository's `pull_request` CI on every combine push; the bootstrap setup note covers it (§3.17, `x:L12`).

**CI on stacked PRs.** When the PR's base is not `I`, `integrate` does not wait for required checks. It is ok once the PR is at the expected head, and records `ci: {stacked: true, checks: <whatever has reported>}`. Required checks are enforced only when the PR's base is `I`.
- `merge` still requires every dependency merged, like a release gate, and an `integrate` record whose PR base is `I` with required checks passed. By then `base` has restacked onto `I`, and `integrate` has re-run against `I`.
- A repository whose workflows run only on PRs into `I` therefore works unchanged.

**Merging a dependency that has stacked dependents.** Once the dependency's merge is observed, `merge` retargets every open PR whose base is that branch to `I` (`gh pr list --base zzzops/pr/g<id>`, then `gh pr edit --base I`). The dependents' own `base` re-runs then restack them properly (`m4:F2`, `m4:F7`, `x:L13`).
- **Only after the merge.** A merge that GitHub refuses or only queues therefore never leaves a dependent PR into `I` that shows the unmerged dependency's code.
- **Merges done by hand on GitHub** are observed the same way, so their dependents are retargeted too.
- **GitHub's automatic head-branch deletion** may delete the merged branch before the engine observes the merge; GitHub then retargets the dependents itself, so no dependent PR is closed either way.
- **A stacked PR merged by hand** goes into its dependency's branch, not `I`. `integrate` and `merge` read the PR's base and raise a human item: "PR #n was merged into `<base>`, not `<I>`" (`x:M7`).

**The graph change.** `approve_merge` no longer consumes anything from `integrate`. It is ready as soon as `review_impl` is ok, so a whole chain's merge approvals can be answered in one sitting, before each goal's own CI. Its item still shows the PR link when one exists, read from `integrate`'s latest record for display only. `merge` consumes `integrate.pr` and `approve_merge`, as before. The default graph is therefore no longer a single line (§4.1):

```
… → run_tests → review_impl ─┬→ integrate ─────┬→ merge
                             └→ approve_merge ─┘
```

**Tradeoffs.**
- **The human approves before the goal's own CI.** A CI failure that needs a code fix changes `change` and re-asks the merge approval. That is rare, because `run_tests` has already run the tests locally.
- **A stacked goal's GitHub PR targets its dependency's branch,** so its GitHub diff is only its own code. With k ≥ 2, the stack PR shows the combined dependencies.
- **Checks on a stacked PR are informational.** They are enforced only after the restack onto `I`, which re-runs `integrate`.
- **Conflicts between dependencies wait.** v1 does not resolve them; the goal proceeds once the stack set combines cleanly (above; `x:M3`).
- **Stacking waits for the chain root's CI** (`x:H1`, `m4:F3`). A dependent stacks only once its root dependency's required checks have passed. While a dependency's `integrate` is re-running or polling CI, its dependents' delivery is a named wait and their human items, `approve_merge` included, are hidden; their recorded approvals are kept. The alternative, stacking on a dependency's PR while its CI is still running, was not adopted: CI stays in `integrate` (the revision 5 fold stands).

The worked examples are §4.2 (one dependency) and §4.4 (a chain).

**Conflicts with the integration branch (G1021).** `integrate` checks a PR into `I` for conflicts before it waits on checks: first locally, with `git merge-tree` against the integration tip it already fetched (deterministic, no GitHub call), then by GitHub's own verdict. A conflict is a `conflict` finding on `base`, which syncs in the selected mode or asks for a hand resolution. GitHub runs no `pull_request` workflows on a conflicting PR, so without this check `integrate` would wait for checks that never appear. A wait that has seen no check at all for 15 minutes becomes a human question. `base` deliberately does not go stale when `I` moves: making the integration tip one of its inputs would re-run every in-flight goal on every merge, although GitHub merges a non-conflicting PR against the current tip anyway. So staleness is detected as late as possible and only where it matters: a real conflict, seen by `integrate` or `merge`.

**Stacking across targets (G1025).** With `settings.branching` a goal's target may be `release/N` or `hotfix/x` instead of `I`, and everything above reads the target where it says `I`. Goals on the same target stack exactly as described. When a dependency merges, `merge` retargets each dependent's PR to the dependent's *own* target, which may differ from the dependency's (a dev goal depending on a release-N goal). Until the release→dev sync brings the dependency's merge commit into dev, the dependent's `base` waits (`release_sync`, computed by the frontier, never recorded), so nothing integrates against a dev that lacks the dependency. G1038 supersedes owner O1 (§3.16a) for goal work branches once the policy requires merge_sync: these moves use the explicit-old-base merge while retaining code_tree/change judgments through per-node carry. Without that requirement legacy rebasing remains. Long-lived line sync/finish merges are unchanged. GitHub's automatic head-branch deletion should be off in branching repositories: finish PRs use the line branch itself as head and would delete the kept release/hotfix branch; dependency deletion can also beat the engine's retargeting. Repository `validate` warns when the setting is on and readable (G1031; SPEC §3.16).

### 3.16a Release branching (git flow, G1025)

**Why.** G1038 later supersedes the goal-branch rebase choice here only when merge_sync is required; release-line operations are unchanged. The owner (2026-11-01): "we base it on git flow. When all R* goals are complete, we ask the user for approval to create a release branch… When a release branch exists for a goal, the CLI should branch off of that tip, not dev… All of this should be deploy/CI/actual release flow agnostic, it's just a branching strategy." The interview answers: merges only for release→dev (goal branches keep rebasing, so code identity is unchanged); dev moves on to release N+1 at the cut; finishing merges into the production branch and back into dev and keeps the release branch; hotfix branches from main; the cut is offered when every release N goal is closed done.

**Shape.** An optional `settings.branching` block (requires capability `release_lines`) turns it on; without it nothing changes. A release or hotfix line is owned by a **line goal** on a second shipped graph, `release`: `approve_start` (recorded by `release cut` / `hotfix start`), `sync` (`git.line_sync`, `schedule: "upstream"`), `approve_finish` and `finish` (`git.line_finish`), the last two `line_complete`. Reusing the goal machinery gives the sync's conflict resolution a lease, a card and an approval without a second state store.

**Decisions.** The effective release is derived from the line goals (never by editing `releases.current`, which would need a policy branch that pauses work). One release line at a time, as git flow. The cut is race-safe through a request key derived from the line. Closed goals are counted through goal-commit trailers, so the cut and the gate need no closed document read. Back-merges are merge-commit PRs whatever `merge.method` is, and a hand-resolved one needs a human approval. The release→dev sync does not block dev work. The restack of goal branches is scheduled only before an agent phase (pass 3), when the tree-bound re-runs happen anyway, and at most once per agent attempt. Merging into goal work branches was considered and dropped (O1): it would rewrite the identity rules (§3.4, §3.16) that carry approvals across restacks. Waits that depend on other goals (`release_sync`, `line_members_open`, `hotfix_start`) are computed by the frontier, never recorded, so they end on their own. Hotfix names are single-use, and a hotfix finish also reaches the open release branch (git flow).

### 3.17 Harness, repository and bootstrap

**Harness requirements** (`harn:C1`; SPEC §1.5). The CLI process and the agents' own `git` commands need network access to the Git remote and write access to the repository's Git directory. Every invocation fetches, and every write creates objects and refs. No ZzzOps command is local-only. A plugin cannot grant these permissions itself, so bootstrap sets them up.
- **Codex.** Its default sandbox for a Git folder turns the network off and mounts `.git` read-only, so every invocation fails. Two configurations are documented:
  - (a) a ZzzOps profile with `sandbox_mode = "danger-full-access"` and `approval_policy = "never"`, which fits the cooperative trust model;
  - (b) workspace-write with on-request approvals, plus `~/.codex/rules/zzzops.rules` allowing the CLI's exact argv prefix and `git`. Rules match an exact prefix, so they are regenerated whenever the plugin path changes.
- **Claude Code.** Bootstrap writes, or tells the human to add, project `permissions.allow` entries: `Bash(zzzops *)`, `Bash(git add *)`, `Bash(git commit *)`, `Bash(git rebase *)` and `Bash(git push *)`. Auto or bypass mode also works. With Claude Code's sandbox on, `github.com` and `api.github.com` go into `sandbox.network.allowedDomains`, and remotes use HTTPS, because Git over SSH fails through the sandbox proxy on macOS.
- **The startup check** refuses with `environment` when the requirement is not met (§3.10), so a sandbox never looks like a network outage.
- **Where to start a session.** ZzzOps writes under the primary worktree and the Git common directory, so sessions start in the primary worktree, or add it as a writable root (`--add-dir`) (`harn:M6`).
- **Versions.** The Git 2.41 floor excludes Debian 12, Ubuntu 22.04 and Apple Command Line Tools before Git 2.50.1; the setup notes say to install current Git. `gh` has a version floor and needs `gh auth status`; sandboxed or headless runs use `GH_TOKEN` (`harn:M5`). The skills discover a Python 3.10 or later interpreter (`python3`, `python` or `py -3`), because macOS Command Line Tools still ship 3.9 (`harn:M3`).
- **Non-interactive Git.** Engine Git commands run without hooks, except pushes that include a work or PR ref (§3.7), never prompt for credentials or yes/no answers, and the printed rebase instructions never open an editor (`harn:M4`; SPEC §4.1).
- **Unattended Claude Code runs** set the Bash timeouts above `verification.timeout_minutes` (`harn:M1`).

**Repository requirements and stated limitations.**
- **`zzzops/**` must be writable by the agents' credentials** (`gen:H2`): create, fast-forward and non-fast-forward update, and delete, with no required PRs, checks, signatures or message patterns. The only rule ZzzOps itself recommends is the one on `zzzops/goal/**`. A refusal is reported as `push_refused` (§3.7), never as contention.
- **Merge method** (`gen:H3`): `settings.merge.method` (`merge`, `squash` or `rebase`) must be allowed by the repository. Squash also satisfies a signed-commit rule on `I`, because GitHub signs squash commits.
- **PR delivery requires GitHub and `gh`** (`gen:M4`). On other hosts the default graph runs up to `review_impl`; delivery there needs a host op (about 100 lines against the op interface), which is not shipped.
- **Forks are out of scope for v1** (`gen:L1`). Every participant needs write access to the remote, and the remote is the repository PRs merge into.
- **Monorepos** (`gen:L2`): one verification contract (per-area selection belongs in the repository's own verify script, and editing `verification.commands` stales every goal's `run_tests`); one policy block for all teams; a full checkout per delivery goal, so disk use is roughly concurrent delivery goals × checkout size; and `git worktree add` does not initialise submodules, so such repositories put `git submodule update --init --recursive` first in `verification.commands`.
- **Required checks must run on every PR** (`econ:L6`, `gen:L2`). A path-filtered required check never reports on some PRs and becomes a human question after `ci_timeout_minutes`; list only always-running checks in `required_ci`.
- **Committer identity** (`gen:L5`). PR heads are deterministic per committer identity, so `zzzops.committer` is set identically on every machine. Under rules that require the committer to be the pusher's verified email, each machine's rebuild differs, which costs a CI re-run.
- **PR titles and DCO** (`gen:L7`). Goal titles follow the repository's PR-title convention when one is enforced, and agents commit with `-s` under DCO.
- **Nested goal worktrees** (`gen:L9`). Goal worktrees under `<primary>/.zzzops/worktrees/` are hidden from Git only through `.git/info/exclude`, so tools that ignore that file see them. Bootstrap adds `.zzzops/worktrees/` to the repository's tool ignore files.

**Bootstrap** (`gen:H1`, C4). There is no bootstrap verb and no bootstrap module: `bootstrap.py` and its test are deleted. The bootstrap skill is a checklist over `validate`, the shipped templates `zzzops/templates/default/{POLICY.json, workflow.json, prompts/*.md}` (CI runs `validate --policy --dir` on them), and plain `git` and `gh`:
1. **Choose the remote and the integration branch.** Greenfield: create the integration branch with the first commit, before any branch rules exist. Brownfield: use the existing trunk, or create `dev` from it and push.
2. **Write the policy files from the template:** the repository's canonical verify command in `verification.commands`; only always-running required check names in `required_ci`, read once with `gh api`; `integration_branch`; `goals.first_id` above the highest issue and PR number; `routing.tiers` for the harnesses in use.
3. **Validate:** `validate --policy`, which needs no remote and no integration branch.
4. **Land the files** on the integration branch: through `zzzops/policy/bootstrap` and a PR when the branch is protected, otherwise a direct push.
5. **Per clone:** `git config zzzops.integrationBranch <I>`, plus `zzzops.remote` and `zzzops.committer` when needed.
6. **Harness setup** (above).
7. **Host settings,** checked by the skill with `gh api`: automatic head-branch deletion on without `settings.branching`, off with it (G1031: finish PRs delete the kept release/hotfix branch and dependency deletion can race with stacked-PR retargeting); repository `validate` checks it best effort and warns when on, without changing it or failing validation (SPEC §3.16); the merge method allowed; the ruleset on `zzzops/goal/**` blocking deletion and force-push; `zzzops/**` excluded from every all-branch ruleset and hook rule.
8. **CI triggers and ignore files:** the skill offers `branches-ignore: ['zzzops/**']` for unfiltered `on: push` workflows and deploy integrations, which otherwise run on every work and PR push. It notes that a draft stack PR into the integration branch runs the repository's `pull_request` CI on every combine push, which a `pull_request` workflow can skip for head branches under `zzzops/stack/` (`x:L12`). It also tells the human that the repository's `pre-push` hook runs on engine pushes of work and PR branches, and adds `.zzzops/worktrees/` to the tool ignore files.
9. **Developer clones (optional):** the negative fetch refspec `^refs/heads/zzzops/*` (`evo:L1`).
10. **Run `validate`**, which checks the environment.
11. **Capture the first goals** with the add-goal flow. Product discovery is ordinary goals; there is no harness or root-goal hierarchy.

A repository whose integration branch has no `.zzzops/workflow.json` gets `not_bootstrapped`, naming this skill (§3.10).


**Repository local verification (G1043).** `python3 .github/scripts/run_product_validation.py --platform linux --local` reuses CI's canonical discovery, individual-test timing hints and longest-first balancing, with available CPUs by default. Fresh interpreter processes isolate unittest globals; executed/completed IDs must account for the whole inventory exactly once, including failed observations. The runner reports compact totals/worker timings and can write exact reports; hints never select tests. Explicit workers and an inherited ZZZOPS_TEST_WORKERS budget are bounded by available CPUs. The obsolete property-test isolation entry/comment is removed only after source audit found no elapsed-time assertion; every seed/step/semantic assertion stays. Genuine future exclusivity uses sequential policy rather than assuming two local joins coordinate.

The under-five-minute full run on the owner's machine is measured acceptance evidence, with exact-ID accounting, not a fragile unit timeout or guessed speedup. Profile/split genuinely expensive tests only while retaining their scenarios/assertions and representative real integration journeys. Existing CI/native/auxiliary semantics stay distinct; this local command covers the canonical Python suite.

## 4. Default workflow and worked examples

### 4.1 Default graph (`graphs.default`, 15 nodes)

**Amended by G1022.** The shipped graph has 15 nodes: `review_design` applies the seven design lenses (`intent`, `simplicity`, `truth`, `adversary`, `concurrency`, `rollout`, `experience`) and runs beside a separate `adversary_design`, and both feed `filter_design`; `review_impl` applies five lenses (`compliance`, `correctness`, `missing`, `tests`, `craft`) and feeds `filter_impl` (§3.8). `intent`, `simplicity`, `compliance`, `missing` and `craft` are not skippable. The G1000 text below describes the 26-node graph it replaces: read `review_design` plus `adversary_design` for the seven `<lens>_design` nodes, and `review_impl` for the seven `<lens>_impl` nodes. The shipped policy still uses the legacy default 3 × 9 agent nodes = 27 until round_budget is explicitly required; that activates default 10 per actor stage (G1039).

**Sync-review/round-budget adoption (G1039).** The shipped workflow adds review_impl.base as a non-context selector of base.base_commit; the review prompt asks only for semantic conflicts after a sync plus actual intervening goal edits. This remains configurable graph data. A separately owner-approved installed-policy branch, after merge_sync activation, requires round_budget and adopts the base edge/prompt. G1039 leaves default POLICY.requires unchanged. Old counters are never reset; review definition changes stale once but retain the established definition exemption. Result budget readers use stages under the capability and the legacy total shape otherwise.

**Measured review configuration (G1043).** The default test writer outputs cost: object, measured against its checkpoint and commands, with integer duration_ms/exit plus the measured changed-test scope and summary. Review_tests and review_impl receive it as context; red runs are labeled failing, incomplete runs need better evidence, and no cost is guessed. Review_tests and the Tests lens assess measured cost, redundant full journeys, sleeps and brittle elapsed-time bounds without weakening tests. Approve_merge consumes the checks result as context and shows total/repository times, each baseline scope's provenance or unavailable reason, and an available repository delta even when total comparison is unavailable. These are template decisions, not universal engine node names or schemas. The shipped policy requires test_cost but leaves parallel_commands absent; repository adoption is a separately reviewed policy PR, with live-worker impact preview and explicit concurrency-safety review.

**G1038 prompt adoption.** The shipped test-design/implement prompts default checkpoints to HEAD and permit test fixes on top of implementation; installed prompts change through policy branches. The default graph remains configuration, and this goal changes no declared node output or op version. When scoped diffs and measured-cost context exhaust normal card shrink steps, a final 80-character blob-preview clip preserves full reader access and checkpoint commands. Exceptional quoted filenames use a shell-neutral encoded argv bridge for scoped current, approval and prior commands; ordinary command strings are unchanged.

**The release graph (G1025).** The shipped template has a second graph, `graphs.release`, beside this one: the 4-node graph of release and hotfix line goals (`approve_start` → `sync` → `approve_finish` → `finish`, §3.16a). It adds no node, prompt or lens to the default graph, and a repository without `settings.branching` never uses it.

```
design ─┬→ review_design ───┐
        └→ adversary_design ┴→ filter_design → approve_design → base → test_design → review_tests → implement → run_tests ─┐
  ┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
  └→ review_impl → filter_impl ─┬→ integrate ─────┬→ merge
                                └→ approve_merge ─┘
```

**Amended by G1000 (#748).** `review_design` and `review_impl` are replaced by seven review lenses per subject, `<lens>_design` and `<lens>_impl` for `intent`, `simplicity`, `truth`, `adversary`, `concurrency`, `rollout` and `experience`. Each set feeds one filter, `filter_design` or `filter_impl` (§3.8). Wherever the table and worked examples below name `review_design`, read the lenses joined by `filter_design`; for `review_impl`, read the impl lenses joined by `filter_impl`. `base` gates on `filter_design.summary`, `approve_merge` is ready once `filter_impl` is ok, and `design` dependents read `deps.filter_design.summary`. The graph's source of truth is the shipped template; SPEC §7 states the engine's rules for any graph.

```
design ─┬→ <7 lenses>_design → filter_design → approve_design → base → test_design → review_tests → implement → run_tests
        └ (each lens reads design.doc and goal.spec)                                                            │
   ┌────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
   └→ <7 lenses>_impl → filter_impl ─┬→ integrate ─────┬→ merge
                                     └→ approve_merge ─┘
```

**Why seven lenses.** The lens set comes from G1000's experiment (HISTORY §4). The five-lens hypothesis covered 12 of the 24 issues that would have caused harm; the seven lenses as run covered 23 of 24. Running all sixteen candidate lenses cost twice as much for one more low-severity issue. `intent` and `simplicity` are not skippable, because every change must serve the goal and stay simple; the other five are skippable, so a goal trims them with paired skips (`skip.concurrency_design` and `skip.concurrency_impl` for a docs-only goal).

**Bindings of the shipped graph** (moved from SPEC §7 when the default graph became configuration, owner decision 2026-11-01):

| Consumer | Binds | So it re-runs when |
|---|---|---|
| `base` | `deps.integrate.pr.head` (each unmerged dependency's PR head; the rest of the PR object is context), `deps.merge.merge_commit` (each merged dependency's merge commit; `null` while unmerged) | a dependency's PR head moves (correction or restack) or it merges; not when only a dependency PR's base changes |
| `run_tests`, `integrate` | `implement.code.tree` | the code tree differs, including after any restack |
| `review_tests` | `test_design.tests.change` (and its subject's output without `responses`, whose checkpoint fingerprints as `change`) | the tests' own diff changes |
| `review_impl` | `implement.code.change`, `test_design.tests.change`, `design.doc`, and its applied lenses | the goal's diff changes (a conflict-resolving rebase), not after a clean restack or a review-commit drop; or a lens is skipped or unskipped |
| `review_design`, `adversary_design` | `design.doc`, `goal.spec` (`review_design` also `settings.intent` and its applied lenses) | the design text or the spec changes; for `review_design`, also an intent change or a lens skip |
| `filter_design`, `filter_impl` | the subject, each lens's `summary`, and the `candidates` part (§4.9) | a lens re-runs, or a lens finding is added, closed or relabelled |
| `approve_design` | `design.summary`, `design.doc` (blob), `filter_design.summary` | the design text or the filter's verdict changes; never because of a rebase or a response |
| `approve_merge` | `implement.code.change`; nothing from `integrate` (the PR link is display only, §4.11) | the goal's diff changes |
| `design` (dependents) | `deps.design.doc`, gated on `deps.filter_design` being ok (not on the dependency's human approval) | a dependency's design text changes |
| `merge` | `integrate.pr` (number, url, head, tree, base) | the PR head or its base changes (deterministic rebuilds keep it) |

**Context edges and gates.** `base` needs a current `filter_design` (non-optional context), so skipping `approve_design` still waits for the lenses and the filter. `merge` needs every dependency's `merge` current (`dep_merges`), so dependents merge in order. Context edges are not in any fingerprint (§4.8).

**Policy invalidation in this graph:** `run_tests` (`verification.commands`), `integrate` (`verification.required_ci`), and `review_design` (`intent`). An intent change stales `review_design` on every open goal and does not count against the budget.

**Checkpoint bases:** `test_design.tests.base` and `implement.code.base` are both `base.base_commit`, the stack base, so `change` is the goal's own diff, review files excluded, never a dependency's code.

**A clean restack** (§4.21) carries `test_design` and `implement` to the rebased commits in `base`'s own push; only `run_tests` and `integrate` re-run, and no review or human gate is asked again. After a conflict in `implement`'s commits, `test_design` is still carried (its commits lie below the conflict) and only `implement` and its consumers re-run.

**Tradeoffs.** The human approves before CI. A dependent stacks only once its dependency's `integrate` is ok, so the chain root's required checks delay its dependents, and while a dependency's `integrate` re-runs or polls CI, its dependents' delivery is a named wait and their human items are hidden (their answers are kept). A CI failure that needs a code fix changes `change` and re-asks `approve_merge` (rare: `run_tests` already ran the tests locally). A stacked goal's GitHub PR targets its dependency's branch, so its GitHub diff is only its own code; with k ≥ 2 the stack PR shows the combined dependencies. `approve_merge` stays required in the default graph; a repository may mark it optional in its own `workflow.json`.

The revision 6.3 graph, kept for the record of its rationale:

```
design → review_design → approve_design → base → test_design → review_tests → implement → run_tests → review_impl ─┬→ integrate ─────┬→ merge
                                                                                                                  └→ approve_merge ─┘
```

`approve_merge` runs parallel to `integrate`: it needs only an approved `review_impl`, so the merge question can be answered before the goal's own CI (§3.16).

```
DISCOVERY   design(worker) → review_design(worker, review of design)
            → approve_design(human, review of design)
DELIVERY    base(op, workspace; stacks on integrated dependencies) → test_design(worker, workspace)
            → review_tests(worker, review of test_design) → implement(worker, workspace, preserve test_design)
            → run_tests(op, workspace) → review_impl(worker, review of implement)
            → integrate(op, workspace; PR, stack PR, required checks when the PR targets I)
              and, in parallel, approve_merge(human, review of implement)
            → merge(op, release_gate; waits for dependencies to merge)                        [terminal]
```

The full `workflow.json` is the shipped template, `plugins/zzzops/zzzops/templates/default/workflow.json`; SPEC §7 states the rules any graph must satisfy.

| Node | Key inputs (✱ = context: gates readiness, not fingerprinted) | Identity bound | Output |
|---|---|---|---|
| `design` | `goal.spec`; `deps.design.doc`; `deps.review_design.summary`✱ (optional) | dependency design blobs, reviewed only | `summary`, `doc` (artifact) |
| `review_design` | `goal.spec`, `design.doc`; subject `design` | design blob | review |
| `approve_design` | `design.summary`, `design.doc`; `review_design.summary`✱; subject `design` | design blob | human review |
| `base` | per dependency: `deps.merge.merge_commit` (optional) if merged, else `deps.integrate.pr.head`; `review_design.summary`✱ (not optional, so a skipped approval still needs an approved review; `model:M4`); `approve_design.summary`✱ (optional, so a skipped approval does not block) | dependency PR heads and merge commits | `branch`, `base_commit`, `stack`, `replay_map` |
| `test_design` | `design.doc`, `base.base_commit` | design blob, base | `tests` (checkpoint), `commands`; `frozen` on the record |
| `review_tests` | `design.doc`, `test_design.tests.change`; subject `test_design` | tests `change` | review |
| `implement` | `design.doc`, `test_design.tests.change`, `base.base_commit`; `test_design.commands`✱, `review_tests.summary`✱; `preserve: test_design` | tests `change`, base | `code` (checkpoint), `summary` |
| `run_tests` | `implement.code.tree`, `test_design.commands`; policy `verification.commands` | code `tree` | `result {passed, tree, details}` |
| `review_impl` | `design.doc`, `test_design.tests.change`, `implement.code.change`; `run_tests.result`✱; subject `implement` | code `change` | review |
| `integrate` | `implement.code.tree`, `base.base_commit` and its stack; `review_impl.summary`✱, `design.summary`✱, `run_tests.result`✱; policy `verification.required_ci` | code `tree` | `pr {number, url, head, tree, base}`, `ci {required, passed, failed}` or `ci {stacked: true, checks}` |
| `approve_merge` | `implement.code.change`; `implement.summary`✱, `design.summary`✱, `review_tests.summary`✱, `review_impl.summary`✱; subject `implement`. The PR link is display only. | code `change`, not the PR head | human review |
| `merge` | `integrate.pr`; `approve_merge.summary`✱, `base.base_commit`✱, `goal.links.issue`✱; `release_gate`; every dependency merged | PR head | `merge_commit`, `merged_at`; the goal then closes by the generic rule |

Because a context input must still resolve, and a producer resolves only when current and ok, each ✱ edge on an approval or a check is a gate: for example `merge` cannot run until `approve_merge` is approved, and `review_impl` cannot run until `run_tests` passed. `approve_merge` stays required: the default graph offers no skip for it (D3).

**Changed in revision 6:** `design` runs as a worker (A4); `approve_merge` no longer consumes `integrate` (A1); `base` stacks on integrated dependencies and gates on `review_design` (A1, `model:M4`); a dependent's `design` gates on the dependency's design review (`econ:M2`); `implement` gains a `summary` (`econ:M1`).

**Removed in revision 5 from the revision 4 graph:**
- `prepare`: the first artifact submit creates the work branch, and discovery reads `dev` without a worktree;
- `ci`: folded into `integrate`, which reads the PR's required checks itself, so no op runs without a lease.

**Removed from today's graph:**
- `decompose` and `review_decomposition`: there is no decomposition node; the design may propose child goals, and the agent creates them with `new` after `approve_design` is ok;
- all `authorize_*`, `publication_context`, `review_publication_context`, `observe_publication`, `review_publication` and `observe_merge`;
- the 37-node `INIT_PLAN.json` graph. The shipped template and this repository use the same `workflow.json`.

### 4.2 Capture to merge (goal G1002, which depends on G1001; abbreviated)

G1001 is a few steps ahead of G1002. G1002 stacks on G1001's PR.

1. **Capture.** In conversation, the root agent (label `claude:0a0a0a01`) writes the spec with the human and runs `new --file g1002.json`.
   - The CLI pushes `zzzops/goal/g1002` create-only (the next free id) and returns `next --goal 1002`, with the `design` action.
   - No work branch and no worktree exist yet.
   - The root dispatches `design` to a worker at once, with the label `claude:0a0a0a01/design-1`, and goes on capturing the next goal with the human.
2. **Design.** The worker runs `start 1002 design --as claude:0a0a0a01/design-1`.
   - The task card includes G1001's design (`deps.design.doc`, available because G1001's design review approved it) and the commands to read `dev` at the fetched integration tip.
   - The worker investigates `dev` with `git show`/`git grep` or the coordinator mirror, writes `design.md`, and runs `submit 1002 design --attempt 1 --output out.json --artifact design.md`. Had it needed the human, it would have submitted `--blocked` with a question, which joins the batch of human items.
   - One atomic push creates `zzzops/work/g1002` at the fetched integration tip with the `docs(review): design for G1002` commit, records the summary on `zzzops/goal/g1002`, and deletes the lease.
3. **Review and approval.** Another worker reviews the design and approves it; its report is another artifact commit.
   - `next` shows the human item "Approve the design for G1002?", with summary, review summary, facts line and the exact `answer 1002 approve_design --fp … --file …` command.
   - The agent presents it with the other pending design approvals. The user approves; the agent records what was approved in its own words and the user's words verbatim.
4. **Batch discovery.** Discovery across the backlog continues the same way.
   - With `stage_first`, `next` offers every other goal's discovery actions before any delivery.
   - It places the human items next to each other, so pending design approvals for G1005 and G1007 are asked together.
5. **Delivery stacks on the dependency.** `base` for G1002 waits only until G1001's `integrate` is current and ok ("waiting: G1001 integrate"); this is not a stuck item.
   - G1001's `integrate` opened PR #1180 from `zzzops/pr/g1001` into `dev`, at head P1. Because that PR targets `dev`, G1001's `integrate` is ok only once its required checks have passed, so G1002 stacks after G1001's CI, but before G1001 merges (§3.16).
   - `start 1002 base` creates the goal worktree and replays G1002's own commits onto P1. The branch so far contains only discovery artifacts, so the replay is trivially clean. Base commit: P1; `stack: [{G1001, P1}]`.
6. **Tests and implementation.**
   - `test_design` commits tests; its checkpoint is `{commit 9e1d, base P1, tree T1, change C1}`. `review_tests` approves, binding C1. C1 is G1002's own diff only; G1001's code is in the base, not in the change.
   - `implement`'s card lists `test_design.commands` to run before submitting. It commits code and a summary; the `preserve` check passes, and its checkpoint is `{commit b7a0, base P1, tree T2, change C2}`.
   - `run_tests` passes at T2, and `review_impl` approves, binding C2. The review commit moves the work-branch head but neither T2 nor C2, so nothing stales.
7. **Merge approval, before G1002's own CI.** As soon as `review_impl` is ok, `approve_merge` is asked about C2: "stacked on G1001 (PR #1180, not merged yet)", with `implement`'s summary, the diffstat and the review summaries. The human answers it in the same sitting as G1001's merge approval.
8. **Integration of a stacked PR.** `start 1002 integrate` builds `zzzops/pr/g1002`.
   - The generated todo drops 4 `docs(review):` commits. The rebuild uses the fixed committer and keeps author dates, so the PR head is reproducible.
   - It asserts the tree is still T2 and that the PR diff has no review files, pushes, and opens PR #1181 with base `zzzops/pr/g1001`. On GitHub the PR shows only G1002's code.
   - The PR's base is not `dev`, so `integrate` does not wait for required checks: it is ok at the expected head, with `ci: {stacked: true, checks: …}`.
   - `merge` waits: "waiting: G1001 merge".
9. **The dependency merges.** G1001's `merge` merges PR #1180 with merge commit M1 and, once it observes the merge, retargets PR #1181 to `dev` (`gh pr edit 1181 --base dev`). GitHub deletes `zzzops/pr/g1001`; if it does so first, it retargets PR #1181 itself. PR #1181 stays open.
10. **Restack.** G1002's `base` is stale, because its dependency is now merged (M1 replaces P1 in its inputs).
    - `start 1002 base` replays G1002's commits onto the new `dev` tip B1. The replay is clean, so the same push carries `test_design`'s and `implement`'s records forward to the rebased commits (`carried_by: "base"`), with the same changes C1 and C2 and new trees.
    - `review_tests`, `review_impl` and `approve_merge` stay current: they bind `change`. No agent phase and no human question.
    - `run_tests` re-runs on the new tree and passes. `integrate` rebuilds the PR head; the PR's base is `dev` now, so it reads the required checks. They are pending, so it records `blocked {waiting_for: time}` ("waiting until 14:35"). `next` reports `wake_at` 14:35; an unattended driver sleeps until then, and an attended agent tells the user and stops.
    - A later `start 1002 integrate` rebuilds the identical head (the push is a no-op) and finds the checks passed: `ok`.
11. **Merge.** Every dependency is merged, the PR targets `dev` with checks passed, and `approve_merge` is current. `start 1002 merge` merges with `--match-head-commit`, then retargets any PRs stacked on G1002 (none here). The same push records the merge and, because `merge` is the terminal node, closes G1002 and deletes its leases. ZzzOps deletes no branch: GitHub removes `zzzops/pr/g1002`, and `zzzops/work/g1002` keeps the artifacts reachable.

### 4.3 Correction cycles

- **Review requests changes.** `review_impl` returns `changes_requested` with finding `review_impl:1:1` targeting `implement` (its `target_fp` is the fingerprint of `implement`'s recorded output). The `review_impl` record is not ok.
  - `implement` is reopened, and its card carries the finding.
  - `run_tests` and `review_impl` keep their records but are blocked, because `implement` is not current.
  - `implement` attempt 2 fixes the code and must answer the finding (`responses: {"review_impl:1:1": "fixed: null check added"}`). Its new checkpoint `{T3, C3}` and the changed output kill the finding.
  - `run_tests` re-runs on T3, and `review_impl` re-runs on C3 with the interdiff. The reviewer marks the finding resolved and approves.
  - `integrate` rebuilds the PR branch at T3, and `approve_merge` is asked about C3.
- **Dispute.** `implement` re-submits the same code with `responses: {"review_impl:1:1": "disputed: the null case cannot occur because …"}`.
  - The output changed, so the finding dies. `review_impl`'s record is now non-ok with no live findings, so it is `ready (not_ok)` and re-runs; the reviewer sees the dispute. `run_tests` stays current: the tree did not change.
  - If the reviewer keeps the dispute open, the human is asked "uphold or waive?".
- **Too many corrections.** Under legacy policy this 12-node worked example stops after total counted re-runs exceed 18 (3 × 6 agents). With round_budget required, the current rule is per actor stage at >= the explicit limit or default 10 new-material-finding rounds, with its precise base-only/no-checkpoint and redefinition exemptions (§3.6; SPEC §4.10). The owner chooses continue, hold or cancel; inherited counts are retained.
- **Human rejects at `approve_merge`.**
  - The answer is `changes_requested` with the human's words as a finding targeting `implement` (or `design`). The ordinary loop follows.
  - "Cancel this goal" is an `edit` that sets `state: closed`, `closed.reason: cancelled` and a note, with `--base <goal commit>`. The item prints the exact command, with the values in a file (§3.15). Its output prints `gh pr close` for the goal's PR.
- **A required check fails** (on a PR into `dev`).
  - On the first failure for this PR head, `integrate` re-runs the failed jobs once and waits.
  - If they fail again, `integrate` records `ok: false` with finding `integrate:check-<name>` targeting `implement`.
  - A real failure: `implement` fixes it (`fixed: …`), the tree and `change` change, and `run_tests`, `review_impl` and `integrate` re-run, and `approve_merge` is asked again (the cost of approving before CI; §3.16). If a failure with the same normalized text recurs after that `fixed:` response, the finding escalates to the human and shows the actual response (G1040). A different failure is a new round; normalization ignores timings, commit ids, object addresses and tempfile names, not test/command names. A prior upheld decision applies only to the same normalized text.
  - A flaky failure: the agent reads the failed log (`gh run view --log-failed`). If it is a flake, it runs `reopen 1002 integrate --note "flaky"`. The reopen waives `integrate`'s own check findings, so `implement` is no longer reopened, and `integrate` re-runs with no `implement` run. Alternatively, `implement` can answer `disputed: flaky`: `integrate` then becomes `ready (not_ok)`, and `review_impl` does not re-run, because `responses` are not part of its subject fingerprint.
- **`dev` moves under an approved goal (clean rebase).** The dev ruleset requires an up-to-date branch, so `merge` records a finding on `base`, which reopens it.
  - `start 1002 base` replays the work branch onto the new `dev` without conflicts. The same push carries `test_design`'s and `implement`'s records forward to the rebased commits: new trees (they now include the newer `dev`), the same changes C1 and C2, and no agent phase.
  - **`run_tests` and `integrate` re-run**, because they bind `tree`. **`review_tests`, `review_impl` and `approve_merge` do not re-run:** they bind `change`, and the carried records are current, so the human is not asked again. This holds even when `implement` answered findings earlier, because `responses` are not part of the subject fingerprint. `merge` re-runs on the rebuilt PR head and merges.
- **A dependency is corrected after its dependent stacked.** G1001's `review_impl` requests changes; `implement` fixes it, and G1001's `integrate` pushes a new PR head P2 and waits for its required checks. Meanwhile G1002's delivery is a named wait ("waiting: G1001 integrate"), and its merge question, already answered, is kept but not shown.
  - Once G1001's checks pass, G1002's `base` is stale (its input P1 became P2). `start 1002 base` replays G1002's commits onto P2. The replay is clean, so the records are carried forward with the same changes.
  - Only `run_tests` and `integrate` re-run for G1002. Nothing is re-reviewed, and the human is not asked again.
- **Merge conflict (a rebase that changes the diff).**
  - `merge` records a finding on `base`, and `start 1002 base` rebases. The rebase conflicts, so it returns `blocked {conflict, agent}` with instructions, keeping the remote work tip and the onto commit it saw. The `retry` action carries the instructions, and the skill dispatches it to a worker, which resolves the conflict, runs `git -c core.editor=true rebase --continue`, and starts `base` again.
  - Nobody pushed the work branch meanwhile, so `base` accepts the hand-rebased branch.
  - Carry-forward is decided per node, from `base`'s commit map, which pairs the old and hand-rebased commits by position and keeps only identical patch ids. `test_design`'s commits sit below the conflict and map exactly, so its record is carried. Resolving the conflict changed one of `implement`'s commits, so nothing is carried for `implement`: it re-records, and its `change` is new, so `run_tests`, `review_impl`, `integrate` and `approve_merge` all re-run. `review_tests` stays current.
  - **Design and human design approval stay current.**
- **Dependencies that conflict with each other.** G1009 depends on G1004 and G1005, both unmerged, and their PR heads conflict. `base` for G1009 records `deps_conflict` and waits. No stack branch or stack PR is created. When G1004 merges, its merge commit is not in G1005's head, so the stack set becomes `dev` plus G1005's head; their combine still conflicts, so G1009 keeps waiting. This is the worst case: G1005's own `integrate` or `merge` then meets the conflict (`integrate` reads the PR's mergeability), and its `base` restacks onto `dev` with the conflict resolved, as its merge requires. Its new PR head contains G1004, so G1009's `base` re-runs, stacks onto that head alone, and so contains G1004's merged code. It is never a stuck item.

### 4.4 A chain answered in one sitting (G1001 → G1003 → G1007)

G1003 depends on G1001, and G1007 on G1003. All three designs were approved in one discovery batch, because each dependent's design waits only for its dependency's design review.

1. **Stacking.** G1001's `integrate` opens PR #1180 into `dev` and is ok once its required checks pass. Only then does G1003's `base` stack on `zzzops/pr/g1001`; G1003's `integrate` opens PR #1182 targeting `zzzops/pr/g1001`, and, being stacked, is ok without waiting for CI. So G1007 stacks on `zzzops/pr/g1003` at once, with PR #1185 targeting `zzzops/pr/g1003`. Only the chain root's CI delayed stacking. Each PR shows only its own goal's code.
2. **One sitting.** Each `approve_merge` becomes ready when that goal's `review_impl` is ok, before that goal's own CI. The human sees the three merge questions together, each saying what it is stacked on, and approves all three before G1001 merges.
3. **G1001 merges.** Its checks have passed and its approval is current, so its `merge` merges PR #1180 and, once the merge is observed, retargets PR #1182 to `dev`.
4. **G1003 follows.** Its `base` restacks onto `dev` cleanly and carries its records forward; `run_tests` and `integrate` re-run, and `integrate` now waits for the required checks of a PR into `dev`. Meanwhile G1007's delivery is a named wait ("waiting: G1003 integrate"), with its answered merge approval kept but not shown. When G1003's checks pass, G1007's `base` restacks onto G1003's new PR head the same way, and G1003's `merge` merges and then retargets PR #1185 to `dev`.
5. **G1007 follows** the same way.

All three merge in order with no further human input: the approvals bind `change`, and a clean restack keeps it. Only a restack that conflicts, or a CI failure that needs a code fix, would ask the human again.

---

## 5. Removal list and consequences

| # | Removed | Replaced by | Capability or protection that changes |
|---|---|---|---|
| R1 | Comment-envelope storage, receipts, transaction manifests, four caches, hydration checkpoints, the label storage lock, the v1/v2 converters (`comment_store.py`, `state_cache.py`, `migration_batch.py`, most of `goals.py`, `capture_v2.py`, the persistence half of `workflow.py`) | Goal documents on per-goal branches `zzzops/goal/g<id>` | **Lost:** tamper evidence based on immutable comments, and the per-mutation receipt history. **Gained:** history via `git log`, a real compare-and-swap per goal, and constant-cost reads. Old comments remain on GitHub, untouched, as the archive. |
| R2 | The correction compiler and admission phases (`graph_compiler.py`, `static_workflow.py`, `resolution_lifecycle.py`, finding intake, the interpret/admit/retain/resolve nodes, late-event review task sets) | The findings rule (§3.8) | **Lost:** the root "admission" gate before a reviewer's finding invalidates work. A finding now reopens its target directly; root can waive it by a visible edit. |
| R3 | The policy approval ceremony: approval digest, bindings, history, default provenance, upgrade classification, proposal store, PROJECT_AUDIT.md (about 1,800 of 2,276 lines in `policy.py`) | Review of policy changes on the `zzzops/policy/*` branch (a PR here); structural validation; the policy-branch block | **Lost:** a CLI-held record that a human approved each policy revision. GitHub PR review takes that role. Hand edits no longer disable the CLI. |
| R4 | Whole-policy contract hash, the 64-commit historical-policy walk, four projection forms, CI compatibility, `policy_only_base`, the DAG cutover ceremony, per-goal compiled graphs | Declared policy inputs; the graph read from dev | **Lost:** instruction-text edits no longer stale finished work automatically. Bump `rev` or reopen to force a re-run. |
| R5 | `CODEX_THREAD_ID` and root-id attestation, `bind`, policy receipts, runtime model evidence, inventory gates, `routing.py`, `route_choice` approvals | Holder labels; advisory `routing.tiers` | **Lost:** the engine no longer checks which session or model ran a phase. Independence becomes label inequality. Claude Code and Codex are treated equally. |
| R6 | Allocation and authorization grants, owned-path enforcement, per-file inventories, legacy `repository_workspace`, finish intents, single-commit topology, draft chains | Per-goal worktree, the `tree` and `change` identities, the `preserve` test-freeze rule | **Lost:** whitelist enforcement of which files a phase may touch. Reviewers see the diff instead. The genuine rule, that accepted tests stay frozen, is kept. |
| R7 | The dependency, blocker, archived-prerequisite, checkpoint-reconcile and graph-repair prepare/review/apply protocols | Direct edit, validation and impact preview | **Lost:** independent review and human approval of relationship edits. Validation, the `--base` fence and the preview are the safety net. |
| R8 | Retained attempt refs, compaction, the restack machine, base transitions, publication topology and the linear-stack rule, certificates, the stack B-tree, terminal reconciliation, four cleanup variants, `merge_reconciliation.py`, `stack_integration.py` | The `base`, `integrate` (with CI) and `merge` operations | **Lost:** curated RED/GREEN commits, native atomic stack merges, and remote retention of every attempt. Independent goals have sibling PRs; a dependent's PR stacks only on its own dependencies' PRs (§3.16). Merges are observe-then-act, in dependency order. |
| R9 | Release-plan issue #695, the release coordinator, lock and receipts (most of `releases.py`) | The `release` field, `releases.current`, the gate | **Lost:** the propose/freeze ceremony. Cutting is a human decision plus `git tag` and a policy change. |
| R10 | Heartbeat daemon, capacity ledger, label phase leases, the `reserve` CLI, observed-stop recovery, working inputs, response store | Empty-commit lease branches; staleness from commit time; reclaim; atomic finish | **Lost:** automatic renewal. An expired lease can be taken over; the late submit is rejected, and its work is kept in the local worktree, with salvage commands. |
| R11 | Installation-validation gate, `plugin_freshness.py`, `entropy_review.py` (dead), the legacy-cleanup gate | `package_status` self-check; `validate` | **Lost:** automatic detection of retired per-repo installs (D9 covers keeping `cleanup_legacy.py` as a manual tool). Automatic detection was restored without a gate by the `legacy` item (G1015). |
| R12 | v1 goal and phase model, intent/skill routing, the 52-operation dispatcher, `_private_main`, `policy_context` receipt caches | The 11-verb CLI (§3.15) | None functionally. |
| R13 | The default graph's ceremony nodes and the 37-node INIT_PLAN graph | The 12-node default graph | `approve_understanding` becomes `approve_design` (an inline decision). The repository and publication authorization nodes are gone. The merge decision is D3. |
| R14 | Revision 5's speculative guards (A5): the engine self-test with compiled-in constants, the verb-scoped diff check, the clock-skew refusal across all goal tips, `edit.confirm_threshold` and `edit --yes`, orphan-lease pruning inside every write, the work-in-progress push in `renew`, and the eight dependency miss reasons | Unit tests in CI (including a hostile global Git configuration); the `Engine:` trailer and the engine floor and ceiling; a skew warning on lease tips; `edit`'s preview and `--base`; orphans excluded from the frontier and reported by `validate`, deleted at goal close or by the one-line `REPAIR.md` recipe; one `dependency` reason plus the dependency's state | **Lost:** runtime refusal when an engine build computes identities or document changes wrongly; tests and the version rules are the protection. A crashed agent's committed but unpushed work stays on its machine (`REPAIR.md` has the push recipe). A fast clock produces a warning, not a refusal. |
| R15 | `bootstrap.py` and its test, and the bootstrap skill's `--intent bootstrap` path with its `BOOTSTRAP.json` provenance comparison and post-harness review checkpoint | The bootstrap skill as a checklist over `validate`, the shipped templates `zzzops/templates/default/` and plain `git`/`gh` (§3.17) | **Lost:** a recorded approval of the repository's initial capabilities. Bootstrap is now ordinary files landed on the integration branch, like any policy change. |

**Retained or adapted:**
- `package.py` (integrity check) and `concepts.py` (`bootstrap.py` is deleted; R15);
- the `managed_worktrees.py` porcelain parser and `_install_ignore`;
- the `git:<commit>:<path>` reference resolver (`workflow.py:840-850`);
- `classify_base_move`, as an optional explanation helper;
- the semantic-commit regex;
- the pure impact computation in `node_dependency_proposal` (`workflow.py:9602-9650`), as a seed for `edit`'s preview;
- `prompt_stats.py`, and packaging/marketplace tooling and tests.

---

## 6. Scope and architectural dependencies

**The redesign changes:** the persistence layer, evaluator, phase lifecycle, Git operations, policy format and loading, scheduling, CLI surface, the shipped skills and references (including the new `REPAIR.md` and `MIGRATING.md`), the default workflow, and the test suite. Packaging and marketplace distribution survive with small edits. Bootstrap becomes a skill checklist over shipped templates, and `bootstrap.py` is deleted (§3.17). The shipped skills are bootstrap, add-goal and execute.

**Dependency order:** each layer only needs the ones above it.
1. **Goal store and coordinator.** The fetch with its porcelain snapshot and lock retry, per-goal refs and id allocation, per-goal compare-and-swap with backoff, the per-goal descendant check, policy read by object id, the coordinator mirror, the policy-branch check, the integration-branch check, the engine floor and ceiling, and the environment checks.
2. **Workflow schema and pure evaluator.** Validation, fingerprints (allowlist, canonical JSON), the two-pass findings rule, `ok` semantics, the portfolio stuck rule with its named waits, the correction budget, the crash-loop and repeat caps, `wake_at`, and scheduling order.
3. **Lifecycle verbs.** Lease branches addressed by attempt, the atomic submit (including blocked outcomes), artifact commits with lazy work-branch creation, `tree` and `change`, the sync rule, fenced answers, and `edit` with its preview.
4. **Operations** (`git.base` with stacking and carry-forward, `checks.run`, `git.integrate` with stacked PRs and CI, `github.merge`), with the three outcome kinds.
5. **Default graph, templates, prompts and skills,** including the add-goal skill that flows into discovery, the execute skill's wait, scope and dispatch guidance, and the bootstrap checklist with the harness setup.
6. **Switch-over for this repository** (§7).
7. **Deletion** of the old modules and tests, then doc rewrites.

**Implementation strategy (D6):**
- Build the new core as new modules with their own contract tests beside the old code.
- Switch the entrypoint.
- Delete old modules wholesale in the same change that removes their tests.

There is no compatibility layer for retired internals. ZzzOps is not used to manage this work (proposal §2).

---

## 7. Migration (documentation only) and preservation

**Decision (human, revision 2):** ZzzOps has one known user, so the reset builds **no migration tooling**: no exporter, no golden diff, no issue rewriting, no automated cutover. The reset does four small things:

1. **Tag the old engine.** Tag `zzzops-pre-reset` at the dev commit the reset branch starts from (expected `64d5196`). The old engine stays runnable from a worktree of that tag, so old goal state can still be read.
2. **Convert this repository's policy.** The new `POLICY.json` (settings plus instructions, derived from revision 70, with `integration_branch` `dev` and `goals.first_id` 1000), `workflow.json`, the prompts, a hand-edited PROJECT.md, and the deletion of PROJECT_AUDIT.md land in the reset PR. The new engine needs these to run here.
3. **Write a migration guide** (`plugins/zzzops/zzzops/references/MIGRATING.md`) for an agent migrating goals on demand. It covers:
   - **Reading an old goal.** Use the issue text and the goal's branches. For phase outputs, use the old engine's read-only decoding from a worktree at `zzzops-pre-reset` (`comment_store.decode_envelope`). Never use `zzzops goal inspect`: it writes (`zzzops.py:3968`).
   - **Creating the new goal.** `zzzops new` with the spec, dependencies, release and a `links.issue` reference.
   - **Carrying finished work forward**, at the agent's judgment. Point the work branch `zzzops/work/g<id>` at the accepted checkpoint commit, then use `zzzops edit` to record finished nodes. The CLI completes checkpoints given as a commit (`base`, `tree`, `change`) and fingerprints for records marked current (SPEC §4.18). When unsure, leave a node to re-run.
   - **Old-node to new-node correspondence:** understand → design, review_understanding → review_design, approve_understanding → approve_design (`decided_by: "unknown (pre-reset)"`), test_design → test_design, review_test_design → review_tests, implement → implement, review_implement → review_impl. Publication nodes are not carried; the operations re-observe.
   - **Release assignments:** proposed per goal at triage and confirmed by the owner; release order is checked before any goal is created.
   - **Housekeeping:** closing moot or delivered issues, and removing stale labels, is optional.
4. **Delete nothing.** The reset never deletes or rewrites branches, worktrees, refs, issues or comments. Old comments stay on GitHub untouched as the archive.

**Preservation facts for whoever cleans up later** (from G §1.6):
- **Branches with unmerged work:** `fix/467-live-base-evidence` (local only, plus dirty edits), `feat/557-test-plan`, `spike/566-release-stack-flow` (local only), `fix/588-test-correction-recovery` (local only), `fix/663-validation-baseline`, `fix/523-explain-portfolio-order`.
- **Worktrees:** 17 have real uncommitted edits or untracked proposals.
- **Refs:** `refs/archive/*` and `refs/zzzops/*` refs with unmerged commits; origin `zzzops/attempts/566/*`, `zzzops/goal-723/*`, `zzzops/native-candidates/*`; commits referenced by `.zzzops/migration/reconciliation-20261002`.
- **`zzzops-goal-566`:** its dirty policy files are byte-identical to dev (`7ec4e25`). Nothing to preserve.
- **Safe to retire (merged content):** 189 merged attempt branches, about 230 managed worktrees (2.7 GB), 5 prunable registrations, `.git/zzzops/` (200 MB). Cleanup is your call, outside the reset.
- **Leftover old refs:** the new `zzzops/goal/g<id>`, `zzzops/work/g<id>`, `zzzops/pr/g<id>` and `zzzops/lease/…` branch names do not collide with the old `zzzops/goal-<n>/…` attempt branches.

---

## 8. Settled choices

These follow from the proposal's principles, the reviews and the human's instructions. The human may override any of them.

| # | Choice | Why |
|---|---|---|
| S1 | One graph replaces both the repository's 16-node DAG and INIT_PLAN's 37-node graph. | Two diverging defaults exist today. |
| S2 | Prompt edits never invalidate records; `rev` forces invalidation. Records keep the prompt blob as provenance. | §3.9: re-verify only for real uncertainty. A prompt edit stays visible (R4 L5). |
| S3 | No admission step and no separate resolver. The re-review resolves findings. Human decisions use the review shape. | §3.6. One correction mechanism for agents and humans. |
| S4 | No fan-out. Parallel reviewers are separate review nodes. There is no decomposition node; child goals proposed by a design are created with `new` after `approve_design` is ok. | Unused by the default graph (R2 R12); the human confirmed decomposition was never used; no unapproved fan-out (R7 M9). |
| S5 | One work branch and one local worktree per goal, the branch created lazily by the first artifact submit. Discovery needs no worktree. Reviewers write artifacts by plumbing. At most one workspace lease per goal at a time, ops included. A stack branch exists only while a goal's stack set has two or more members (`x:M2`). Closed goals' worktrees are removed opportunistically on every machine. | Isolation without hundreds of worktrees (R1 M6, R6 F5, R6 F12, `evo:M9`). |
| S6 | Design, test-plan and review texts all use the `docs(review):` artifact path. They are referenced by blob, so they survive rebases. | One artifact mechanism; workflow-only documents never reach dev. |
| S7 | An identical scoped change across a sync carries its producer and retains change-bound reviews and approvals; tree-bound checks re-run. Merge mode uses the actual sync commit, legacy rebase its exact replay map (§3.16). | Two identities preserve judgments without skipping verification. G1039 widens carry with transient -U0 comparison plus conservative positional union checks (§3.16). |
| S8 | A `zzzops/policy/*` branch on the remote blocks `start` everywhere, for agent and op nodes, until it lands (its tip is an ancestor of the integration branch, or its policy files equal the integration branch's after a squash) or is deleted. It is detected in the ordinary fetch, with no GitHub API call. | The human's rule and the human's chosen mechanism (D11); unblocking does not depend on GitHub's branch deletion (`gen:L3`, `x:M4`). |
| S9 | No offline mode for mutations. Read-only verbs may use the last fetch, marked `current: false`. | Never silently claim current policy. |
| S10 | Advisory model routing only. | Model choice is agent judgment. |
| S11 | Policy is read by object id. The coordinator worktree is a best-effort, self-healing mirror. | Concurrency-safe (R1 H3). The proposal's coordinator worktree is kept for agents. |
| S12 | Request, byte and push counts are hard CI budgets. Wall time is diagnostic only. | Measured round-trip time makes wall time host-dependent. |
| S13 | Every push names its expected old value from the invocation's own fetch output. | The bare form destroyed a concurrent commit in experiment (R1 H2). |
| S14 | integrate builds review-free tests/implementation PR commits on the last recorded base, with increasing dates and idempotent head reuse. Work history is untouched; merge-mode base advances it only forward. | Keeps worktrees/artifacts reachable, conventional release effects, truthful review views and stable repeated integration (G1038). |
| S15 | Leases live under `zzzops/lease/g<id>/<node>`. | A single-`*` refspec can then fetch exactly the leases (R1 M1). |
| S16 | Goals close by the generic rule in the same push that makes every terminal node current and ok; that push deletes the goal's leases and stack branch. Goal branches are never deleted; ids are never reused. Work branches are kept by default, deletable once no open goal depends on them (`REPAIR.md`). `merge` deletes no branches; it retargets stacked dependents' PRs once their dependency's merge is observed. | Prevents re-staling merged goals and duplicate ids (R2 #43/#44); keeps artifact blobs reachable while they are needed (R7 H6, R6 F3), without a mandatory permanent archive (`cons` §4.3, `evo:L1`). |
| S17 | Goal `state: held` pauses one goal; its running phases may finish. A global pause is stopping the agents, or pushing a policy branch. | Explicit human control (charter); `hold` must not destroy the phases it pauses (R7 H5). |

---

## 9. Decisions requiring human approval

| # | Decision | Status / recommendation | Tradeoff |
|---|---|---|---|
| D1 | Where goal state lives | **Approved (revision 2), modified in revision 5:** one branch per goal, `zzzops/goal/g<id>`, holding `goal.json`, instead of the single `zzzops/state` branch. Multi-goal edits are one atomic push of several goal refs. | Writes to different goals never contend, which removes the measured write ceiling (R3 F13, R1 M3), and the descendant check is per goal. The fetch lists one goal ref per goal ever created, since goal branches are never deleted. |
| D2 | Where the spec text lives | **Approved (revision 3):** in the goal document. | A single source of truth and no GitHub reads in `next`. You edit the spec through an agent or a direct edit, not an issue editor. |
| D3 | Merge decision | **Approved.** An `approve_merge` human review node, answered in conversation and batchable across goals. Since revision 6 it is ready as soon as `review_impl` is ok, before the goal's own CI, so a chain's merge approvals can be answered in one sitting (§3.16). **It stays required (revision 6, A2):** the default graph offers no skip for it, and the add-goal skill never suggests one. The human's reason: "we shouldn't really encourage not reading the code as that's already got me into messes". A repository may still mark it optional in its own `workflow.json`; this design does not recommend it. Before presenting the item, the skill checks `gh pr view`; a PR you merged yourself on GitHub into the integration branch is recorded with `decided_by` = the merger and `quote` = "Merged PR #N on GitHub at T", and `merge` records the merge. | GitHub won't let you approve PRs authored by your own account. The alternative is merging every PR by hand on GitHub, which means more supervision. Every goal ends at this gate, which is the cost of reading the code. |
| D4 | Design approval | **Approved.** On by default. A per-goal `skip: {approve_design: reason}`, agreed at capture, turns it off for small, low-risk goals. | Explicit human control of scope, versus fewer interruptions. With discovery batched (§3.12), the cost of keeping it on is lower. |
| D5 | Stacked dependencies | **Approved (revision 6): stacked delivery** (reverses revision 4's "no stacking"). A dependent's `base` stacks once every dependency is merged or has a current, ok `integrate` (for a PR into the integration branch, with its required checks passed; revision 6.1). Its stack set is the unmerged dependencies' PR heads, plus the integration tip when there are none or when a merged dependency is not contained in every head, minus members that are ancestors of others; it stacks onto that single commit, or onto a combine commit on `zzzops/stack/g<id>` when there are two or more. Only the goal's own change is synced (merge when required, legacy rebase otherwise), and reviews bind only its own diff. Its GitHub PR targets the same base; when the stack set has two or more members a draft stack PR into the integration branch shows the combination. PRs are retargeted explicitly, a dependency's dependents only once its merge is observed. Required checks are enforced only on PRs into the integration branch, and `merge` waits for every dependency to merge, by which time `base` has restacked. A restack carries forward each node whose commits keep their patch ids (A6). Conflicting dependencies are a named wait. `approve_merge` runs parallel to `integrate` (§3.16). | The human approves before the goal's own CI; a CI failure that needs a code fix changes `change` and re-asks (rare, because `run_tests` already ran the tests locally). A stacked goal's GitHub PR shows only its own code; with a stack set of two or more members the stack PR shows the combined dependencies. Stacking waits for the chain root's CI, and while a dependency's `integrate` re-runs, its dependents' items are hidden. v1 does not resolve conflicts between dependencies. |
| D6 | Implementation strategy | **Approved.** Build the new core alongside, switch over, then delete. | `workflow.py` couples every removed mechanism. The switch-over is a single event. |
| D7 | Leases | **Approved:** empty commits on per-lease branches, with staleness from commit time. The name is now `zzzops/lease/g<id>/<node>` (S15). Revision 5: each lease records its own timeout, and lease verbs address it by attempt. | — |
| D8 | Existing goals and local state | **Resolved:** migration is documentation only, and the reset deletes nothing. | — |
| D9 | Peripheral features | **Approved, modified:** keep bootstrap only, as a skill checklist (revision 6 deletes `bootstrap.py`; §3.17). Drop feedback (the human will rebuild it as transcript-based), coaching, diagnostics, entropy, refill/suggest and execution reports. | These features disappear until rebuilt on the new state. |
| D10 | Goal ids | **Approved.** `G<id>`, never reused, with no GitHub issue required (`links.issue` optional). Since revision 5 (with D1), an id is allocated by a create-only push of `zzzops/goal/g<id>` with `id = max(existing) + 1`, retrying with the next id on collision. Start above the highest existing issue number (`settings.goals.first_id` = 1000 here), so `G1002`-style ids never collide with old `#812` references. | Goal creation doesn't touch issues, and there is one place for state. You lose issue pages and notifications per goal. |
| D11 | How an open policy change is detected | **Approved (revision 4):** by a branch prefix. Any `zzzops/policy/*` branch on the remote blocks new work; deleting it (normally by landing it on dev) unblocks. The earlier PR-query design and its draft and outage questions are withdrawn. | No GitHub API in normal work, no rate-limit ceiling, no outage question. A policy change made on a misnamed branch isn't noticed until it lands; an optional repository CI check closes that gap. In a monorepo, any team's policy branch blocks every team's new work (`gen:L2`). |
| D12 | Default graph | **Approved (revision 5):** 12 nodes (§4.1). `prepare` is removed: the first artifact submit creates the work branch, and discovery creates no worktree. `ci` is folded into `integrate`, which reads the required checks itself. `review_tests` is kept. There is no decomposition node. | Fewer nodes, no worktree per backlog goal in discovery, and no op that runs without a lease. Keeping `review_tests` costs one review per goal but catches weak tests before implementation. |
| D13 | Policy disclosure | **Approved (revision 5): progressive disclosure kept.** POLICY.json stays separate from `workflow.json`, with per-section instructions selected per node and shown in the task card, and advisory `routing.tiers`. Moving instructions to AGENTS.md/CLAUDE.md and merging POLICY.json into `workflow.json` (R6 F8, F9) are rejected. | Two policy files instead of one, in exchange for each node seeing only the instructions it needs; AGENTS.md and CLAUDE.md load everything into every context. |
| D14 | Code identity | **Approved (revision 5): two identities.** Checkpoints carry `tree` and `change` (§3.4). `run_tests` and `integrate` bind `tree`; `review_tests`, `review_impl`, `approve_design` (the design blob) and `approve_merge` bind `change`. This replaces the revision 4 S7. | A carried sync no longer re-runs change-bound reviews or re-asks the merge approval, while tests always re-run on different code. The cost is one more identity to compute, and trusting that a rebase which leaves the goal's diff unchanged changes nothing a reviewer judged. |

---

## 10. Design-level validation contract

The implementation is accepted when all of these hold. Commands and fixtures go in `IMPLEMENTATION_PLAN.md`.

1. **Determinism.** Two `next` runs on unchanged state are byte-identical. The frontier is a pure function of (graph, documents, leases, settings, now).
2. **Bounded cost.** Git round trips, pushes, API calls and comment reads per verb are identical with 0 and with 2,000 archived comments, and within the §3.15 counts (as amended by G1015); the legacy check reads no issue bodies or comments; the `next` embedded in `submit` and an op's finish do not fetch again, and `start G base` fetches its dependencies' PR branches in its one fetch. `next` reads all documents it needs in one batch, and skips closed goals that no open goal depends on. Task cards are at most 4 KB and `next` at most 8 KB.
3. **Name independence.** The full journey passes on a graph with every node renamed. Engine source contains no default node id, and ops read only their inputs.
4. **Code identity.** `tree` is identical across `docs(review):` commits, across the `base-i1-r1-i2-r2` drop-rebase, and with a dirty or differently checked-out worktree. `integrate` asserts it. The PR branch's diff from its base contains no review files, and the work branch is unchanged. Another clone recomputes `tree` from `commit` and gets the same id.
5. **Change-identity survival.** `change` is identical across review-commit drops, the PR-branch rebuild, a clean rebase and a clean restack, and differs after a conflict-resolving rebase. In the §4.3 clean-rebase scenario, with `implement` having answered a `run_tests` finding earlier, `run_tests` and `integrate` re-run while `review_tests`, `review_impl` and `approve_merge` do not (the carried-forward records are current); in the conflict scenario, `review_impl` and `approve_merge` re-run. `design` and `approve_design` never re-run because of a rebase.
6. **Corrections.** `changes_requested` reopens the target with zero extra phases: a finding submitted while its carrier is `running` gets its `target_fp`, because the running state carries the input fingerprint computed from recorded values, also while a dependency's `integrate` polls. A finding on an op target dies once the op has a later attempt, also with byte-identical output and with every clock equal (a fixed `ZZZOPS_NOW`). Every ready node's card carries every live finding targeting it, including a node that is both stale and reopened. A reopened submit without `responses` is rejected. A dispute reaches the reviewer (its record becomes `ready (not_ok)`). A stale review's findings are never live. A dispute the reviewer keeps open produces a human item; a new finding starts at round 1; the engine's automatic responses and findings carried by a human node never escalate; a dispute item for an op-carried finding offers no waive, but offers `reopen G <op>`, and offers no skip when the op is terminal; an op's blocked records keep its previous findings' `upheld`, notes and rounds. A re-review uses the scoped diff/log/range-diff for its base/mode and separate sync remerge-diffs, leaving target movement out of the goal change while exposing conflict resolution; identical change omits interdiff (G1038). A reopen of a stale node is not dropped. Human rejection reopens its subject.
7. **`ok` semantics.** Every record carries `ok`. A producer satisfies its consumers only when current and ok. A non-ok record with no live findings is ready; one with live findings stays blocked while its targets are reopened. No workflow field `require` exists.
8. **Portfolio stuck rule and no dead ends** (property test). For randomized sequences of submits, reopens, skips, graph edits, dependency changes, holds and cancellations, every open, non-held goal yields an action, a human item, or a wait naming a time, a release gate, a live lease, a dependency that is open or held, a `deps_conflict`, or an engine upgrade. A goal waiting only on an open or held dependency gets no stuck item; a goal whose dependency is stuck, cancelled or invalid gets one naming it, with drop, retarget and cancel commands. A dependency closed done without a merge does not hold back its dependents and is never stacked on. A goal closed done whose PR was never merged cannot hold a dependent in an op-to-op loop. An open goal whose terminal nodes are all current gets an item that closes it.
9. **Budgets.** Round-budget activation preserves prior cumulative counts and changes only future counting/gating: a first done agent record with new material findings may count; carrying/narrowing/notes and blocked/op/human records do not. A no-checkpoint base-only stale run is free even with a new finding, while checkpoint-producing/base+code-stale work counts. At stage used>=limit, starts/reclaims and action listing agree; other stages/ops/human items proceed. Continue raises the shared override to that stage's used+10. Legacy rule/JSON shape remains without the capability. Crash/dispute/repeat caps stay unchanged.
10. **Policy.** From any worktree, the coordinator commit equals the fetched `origin/dev`. A `zzzops/policy/*` branch on the remote blocks `start` for agent and op nodes, naming the branch and how to resolve it; deleting it unblocks, and so does landing it (its tip an ancestor of `dev`, or, after a squash landing, its `.zzzops/` files equal to `dev`'s). No verb makes a GitHub API call except the `integrate` and `merge` operations, `base` closing a stack PR, the legacy check (§3.15), and the best-effort branch-deletion read in repository `validate` with `settings.branching` (G1031). An undeclared setting change stales nothing; `verification.required_ci` stales only `integrate`. Adding or removing a context edge stales nothing. `validate --policy --dir D` prints the impact on in-flight goals. A clone whose integration branch differs from `settings.integration_branch` is refused. Twenty concurrent invocations after dev moves all succeed. Out-of-range settings make the policy invalid.
11. **Leases and pushes.** Create-only claims (one winner), including two claims built from identical bytes in the same second. Renew, with the attempt as the handle after any number of renewals; renew pushes only the lease. Reclaim after the lease's own recorded timeout, unaffected by a later policy edit. `--force`. `abandon` leaves an expired lease, the next start is a new attempt, and a forced-off agent's late `submit` or `renew` is refused with `superseded`, even before a reclaim. The atomic submit is fenced after a reclaim, and the goal is not updated. A lost response is reported as applied only to the holder that submitted it. Every push carries an explicit expected value; a test with a concurrent fetch shows no lost commit. A push refused by a server rule is reported as `push_refused` at once, not as contention. Orphan and unparsable leases are excluded and reported, never deleted by a write; a held goal's running leases are not orphans; unknown lease trailers are ignored. A future-dated lease tip gives a warning; a mass expiry requires `--force` for reclaims.
12. **Sync.** Every sync-rule case, including automatic rebase over remote-only review commits with `tree` preserved, the local-ahead push, patch equivalence that treats a whitespace-only difference as different, and the refusal with working salvage commands.
13. **Operations.** Each op's `done`, `blocked` (agent, human, time, dependency) and crash paths. Required checks: pending is shown as waiting with 5, 10, 20, 30-minute backoff, then a human item after `ci_timeout_minutes`; the first failure per head is re-run once; findings have fixed ids per check name, and the same id after a `fixed:` response from `implement` escalates. `reopen integrate` after a twice-failed check re-runs `integrate` without an `implement` run. A crash after the PR push is retried without a dead end. A PR merged or closed by hand on GitHub is observed; a merged PR with other code, or one merged into a base other than the integration branch, is a human item. A PR into the integration branch that conflicts with it gets a `base` finding from `integrate` instead of a CI wait. `merge` with every dependency merged but a PR on another base asks the human and raises no finding. A merge conflict leads to a base sync in the selected mode. Merge resume compares against its conflicted tree and stages only listed files; legacy rebase resolution remains accepted. Discovery stays current. `base`'s first run rebases onto the current stack base, and a work branch it creates starts there locally and remotely. A review commit that lands on the work branch during a restack never leaves `base` at `sync_refused`. `base`'s GitHub calls happen only after its push succeeds. With `skip.approve_design`, `base` still waits for an approved `review_design`. `merge` uses `settings.merge.method`, and a GitHub-blocked merge waits and then asks. `merge` deletes no branches, and artifact blobs of a merged goal stay readable by its dependents.
14. **Deterministic integrate rebuild.** Rebuilding identical code on the same base yields the identical PR head, so re-running `integrate` on unchanged code leaves `merge` current.
15. **Generic close.** When every terminal node is current and ok, the same push closes the goal and deletes its leases and stack branch, under a renamed graph and with any terminal op. Deleting a cancelled goal's stack branch lets GitHub close its PR and stack PR; `edit` makes no GitHub call.
16. **Scheduling.** With `stage_first`, all ready discovery actions and human items across goals precede delivery actions. A dependent goal's discovery runs while its dependency is unmerged, against reviewed dependency designs, so a chain's design approvals can be answered in one batch. `new` returns that goal's discovery action, a worker action, and creates neither a work branch nor a worktree; the first artifact submit creates the work branch. `next --goal` shows `also_pending` for the rest of the portfolio. `wake_at` equals the earliest `retry_after` or live-lease expiry in scope, ignores release gates, and is `null` when there is none.
17. **Per-goal refs and id allocation.** Concurrent `new` calls receive distinct ids, the loser retrying with the next id. Ids are never reused, including after a goal ref disappears. A multi-goal edit is one atomic push. Writes to different goals never contend; concurrent writes to one goal retry with backoff within the deadline.
18. **Editing.** Editing an invalid document. Impact preview. `--base` refuses an edit of a changed goal; a whole-document edit is never re-applied over a concurrent change. Cycle, size and release-order errors. A `skip` of a terminal node, a reopen of a goal closed as done, and `closed.reason: done` while a terminal node is not current are refused.
19. **Fenced answers.** `answer` with a fingerprint that no longer matches the item is refused with `fp_mismatch` and shows the current question; a retried identical answer is reported as applied.
20. **Goal integrity.** A force-pushed or deleted goal branch is detected per goal by the non-`+` fetch; writes to it are refused, and other goals are unaffected.
21. **Engine capabilities.** An engine that lacks a capability the policy requires refuses writes while reads still work. A goal with an unknown schema refuses writes to that goal, and its dependents wait for an engine upgrade. New policy keys are reported to an older engine as `engine_too_old`. A record whose fingerprint is in another version is stale. Every goal commit carries the `Engine:` and `State:` trailers and an `Outcome:` line.
22. **Identity isolation.** `change` and `code_tree` are identical under a hostile global Git configuration and attributes file (a CI unit test), and a failing `git diff` is an error, never an empty `change`.
23. **Environment.** The CLI refuses below Git 2.41, and the ops that need `gh` refuse without it or without `gh auth`. Under `CODEX_SANDBOX_NETWORK_DISABLED=1` or a read-only Git directory, every verb refuses with `environment`, not `remote`. A shallow clone is refused. One fenced-submit smoke test runs against real GitHub over HTTPS.
24. **Switch-over and bootstrap.** This repository's converted policy and workflow validate, and so do the shipped templates (`validate --policy --dir`, with no remote). A repository without `.zzzops/workflow.json` reports `not_bootstrapped`. `MIGRATING.md` and `REPAIR.md` exist, and their worked examples run. The reset deletes nothing.
25. **Stacked delivery.**
    - A 3-goal chain G1001 → G1003 → G1007 in which all three merge approvals are answered in one sitting before G1001 merges; then all three merge in order with no further human input.
    - A 2-dependency goal with a stack PR, which is closed (and its stack branch deleted) once the stack set drops to one member: one dependency merged and the other's head contains it. The stack PR is closed only after `base`'s push succeeds, and the goal's PR is retargeted before the stack branch is deleted, so it stays open.
    - A goal whose dependencies are transitive (one dependency stacked on the other) stacks on the later head alone, with no combine commit.
    - A dependency correction that restacks a dependent with no re-review and no re-ask.
    - An inter-dependency conflict that waits, then proceeds once the stack set combines cleanly (after a dependency merges and, if still needed, the remaining dependency rebases onto the integration branch); it is never a stuck item.
    - A dependency merge that retargets its dependents' PRs once the merge is observed, including a merge done by hand on GitHub; a refused or queued merge retargets nothing. A stacked PR merged by hand into its dependency's branch is a human item.
    - After one of two dependencies merges, the goal's base contains the merged code: the stack set adds the integration tip whenever the remaining head does not contain the merged dependency.
    - A stacked PR is ok without waiting for required checks; after the restack onto the integration branch, the checks are enforced before `merge`.
    - A dependent stacks only once its chain root's required checks pass. While a dependency's `integrate` re-runs or polls, the dependent's delivery is a named wait, its answered approvals are kept but not shown, and they reappear unchanged once the dependency is current.
26. **Scoped checkpoints and forward sync (G1038).** Checkpoints default to HEAD, with frozen paths calculated before a preserved checkpoint's scoped change; no-commit reruns keep that change when F is unchanged. Test fixes may follow implementation without rewriting pushed work. Agent merges/nonconventional subjects/non-test test-writer commits are refused, and transient edits to frozen paths still fail. Merge-mode base moves work only forward, carries only checkpoints in the synced work history with identical scoped changes, and preserves conflict resolutions. Dropping/rewriting dependencies and target changes retain only the goal's own diff. Rollback is blocked for branches with sync merges; legacy mode and golden node fingerprints remain compatible.

**Added after approval** (each with its goal's tests):

27. **Idempotent `new` (G1001).** Rerunning the same `new` after any failure, including an uncertain push, returns the existing goal with `recovered: true`; a reused `request_key` with different contents is refused; concurrent identical calls end as one goal.
28. **Live inputs (G1014).** An edit that changes a running phase's inputs lists its lease, with the restart commands, in both the preview and the result, and the phase's `renew` reports `inputs_changed`.
29. **Legacy detection (G1015).** Pre-reset state is disclosed as a non-blocking `legacy` item within the §3.15 counts; an old-format policy is `legacy_policy`.
30. **Explained cards (G1016, G1018).** Every started card says why it re-runs (`stale_because`, `changed`); `abandon` prints its restart command; a submit refused for responses lists the findings to answer; checkpoint inputs selected by `change` or `tree` show the full checkpoint; cards over 4,096 bytes shrink in a fixed order.
31. **Conflicting PRs (G1021).** A PR that conflicts with `I` gives a `conflict` finding on `base` on the first `integrate` run, and a PR with no checks at all becomes a human question after 15 minutes.
32. **Lenses (G1000, G1020).** The template graph validates; lens findings carry `impact` and `material`; the filter never demotes a material claim; a non-skippable node cannot be skipped, and a lens cannot be skipped while it has open findings that are not notes; a notes-only lens approves; an intent change stales the intent lenses; the PR body lists the reviews and skips.
33. **Multi-lens reviewers (G1022).** The template graph has 15 nodes; a reviewer card carries its lens checklist, and new findings carry a declared `lens`; a goal removes an optional lens with `<node>:<lens>` and is refused a mandatory one; a lens skip stales the reviewer without budget and drops no finding; nodes without `lenses` keep their 1.1 definition fingerprints.

---

**Default update acceptance (G1024).** Identical reviewed defaults are quiet; upstream edits show working quoted diff/merge commands, including paths with spaces; non-overlap preserves local edits and overlap warns on markers. Record-only decline stays quiet until another upstream change. Inference recognizes history matches and leaves custom content unknown. Added/removed/deleted files, invalid/newer records, unknown bases and tombstones stay advisory under version skew. Both policy-preview and directory comparison use their selected source; explicit next stays capped while writes omit notices. Current history bytes and the pinned seed remain bundled. Targeted tests cover these behaviors without repeated full journeys.

## 11. Change log

### Revision 6.3

The decision record is REV6 §H, items H26–H30 ([index](HISTORY.md#3-amendment-index)). Review source: `m5`, the exhaustive model check of revision 6.2.

| Change | Source |
|---|---|
| A workspace re-run that adds no commit defaults to its previous checkpoint, followed through `base`'s maps; `checkpoint_required` when it cannot be followed; §3.7, §3.16, §10 item 26 (H26) | `m5:N1` |
| `replay_pos` declared in the default graph's `base` outputs (H27; SPEC only) | `m5:N2` |
| Retargeting wording: explicit whenever ZzzOps changes a target; GitHub may retarget first after a merge; §3.16 (H28) | `m5:N3` |
| A crash-loop item on an over-budget agent node prints the budget raise before one more try; §3.6 (H29) | `m5:N4` |
| The suggested checkpoint is computed at submit, so a reclaimed phase keeps it; §3.7 (H30) | `m5:N5` |

### Revision 6.2

The decision record is REV6 §H, items H23–H25 ([index](HISTORY.md#3-amendment-index)). Review source: `x2`, the final cross-check of revision 6.1 against REV6, DESIGN and SPEC.

| Change | Source |
|---|---|
| Retiring a stack, after `base`'s push: retarget the goal's PR, close the stack PR, then delete the stack branch; §3.16, §10 item 25 (H23) | `x2:M1` |
| The op-finding cap counts a recurring finding only while the op's inputs are unchanged; §3.6, §3.14 table, §10 item 9 (H23) | `x2:M2` |
| A review commit racing a hand-resolved conflict is re-applied on the resolved branch instead of ending in `sync_refused` (H23; SPEC only, DESIGN already promised it) | `x2:M4` |
| After a conflict, the suggested checkpoint follows the replay's positional pairs (`replay_pos`); carry-forward still uses identical pairs only; §3.16, §10 item 26 (H23) | `x2:M5`, `m4:F5` |
| A finding records its target's attempt (`target_attempt`); an op target answers by a later attempt, with no wall-clock comparison; §3.8, §10 item 6 (H24, revising H22) | `x2:M3` |
| A running state's fingerprint is computed from recorded values; §3.6 table, §10 item 6 (H25) | `x2:L1` |
| `start base` cost counts retiring a stack PR (2–4 GitHub calls, one stack-ref push); §3.1, §3.15 (H25) | `x2:L2` |
| Carried responses: dropped only when no record has their finding open, all kept while the node has live findings; §3.16, §10 item 26 (H25) | `x2:L3` |
| The op-finding cap counts done records only; §3.6, §10 item 9 (H25) | `x2:L5` |
| The work branch may be created by `base`; this log's revision 6.1 heading names H1–H22 (H25) | `x2:L6` |
| Squash landing: stated limitation once another policy change lands; H16's test kept; §3.10 (H25) | `x2:L7` |
| Crash-loop and op-dispute items offer no skip of a terminal node; §3.6, §3.8, §10 items 6 and 9 (H25) | `x2:L8` |
| `merge` reads the live PR base before merging; §3.9 (H25) | `x2:L9` |
| Goal size: about 200 commits, a stated limitation of the commit map; §3.16 (H25) | `x2:L10` |
| §10 item 15 matches H15: GitHub closes a cancelled goal's PRs when its stack branch is deleted (H25) | `x2:L11` |
| SPEC only: the Blocked `repeats` comment (H25) | `x2:L4` |

### Revision 6.1

The decision record is REV6 §H (items H1–H22 below; [index](HISTORY.md#3-amendment-index)). Review sources, fourth pass: `x` cross-check of REV6, DESIGN and SPEC; `m4` model check of the SPEC rules.

| Change | Source |
|---|---|
| A `running` state carries the current input fingerprint (or `null`), so findings from a running carrier get their `target_fp`; §3.6 state table, §3.8, §10 item 6 (H1) | `x:C1`, `m4:F10` |
| Stacking waits for the chain root's CI; while a dependency's `integrate` re-runs or polls, dependents' delivery is a named wait with approvals kept but hidden; §3.16 rule and tradeoff, §4.2 step 5, §4.4 steps 1, 2 and 4, §4.3 dependency correction, §1 and §3.12 wording, §10 item 25 (H2) | `x:H1`, `m4:F3` |
| `base` records its commit map (`replay_map`), also after a hand-resolved conflict; carry-forward decided per node on the commits at and below its checkpoint; the suggested checkpoint follows the map and is the default only when it contains the producers' current checkpoints; §3.7, §3.9, §3.16, §4.3, §10 item 26 (H3) | `x:H2`, `m4:F5` |
| A restack racing a review commit replays again instead of ending in `sync_refused` (H4) | `x:H3` |
| `submit` and `renew` on an abandoned lease refuse with `superseded` (H5) | `x:M5` |
| Carry-forward drops `responses` to findings no longer live (H6) | `x:M6` |
| `closed.reason: done` only when every terminal node is current; repeat cap on an op's recurring finding; only open or held dependencies are unmerged; `merge`'s PR-base mismatch asks the human (H7) | `x:M8`, `m4:F1` (a), (b) |
| Dependents retargeted only after a merge is observed, hand merges included; PR base read in `integrate` and `merge`; a PR merged into another base is a human item; GitHub merges recorded as approval only into the integration branch (H8) | `x:M7`, `m4:F2`, `m4:F7`, `x:L13` |
| A work branch created by `base` starts at the stack base, locally too (H9) | `x:M9` |
| `integrate` turns a conflicting PR into the integration branch into a `base` finding (H10) | `x:M11` |
| Repeat cap counts agent waits whatever the reason, and covers `waiting_for: agent` only (H11) | `m4:F4`, `x:M10` |
| Correction budget counts every agent re-run except `def`- or policy-only re-runs and carried records; still 3 × 6 = 18; §1, §3.6, §3.8, §4.3, §10 item 9 (H12, revising B16) | `m4:F8` |
| Stack set drops members that are ancestors of others (H13) | `m4:F6` |
| `base`'s GitHub calls only after its push succeeds (H14) | `m4:F9` |
| Op blocked records keep the previous findings inert; op-carried dispute items offer `reopen G <op>`; a cancelled goal's PR is closed by GitHub when its stack branch is deleted, which is intended (H15) | `m4:F10` |
| An op target answers a finding by re-running, even with identical output, so an op cannot loop on its own (H22) | SPEC application report |
| A squash-landed policy branch (policy files equal to the integration branch's) no longer blocks; §3.10, S8, §10 item 10 (H16) | `x:M4` |
| `wake_at` is the earliest `retry_after` or live-lease expiry; release gates carry no time (H17, correcting A3) | `x:M1` |
| One fetch for `start G base`, including the dependencies' PR branches; `start base` cost row (H18) | `x:M12` |
| `base` fingerprints only the dependency's `pr.head` (H19; DESIGN already said so) | `x:L1` |
| Re-review interdiff is `git range-diff`, omitted when `change` is identical (H20) | `x:L9` |
| Wording: "stack set of two or more members" (S5, `integrate`, D5, §10 item 25); `deps_conflict` ends when the stack set combines (§3.16); `pending` and `list` in §3.3 and §3.5; `deps_conflict` and engine-upgrade waits in §1, §3.6 and §10 item 8; `submit --as` and `start --force` in the grammar; no abandon option at the crash-loop cap; recurrence after `fixed:` or `disputed:`; "rewritten out of the integration branch" with reverts a stated limitation; stack PR CI setup note; bootstrap steps in SPEC order (H21). `x:L8` and `x:L11` are SPEC-only; for `x:L10` DESIGN already counts a closed goal's lease as an orphan; `m4:F10`'s nits are H1 and H15 | `x:M2`, `x:M3`, `x:L2`–`x:L7`, `x:L12`, `x:L14` |

### Revision 6

The decision record is REV6 (items A1–E5 below; [index](HISTORY.md#3-amendment-index)). Review sources, third pass: `cons` consistency, `model` model checking, `harn` harness and platform, `gen` generality and bootstrap, `econ` human economics, `evo` evolution.

| Change | Source |
|---|---|
| Stacked delivery: `base` stacks on dependencies that are merged or integrated, using a stack set (dependency PR heads, plus the integration tip when none remain or a merged dependency is missing from a head; a combine commit on `zzzops/stack/g<id>` for two or more; amendment 1); `deps_conflict` lasts until the stack set combines cleanly (amendment 3); `deps_conflict` named wait; only the goal's own commits replayed; restack on dependency change; reviews bind the goal's own diff; GitHub stacked PRs with explicit retargeting and a draft stack PR; required checks only on PRs into the integration branch; `merge` waits for dependencies and retargets dependents first; `approve_merge` parallel to `integrate`; D5 reversed; validation item 25; worked examples §4.2 and §4.4 (A1) | Human |
| `approve_merge` stays required; no skip offered or suggested; a repository may mark it optional itself (A2) | Human (`econ:H1` not adopted) |
| `wake_at` in `next`; unattended runs sleep until it with the harness's own scheduling; no loop script shipped (A3) | Human; `econ:C1` step 1, `harn:M2` |
| `design` runs as a worker; the add-goal skill dispatches it and keeps capturing; design questions as batched blocked items (A4) | Human; `econ:H4` |
| Cut: runtime self-test (fixtures become CI unit tests), verb-scoped diff check, clock-skew refusal (now a lease-tip warning), `edit.confirm_threshold` and `--yes`, orphan pruning in writes, work-in-progress push in `renew`, eight dependency miss reasons (now one reason plus state); kept: mass-expiry `--force`, `abandon` (A5) | Human; `cons` §4 |
| Carry-forward of checkpoint records across a clean `base` replay, exact patch-id match only, `carried_by: "base"`; why it is not `accept` (A6) | Decision record (human may override); `cons:M7`, `cons:M4`, `econ:M4` |
| Hand-resolved rebase conflicts accepted when the remote work tip has not moved; patch-id subset test deleted (B1) | `model:C1`, `cons:H2` |
| `change` recipe: `-O/dev/null`, raise on `git diff` failure, isolated Git configuration and attributes, submodule overrides, `info/attributes` warning (B2) | `gen:S1`, `harn:H2`, `gen:M1` |
| Engine-written dates as `@<seconds> +0000` (B3) | `gen:S2` |
| `responses` left out of a review's subject fingerprint; `target_fp` keeps the full output; §10 item 5 extended (B4) | `econ:H2`, `cons:H1`, `model:H1` |
| Test freeze from a `frozen` path list and the lease's `Work:` trailer (B5) | `model:H2` |
| Checkpoint defaults to the suggested checkpoint; subject-line fallback deleted (B6) | `cons:M4` |
| `abandon` pushes an expired renewal, never deletes; attempts always advance; abandons count toward the crash-loop cap (B7) | `model:M3`, `cons:H3` |
| `Nonce:` on claims; lost-response detection requires holder match; dispatcher-minted labels; uniqueness no longer a requirement (B8) | `harn:H1` |
| Unknown lease trailers ignored; unparsable leases excluded and reported, never deleted (B9) | `evo:M6` |
| A live lease renders `running` before input checks (B10) | `cons:L1` item 2 |
| Escalation: recurrence read from the target's `responses`, agent targets only, automatic responses never count; only a dispute the reviewer keeps open escalates; new findings start at 1 (B11) | `cons:M1`, `cons:M2`; covers `model:M1`, `model:M2` |
| Op-carried dispute items offer uphold, skip or cancel, never waive (B12) | `model:M2` |
| Repeat cap; `merge` waits get `pending_since` and the timeout (B13) | `model:M3` |
| `reopen G X` waives X's own open findings, so `reopen integrate` handles flaky CI; skill hint (B14) | `econ:H3` (`cons:M3` alternative not adopted) |
| Reopen of a stale node is not dropped (B15) | `model:M5` |
| Correction budget counts only corrections; `Reason:` on leases and records; `capability: routine` for base-only re-runs (B16) | `econ:M4`, `cons:M7` |
| Closed done dependencies never look open; `base.merges` optional; held dependency is a named wait; no-dead-end wording extended (B17) | `evo:H1`, `econ:M5`, `model:L5` |
| `base` gates on `review_design`; `skip` of a terminal node refused (B18) | `model:M4`, `model:L1` |
| `base`'s first run always rebases onto the current integration tip (B19) | `cons:L1` item 10 |
| `target_fp` also requires the target's record to predate the claim; human-carried findings never escalate (B20) | `model:L2`, `model:L4` |
| Every node reaches a terminal; an item closes an open goal whose terminals are all current (B21) | `evo:M3` |
| A merged PR with other code is a human item; reopening a goal closed done is refused (B22) | `evo:M1` |
| Op `details` ≤ 4 KB; output texts over 4 KB refused with `too_large` (B23) | `evo:M8` |
| Small fixes: busy worktree rendered as waiting; `--fp` qualified; embedded `next` and op finish reuse the snapshot; superseded salvage commands; release-gate wait wording (B24) | `cons:L1` items 1, 3–9; `model:L5` |
| Harness requirements; Codex configurations (a) and (b); `environment` refusal; Claude Code `permissions.allow`; sandbox domains (C1) | `harn:C1` |
| Verb-relative stored commands, prefix rendered at print time, `--file` instead of embedded quotes, `bin/zzzops` launcher (C2) | `harn:H3` |
| Op timeouts and process groups; POSIX shell and interpreter discovery; non-interactive Git; version floors and excluded distributions; primary-worktree sessions (C3) | `harn:M1`, `harn:M3`, `harn:M4`, `harn:M5`, `harn:M6` |
| Bootstrap as a skill checklist; `bootstrap.py` deleted; shipped templates; `not_bootstrapped`; offline `validate --policy`; skill set named (C4) | `gen:H1`; with `gen:H2` step 2, `evo:L1` |
| `push_refused`; the `zzzops/**` rule requirement (C5) | `gen:H2` steps 1–2 |
| `settings.merge.method`; GitHub `BLOCKED` handling; queue and auto-merge waits; `remove_if_safe` rule (C6) | `gen:H3` |
| `settings.integration_branch` checked on every verb; default from git config, else the remote's HEAD; PR retargeting (C7) | `evo:M5`, `gen:M2` |
| Shallow clones refused, partial clones warned; `--no-verify` only for goal, lease and stack pushes, hooks kept on work and PR pushes (git-lfs), documented; `branches-ignore` offered by bootstrap; empty `core.hooksPath` elsewhere (C8, amendment 2) | `gen:M3`, `gen:M5`, `harn:M4` |
| A landed policy branch does not block; blocker message adds paused actions and age (C9) | `gen:L3`, `econ:L1` |
| Stated limitations and setup notes: GitHub-only delivery, forks, monorepos, committer identity, `change` cost, PR titles and DCO, nested worktrees, template defaults, always-running required checks (C10) | `gen:M4`, `gen:L1`, `gen:L2`, `gen:L5`, `gen:L6`, `gen:L7`, `gen:L8`, `gen:L9`, `econ:L6` |
| Claude model ids beside GPT ids in `routing.tiers` (C11) | `cons:M6` |
| Policy impact preview in `validate --policy --dir` (D1) | `evo:H2` |
| Context edges out of the definition fingerprint; "if it still holds, resubmit it" hint (D2) | `evo:H3` |
| Engine ceiling (removed in G1027), tolerant floor read, unknown goal schema as a wait, the floor bump rule (capabilities since G1027), upgrade recipe (D3) | `evo:H4` (a)–(e), without the self-test |
| Fingerprints compared only in their own version; no multi-version support (D4) | Decision record (`evo:H5` not adopted) |
| Engines read every shipped goal schema and write the newest (D5) | `evo:M7` |
| Node rename recipe (D6) | `evo:M2` (recipe only) |
| `review_path` deleted; `.zzzops/reviews` is a constant (D7) | `evo:M4` |
| Opportunistic removal of closed goals' worktrees (D8) | `evo:M9` |
| `State:` trailer and open-only reads; corrected scaling rows; negative refspec; work branches deletable once no open goal depends on them; op time waits time out; offline leases and policy branches unknown; PR and issue close commands; small gaps (D9) | `evo:L1`–`evo:L5`; `cons` §4.3 |
| `Outcome:` line, since-T recipe, `last_change` (E1) | `econ:H5` |
| Decision facts: `implement.summary`, diffstat and diff command, `since`, `previous`, facts line; PR link for display only (E2) | `econ:M1`, `cons:M5` |
| Dependent discovery gates on the dependency's design review (E3) | `econ:M2` |
| Compact human items in unscoped `next`; `retry` actions carry instructions and a capability (E4) | `econ:M6`, `econ:M7` |
| `gh pr view` before `approve_merge`; mass-expiry warning names sleep; `show` text format (E5) | `econ:L2`, `econ:L3`, `econ:L4` |
| Not adopted: optional `approve_merge`, a shipped unattended loop and no-LLM op loop, skippable reviews or a `light` graph, usage recording, multi-version fingerprints, a name-free `node_def_fp`, reclaim as a child of the expired tip, deleting the reopen alternative, removing the small op state machines, the alternative repeat-cap form (REV6 §G) | Human; decision record |

### Revision 5

The decision record is REV5 (items A1–D9 below; [index](HISTORY.md#3-amendment-index)); the pinned detail is [SPEC.md](SPEC.md). Review sources: R3 prototype, R4 prior art, R5 implementability, R6 deletion, R7 blast radius, R8 Sonnet walkthrough, R9 Haiku walkthrough.

| Change | Source |
|---|---|
| Default graph of 12 nodes; `prepare` removed: the first artifact submit creates the work branch, and discovery reads `dev` without a worktree (A1) | Human; R6 F5 |
| `ci` folded into `integrate`, which reads the required checks; the lease-less run path is deleted (A1) | Human; R6 F6 |
| `review_tests` kept; no decomposition node; child goals created with `new` only after `approve_design` is ok (A1) | Human (R6 F7 not adopted); R7 M9 |
| POLICY.json kept separate with per-node instructions and advisory `routing.tiers` (A2, D13) | Human (R6 F8, F9 rejected) |
| One branch per goal `zzzops/goal/g<id>`; work, PR, lease and policy namespaces; id allocation by create-only push; multi-goal atomic edits; per-goal descendant check by a non-`+` refspec; fetch of four patterns with `cannot lock ref` retry (A3, D1, D10) | Human; R3 F13, F5; R1 M3 |
| Two code identities `tree` and `change`; selectors choose; default bindings; `approve_merge` binds `change`, not the PR head; S7 replaced; local `code_tree` objects recomputed from `commit` (A4, D14) | Human; R4 H2; R3 F10, F12 |
| Deterministic `integrate` rebuild (fixed committer, `--committer-date-is-author-date`) (A4) | R3 F11 |
| Lease handle `--attempt N`; lease records its own `Timeout`; a held goal's leases are not orphans (B1–B3) | R6 F2, R5 C3, R3; R4 M9; R7 H5 |
| Two-pass frontier; every ready node carries its live findings (B4, B5) | R5 C1, R3 F8; R3 F1 |
| `ok` replaces `require`, the release of dead-finding records and the decision special case (B6) | R6 F4, R5 C10, R3 F9 |
| Portfolio-aware stuck rule replacing the cancelled- and invalid-dependency rules (B7) | R6 F1, R3 F2, R5 C5 |
| `node_def_fp` allowlist; RFC 8785 canonical JSON; `v1:` prefix (B8) | R4 M3, R7 M2; R4 L1, L2 |
| Dependent designs gated on approved dependency designs (B9) | R4 M6 |
| Test freeze from `test_design`'s own commits (B10) | R3 F3 |
| `workspace` as a node-level flag; one workspace lease per goal, ops included (B11) | R6 F12 |
| Sync rule: local-ahead row, `--verbatim` patch equivalence, salvage commands in `sync_refused` and `REPAIR.md` (B12) | R5 C2; R4 M4; R8 #1 |
| `integrate` expects the PR head from its own fetch; diff-based review-file assertion (B13) | R3 F4; R7 M7 |
| `merge` deletes no branches; work branches kept (B14) | R7 H6, R6 F3, R4 M5 |
| Generic close when every terminal node is current and ok (B15) | R6 F11, R5 C6 |
| Ops parameterized by their inputs, never node names (B16) | R5 C6 |
| CI inside `integrate`: fixed finding ids per check, escalation on recurrence after `fixed:`, one re-run per head, 5→30-minute backoff, `ci_timeout_minutes` escalation (B17) | R7 H1, R4 M2, R7 L5 |
| Agents can submit a blocked outcome (B18) | R5 C7 |
| Human answers fenced by `--fp` (B19) | R4 H1 |
| `edit` requires `--base` or `--yes`; no silent whole-document re-apply; `confirm_threshold` (B20) | R5 C9, R7 M1 |
| Correction budget; dispute rounds per target node (B21) | R7 H2, R3 F7 |
| Crash-loop cap (B22) | R4 M1 |
| Engine floor `settings.engine.min`, `Engine:` trailer, unknown-schema refusal, self-test (B23) | R7 H3 |
| Verb-scoped diff check before every goal push (B24) | R7 H4 |
| Settings ranges validated (B25) | R7 M6 |
| Clock-skew refusal at `start`; mass-expiry `--force` (B26) | R7 M5, R3 F14 |
| Git ≥ 2.41 and `gh` checks; one real-GitHub fenced-submit smoke test (B27) | R4 L3 |
| Re-review cards carry the interdiff and previous findings; records keep the prompt blob (B28) | R4 M8, L5 |
| Task cards ≤ 4 KB, long inputs by blob (B29) | R8 |
| 11 verbs; `status`, `doctor`, `set`, `depend`, `close`, `hold`/`unhold`, `policy validate` and `run` folded in (C) | REV5 §C; cf. R6 F10 |
| Wait versus stop; scope with `--goal` and `also_pending`; "not yet" records nothing; approval summary in the agent's words; dispatch and label guidance (D1–D5) | R8 #2, #3, #4, #5, #8; R9 |
| Implement card lists the test commands; one renew number; `new` fields and defaults; actionable policy-branch blocker message (D6–D9) | R8 #6, #7, #9; R9 |
| `SPEC.md` created with the schemas, algorithms, CLI contract and default data files; DESIGN.md pseudocode moved there (E) | R5 §B, §C; R3 prototype; R8/R9 fixtures |
| Not adopted: any reviewer recommendation not listed in the REV5 decision record, including dropping `review_tests` (R6 F7) and moving or merging policy instructions (R6 F8, F9) | Human |

### Revision 3 (with the revision 4 human decisions)

| Change | Source |
|---|---|
| Discovery stage, `stage_first` scheduling, batched human gates, dependency designs as inputs, `base` gate for delivery | Human requirement; R0 #3; R2 B.3 |
| `goal new` returns discovery actions; the add-goal skill continues discovery in the same conversation | Human requirement |
| `code_tree` via mktree (the revision 2 recipe was wrong) | R1 H1 |
| Explicit push leases from the porcelain fetch snapshot | R1 H2 |
| Policy read by object id; best-effort coordinator mirror | R1 H3 |
| Review fingerprints the whole subject output; required `responses`; `target_fp` null for stale reviews; tightened liveness; a rule releasing non-approved records whose findings died (replaced in revision 5 by `ok` semantics); dispute escalation; previous findings as context | R1 H4a–d; R2 #1, #19–22, R9 |
| Design consumes the branch as context; delivery checkpoints consume `base`; `preserve` and `checks.run` tree-based | R1 H4e–f, M8; R2 #24, #30, #35 |
| One atomic push per submit (work branch + state + lease) | R1 H5; R2 #6 |
| Lease prefix `zzzops/lease/…`; a 3-ref fetch; work branches fetched per goal; branches deleted at merge (superseded in revision 5: `merge` deletes no branches) | R1 M1; R0 #7 |
| Policy-PR check only in `next`/`start`/`run`, paginated, concurrent (superseded in revision 4 by the branch prefix) | R1 M2; R2 #12–13 |
| State compare-and-swap with backoff and deadline; stated ceiling (superseded in revision 5 by per-goal branches) | R1 M3 |
| Separate PR branch; work branch never rewritten by `integrate` | R1 M4; R2 #16, #34; R0 #1 |
| Sync rule with automatic rebase over review commits | R1 M5; R0 #2 |
| Observe-only ops take no lease (superseded in revision 5: `ci` is folded into `integrate`); op leases short and self-renewed; one workspace lease per goal | R1 M6; R2 #8 |
| Deterministic consumed op outputs | R1 M7 |
| Op outcomes `done`/`blocked`/crash, with categories and `retry_after` | R2 R5; R0 #12, #18 |
| Human decisions use the review shape; `answer` for all human input | R2 R6 |
| `skip` replaces `when` and `approvals`; the fan-out field, `previous`, umbrella, `parent`, request ids, `value` dropped | R2 R7, R12; R0 #19–22 |
| Lease verbs named the lease commit (replaced in revision 5 by `--attempt N`), `abandon --force`, `reclaim --force`, dirty-worktree guard, orphan leases, renew pushes work in progress | R2 R8; R0 #14 |
| Auto-close, `held`, id counter without reuse, multi-goal `edit`, `edit` of invalid documents, `depend --remove`, cancelled-dependency item, `set` listed (revision 5 folds these verbs into `edit` and the item into the stuck rule) | R2 R10 |
| State-branch descendant check plus ruleset (the server `Date` lease time was dropped in revision 4; revision 5 makes the check per goal) | R2 R11 |
| Stuck-goal human item (no-dead-end invariant) | R2 R1 |
| `REPAIR.md` recipes | R2 R13 |
| Batched document reads; mktree artifact commits; absolute todo path; `--no-update-refs`; maintenance off | R1 L1–L5 |
| **Revision 4:** policy-change detection by the `zzzops/policy/*` branch prefix instead of a GitHub PR query (removes the GitHub API from normal work and resolves D11); lease times from the local clock with a skew warning; feedback dropped (D9); D3–D6 and D10 approved | Human |
| Not adopted: dropping the policy-change block (it was the human's decision); an `accept` re-stamp verb (it trades verification for supervision, so it is left out of v1) | R2 R4, R14 |
