# G1036 design review, attempt 7

Approved. The refreshed design meets the clarified whitepaper goal without restoring the obsolete dogfood report gate or requiring empirical cost/reliability proof. No material findings or optional findings were raised. There are no prior findings requiring status updates.

## Reviewed subject and evidence

Reviewed design blob `9c056c03d9f2e0238eadcef88eef497970e66e6a`, its change from `2a239e92a02beb5c9dc03824485c183501bfc80a`, specification blob `964280acf2f19348a0592bfa018cabd1796b52cc`, and project intent blob `ffa5169f852244b448ef8b49cc7ea791c12617d9`. Claims were checked against immutable integration source `c455b09914b49fd65e169f91a4f79110e3e2540b`, rather than the local checkout. No other review artifacts were read.

## Lens passes

### Intent

The organizing loop is state → frontier → next → card → result/review → recomputed context. The design preserves the practitioner-first audience, precise technical back half, owner-published blog draft, byline/disclosure, brief related work and working-document upkeep. All required behavior families appear in the coverage and ledger plans. The owner clarification explicitly removes the merged-report prerequisite, private run evidence and evaluation. Reliability/savings remain labelled aims. Settled owner decisions are recorded, and the design introduces no new product or external-publication choice.

### Simplicity

The four changed paths serve the requested paper, blog, navigation and manual evidence check. The checker validates structured binding/ledger references, computes builds from pinned archives, reports drift and exercises two bounded existing-fixture reproductions. This is proportionate to preventing stale or overstated documentation claims. It adds no CI wiring, installation machinery, simulator, benchmark framework or scheduled upkeep. Semantic truth and readability remain review work; the design does not require brittle prose-string assertions. No simpler alternative is needed to satisfy the audit and upkeep requirements.

### Truth

The design correctly limits determinism to complete frontier arguments, including time, and rejects a Git-refs-only or byte-identical-card guarantee. The pinned `frontier.py` supports the stated live-lease precedence. `fingerprint.py` confirms semantic definition allowlisting, artifact/checkpoint normalization, context-edge omissions and exclusion of prompt/provenance from normal identity. `card.py` confirms selective inputs, deeper read pointers and exact lifecycle commands. `render_next` trims actions/human items without universally bounding waiting/running output. The two documented size discrepancies are therefore appropriate audit content, not reasons to block a documentation goal. The exact final ledger claims and example steps remain to be checked during implementation review, as the design requires.

### Adversary

The design identifies selective disclosure as an initial-context mechanism, rather than access control. It distinguishes holder-label independence from authenticated actors, Git provenance from tamper-proof evidence, and fingerprint agreement from correctness. Shared credentials, missing declared edges, direct Git administration and external side effects remain explicit limits. Privacy and publication boundaries match the specification. No new authority or irreversible external action is proposed.

### Concurrency

Snapshot/CAS writes, contention, ambiguous response recovery, clock-sensitive leases, reclaim, superseded submissions, busy worktrees and interrupted execution have explicit coverage. The paired recovery/sync example must expose rejected old attempts, qualifying carry and rerun tree checks rather than imply process termination or filesystem isolation. This supplies the relevant failure boundaries without changing runtime concurrency behavior.

### Rollout

The primary binding is the refreshed dev core snapshot and its computed package build. The separate optional extension binding preserves its unmerged status; the diff from c455 to `4ff4e3f188f613adbd22a0726c1bbde69eed9d1b` contains the release-summary extension and supporting tests/docs. Documentation changes do not require copying that extension into the docs worktree. Runtime, schemas, repository policy and existing release/approval gates remain outside the change. Historical pins, discrepancy records and the upkeep procedure provide a proportionate correction path.

### Experience

The accessible front half, progressively precise back half, annotated card, checked synthetic walkthrough and paired failure/recovery example support both target audiences. Small diagrams with adjacent prose, linked contents and narrow tables address print use. The authority table, exact source/test ledger and known limits help the owner inspect behavior and find flaws without duplicating the normative schema/algorithm reference. Flexible word counts and diagram choices are implementation guidance, not blocking acceptance mechanisms.

## Local verification

An immutable c455 archive reported `0.0.0-dev d0738ea601d8`, matching the design. Sixteen focused tests passed locally: `test_engine_frontier.FingerprintTests`, `test_engine_card_budget.ShrinkBudgetTests`, `test_engine_portfolio.RenderTests.test_truncation_keeps_under_8k`, `test_engine_review_lenses.ShippedTemplateTests.test_the_15_node_graph`, and the two `test_engine_lifecycle.LeaseTests` checks for holder independence/held goals and fencing after reclaim. Exact commands/results are in `verification.json` beside this artifact. These tests check the selected source facts; they do not prove universal size limits, empirical benefits or final prose quality.

The paper, blog and checker have not yet been implemented in this design phase. Final claim wording, exact test citations, both production-function size reproductions, local links/anchors and rendered readability remain the planned implementation verification, rather than outcomes claimed by this review.
