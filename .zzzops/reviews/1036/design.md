# G1036 design: the ZzzOps whitepaper on deterministic progressive disclosure

Revision 2. It answers review_design:1:1 (decision ids corrected, ledger citations made explicit, R9 reconciled with G1025) and review_design:1:2 (the binding check covers all of `plugins/zzzops` except the version-bearing manifests; the header's build id is the checked dev build's). It also applies the review's three notes: trace step T1, a broader ratio rule, and the cited-test fallback for any trace step. §13 has the responses.

Revision 1 was written against read_dev 8d8437a, with `docs/design/` read from `zzzops/work/g1017`. It replaces G1002. The owner's ordering (OD2 of G1037) is that this design is done now and the paper is written only after G1037 merges, so that the dogfood run can still change the engine first. The writing nodes (`test_design` and `implement`) cannot start before then anyway: `depends_on: [1000, 1017, 1037]`, and G1037 depends on every Release 1 engine goal (G1022, G1024 to G1029 and the rest).

## 1. Owner decisions (2026-11-01 interview, relayed by the coordinator)

The quoted words are the owner's choices. The text after each one is the coordinator's statement of what the choice means.

- **WD1 Audience:** "Both, practitioner-first". A front half that practitioners can read (why, how it works, what it costs, when not to use it), and a technical back half (mechanism, evaluation) for tool builders.
- **WD2 Core claim:** "Progressive disclosure". Giving each agent only its node's prompt, inputs and policy, derived deterministically from Git, makes long-running agent work reliable and cheap. Everything else in the paper supports this claim.
- **WD3 Venue:** "Repo page + blog post". `docs/WHITEPAPER.md`, linked from README, is the reference. A shorter narrative blog post announces Release 1.
- **WD4 Blog location:** "External, you publish". The goal drafts the post as Markdown, and the owner posts it on their own site. The goal does not publish it.
- **WD5 Prior art:** "Brief related-work section". It names the approaches (issue-tracker agents, orchestration frameworks, single-session agents) and says what differs, with no benchmarks.
- **WD6 Term:** "Coin \"deterministic progressive disclosure\"". The paper keeps the spec's term, defines it as the frontier-and-card mechanism, and says how it differs from concept loading in `docs/CONCEPTS.md`.
- **WD7 Byline:** "Your name". The paper is authored by David Rzepa, with a note that agents drafted and reviewed it.
- **WD8 Evidence:** "Ratios and trends only". Results are relative (for example "about a quarter of the tokens"). There are no absolute token counts, costs or money. Sample sizes and caveats stay.

## 2. Outcome

Two new files and one changed line:

| Path | What |
|---|---|
| `docs/WHITEPAPER.md` | The paper. About 5,000–7,000 words: claim first, practitioner front half, technical back half, claim ledger appendix (§3). |
| `docs/blog/release-1.md` | The blog-post draft (WD3, WD4). About 900–1,200 words of narrative, the source text for the owner's external post. It makes no claim the paper does not make, and it links the paper. It is not published by the goal. |
| `.agents/whitepaper_check.py` | The check script (§5). It regenerates the synthetic trace from the engine in the tree and resolves every claim-ledger reference. It is not a `test_*` file, so CI does not run it (§5.3). |
| `README.md` | "What to read next" gains one line: "[Whitepaper](docs/WHITEPAPER.md): deterministic progressive disclosure, how ZzzOps keeps long-running agent work reliable and cheap." |

Nothing changes under `plugins/`. No contract changes, so no `docs/design/` edit and no HISTORY row are needed (G1017's rule).

## 3. Structure of the paper

The paper opens with its claim (WD2), and every later section is marked with the claim it supports. The header gives the title, "David Rzepa" with the note "Drafted and reviewed by coding agents working under ZzzOps; every claim is checked against the build named below" (WD7), the date, and the **engine binding** (§5.1).

**Front half: for practitioners (WD1).**

1. **The claim.** One paragraph stating WD2, followed by a three-sentence definition of deterministic progressive disclosure: a pure function of Git state (the frontier) decides each agent's next action, and a bounded task card discloses only that node's prompt, its selected policy instructions and its inputs. The same state gives the same card.
2. **The problem.** Long-running agent work fails in two opposite ways. One is to load everything: the pre-reset engine's frontier output was mostly waiting steps (78% of its bytes), and its input step averaged about twenty times today's card limit (DESIGN §2.6 F2). The other is to load nothing durable: a single session forgets plans, priorities and approvals when it ends. Both are stated as ratios (WD8).
3. **How it works, in one page.** Diagram D1 (the disclosure loop) plus the five things a practitioner sees: goals, `next`, task cards, reviews that reopen work, and batched human decisions, including owner-question interviews (G1026).
4. **What it costs** (ratios only, WD8):
   - The multi-lens review experiment (G1022 Appendix A). One reviewer with five lenses found as many or more known defects than five separate lens agents, for about a quarter of the tokens. Adding a separate Adversary at the design stage matched seven separate lenses for about a third of the tokens. Sample sizes: 3 implementation runs and 2 design runs, one subject each.
   - The dogfood run (G1037), as ratios derived from its report's totals (§7): for example the share of tokens spent on engine bookkeeping against the work itself, correction rounds per goal, the share of wall-clock time spent waiting on the owner, and how often a restack was free (carry-forward) against a re-run.
   - Every number names its sample (n goals, n runs) and its caveat.
5. **When not to use it.** One-session tasks. Repositories with no shared Git remote. Teams that need a project-management suite, enforced model routing, tamper-evident audit, or a CI/deploy orchestrator (these come from the intent's `not` list and R5/R1/R9).

**Back half: for tool builders (WD1).**

6. **Definition and distinctions** (WD6). A precise definition: frontier (SPEC §4.9), card construction (SPEC §4.20), the 4,096-byte card bound and the 8,192-byte `next` bound (SPEC §3.14, §3.15), and per-node `instructions` selection (DESIGN §9 D13). "Deterministic" means the same goal documents, policy and integration tip yield the same frontier and the same card content; leases and clock time enter only as named waits. Then the contrasts:
   - **Concept loading** (`docs/CONCEPTS.md`): an agent pulls linked definitions on demand. That is agent-driven and lazy. Deterministic progressive disclosure is engine-driven and computed before the agent starts, from state, not from the agent's choices.
   - **Retrieval** (RAG-style context selection): selection by similarity is probabilistic. Here selection is by declared graph edges.
7. **Mechanism, as Release 1 built it.** One subsection each, with the SPEC/DESIGN sections cited:
   1. Goal documents on per-goal branches, compare-and-swap writes; Git as the only store (DESIGN §9 D1; the spec text lives in the goal document, §9 D2; SPEC §4.4).
   2. Lease branches: an empty commit, renew, reclaim, atomic submit (DESIGN §9 D7, §3.7; SPEC §4.12). No heartbeats, receipts or storage locks.
   3. `workflow.json`: the declarative graph, with agent, op, review and human approve nodes (DESIGN §3.3); the Release 1 default graph is G1022's 15 nodes (DESIGN §9 D12 and §4.1 as amended by G1022's HISTORY §4 row), with lenses, a lens tag on findings, and skip keys `<node>:<lens>`; a project can replace any of it.
   4. Findings and corrections: a finding reopens its target; responses `fixed:`/`disputed:`; the filter; findings carried across rounds and edits (G1028); `owner question:` findings that block the design for the owner (G1026).
   5. Identities and staleness: tree and change, fingerprints (DESIGN §9 D14, §3.4, §3.5; SPEC §4.7, §4.8).
   6. Stacked PRs and carry-forward (DESIGN §9 D5, §3.16; SPEC §4.21). Not linear stacks: a dependent stacks only on its own dependencies.
   7. Policy: the policy branch that pauses new work (DESIGN §9 D11); declared engine capabilities and the build id (G1027); policy-update notices (G1024); the intent check at capture (G1029).
   8. Releases: the `release` field and the release gate on `merge` (DESIGN §2.5 W10; SPEC §3.1 `release_gate`, §4.9), and git-flow release and hotfix lines with `release_cut`, `sync`, `approve_finish` and `finish`, cited by the sections G1025's HISTORY §4 row names. The engine stays CI- and deploy-agnostic. The paper says plainly that R9 removed the old propose/freeze ceremony and that G1025 brings back release lines without it.

   Model-effort binding is not described, because the reset removed it: `routing.tiers` is advisory (R5).
8. **A synthetic end-to-end trace** (§4).
9. **Evaluation.** The G1022 experiment and the G1037 run in full, as ratios with sample sizes and the A.5 caveats. A short "what was not measured" list: no controlled comparison with another tool, one dogfood repository, and no measure of whether agents understood their cards.
10. **Related work** (WD5, at most about 400 words, no benchmarks):
    - Issue-tracker agents: state lives in a hosted tracker, and the agent receives the issue thread. Here state lives in Git, and the agent receives a computed card.
    - Orchestration frameworks: the graph lives in code and its state in a runtime. Here the graph is project data in the repository, and the engine is stateless between invocations.
    - Single-session agents: context is the conversation. Here the context is rebuilt from durable state for each phase.

    Each approach is named generically, with no product claims.
11. **Limitations** (§6).
12. **Appendix A: claim ledger** (§5.2). **Appendix B:** the trace transcript excerpts.

## 4. The synthetic trace

One goal pair in a scratch repository, generated by `.agents/whitepaper_check.py trace` from the engine in the tree. It reuses `engine_fixtures.World`, `FakeGitHub` and the Autopilot pattern of `test_engine_journeys.py`: real Git, the real CLI and fixed clocks. It is generic: goals "G1 add a `greet` command" and "G2 add `greet --loud`", where G2 depends on G1.

| Step | What happens | What the paper shows |
|---|---|---|
| T1 | `new` G1 and G2; `next` shows G1 `design` ready, while G2 `design` waits for G1's design (its `dep_designs` input reads `deps.design.doc`). Once G1's design is submitted, G2's design starts while G1 is still in delivery: discovery runs ahead of delivery, not ahead of a dependency's design. | a trimmed `next` excerpt at each point |
| T2 | `start` G1 `design`. | the full task card, trimmed only of hex: prompt blob, instructions, inputs, `read_dev`, commands, and the byte size against the 4,096 limit |
| T3 | `review_design` raises one material finding; `filter_design` keeps it; G1 `design` reopens. | the reopened card's `corrections` and `previous` |
| T4 | Design fixed (`fixed:` response); reviews approve; the human `approve_design` item is answered. | the approve item and the answer file |
| T5 | The delivery stage runs: `base`, `test_design`, `review_tests`, `implement`, `run_tests`, `review_impl`, `filter_impl`, `integrate`. | tree and change identities on the checkpoint view |
| T6 | G2 stacks on G1's PR branch; its PR shows only its own diff. | the G2 `integrate` record's target |
| T7 | A `zzzops/policy/*` branch is pushed; `next` pauses new starts with a named wait. Landing it resumes work. | the wait line |
| T8 | G1 merges; `base` restacks G2 onto the integration branch with unchanged patch ids, so carry-forward keeps `test_design` and `implement` and only the checks re-run. | the carried records and the `replay_map` |
| T9 | Release: G1 and G2 carry `release: 1`; the release line is cut, synced and finished (G1025), with `approve_finish` bound to the line tip. | the line goal's `next` lines |

Rules:
- Normalisation: each 40-hex id is replaced by `<c1>`, `<c2>` … in order of first appearance, times by `<t+Ns>`, and paths by `<repo>`. Holder labels use the synthetic form `claude:0a01/…`.
- The paper embeds excerpts (Appendix B), and the script writes the full normalised transcript to stdout. The excerpts in the paper must match the script's output byte for byte after normalisation.
- **Cited-test fallback, for any step.** If a step cannot be driven by the fixtures at the checked build, it is shown from the engine's own test for that behaviour, cited as a `test` ledger row, and the paper says so next to the step. That applies when FakeGitHub lacks a line op for T9, or when G1037's fixes renamed or changed an op, node or output a step depends on. Step ids T1–T9 stay fixed, so the ledger is unaffected. The implementer decides per step and records the reason in the ledger.

## 5. Claims and how each is checked

### 5.1 The engine binding

G1027 replaced the version number with a **build id** (`<plugin version> <package revision[:12]>`), and the revision hashes `plugin.json`. So a dev build (`0.0.0-dev …`) and the released build of the same source have different ids, and no reset engine has been released yet.

The header therefore names three things:
- the **checked commit** on the integration branch (or the release line, if this repository has cut `release/1` by then);
- the **build id of the checked dev build** at that commit (`zzzops --version`, of the form `0.0.0-dev <rev12>`). The header says it is a dev build id. A released bundle has a different id, because the build id hashes the whole package and release rendering rewrites the manifests and the skill metadata;
- the **Release 1 tag**, filled in once it exists, with the statement "the plugin source (engine, templates, prompts, skills and references) is unchanged between the checked commit and this tag, apart from version-bearing manifests". This statement is about the source; it does not equate the two build ids.

`whitepaper_check.py binding <tag>` proves the statement:

```
git diff --quiet <checked> <tag> -- plugins/zzzops \
  ':!plugins/zzzops/plugin.json' ':!plugins/zzzops/.codex-plugin/plugin.json' ':!plugins/zzzops/.claude-plugin/plugin.json'
```

The skills, references and prompts the paper describes are inside that path: the owner-question batching in the execute skill (G1026), the add-goal intent check (G1029) and the policy-update flow (G1024). The tag is compared on the source branch the release is cut from, which is what semantic-release tags. If a rendered copy of skill metadata is ever committed on the tagged branch, the script strips the `SKILL_PROVENANCE`/`DISPLAY_PROVENANCE` prefixes that `package.py` renders before comparing, and reports every other difference. The implementer confirms at the time of writing which of these two cases applies, and records it in the ledger.

### 5.2 The claim ledger

Appendix A is a table: `id | claim | kind | reference`. Every factual sentence about engine behaviour carries a ledger id (`[C7]`). There are four kinds:
- **spec:** a `SPEC §x` or `DESIGN §x` section that exists at the checked commit, with a quoted phrase the script finds in that section. Decisions are always cited as `DESIGN §9 Dn`, and removals as `DESIGN §5 Rn`, never as a bare `Dn` or `Rn`, so a decision id cannot be confused with a section or another table's row. The script looks the id up in that table's rows and finds the quoted phrase in the same row;
- **test:** an `.agents/test_*.py::Class::test_name` that exists and passes at the checked commit;
- **trace:** a trace step T1–T9 whose transcript shows the claim;
- **report:** a section anchor in G1037's report (§7).

Claims about why or how well (for example "reliable and cheap") are tagged **argued**, and each one must cite the ledger ids that support it. The limitations section says which of them rest on n=1.

`whitepaper_check.py claims` resolves every row and fails on the first unresolved one. It runs the cited tests with `run_product_validation.py`'s runner. It also fails if the paper contains an engine-behaviour sentence with no id. That is an author's check: the script lists the uncited sentences in §7 and §8, and the reviewer judges them.

### 5.3 Why no permanent CI guard

A CI test would make every later engine change that alters a card or `next` line also edit the whitepaper. That reaches into every future goal, for a document that is dated and pinned to a named build. A pinned statement stays true. The failure that matters is the paper describing an engine that never shipped, and §5.1's binding check covers that.

The script runs in three places:
- at `review_impl` (the reviewer re-runs it);
- before Release 1's `approve_finish` if any engine change landed after G1036 merged (a root step this design asks for; §9);
- whenever the paper is revised.

### 5.4 Ratio rule (WD8)

The script also scans the paper and the blog draft, and fails on any absolute count or cost:
- a number with a `k`, `K`, `M` or `B` suffix, or with a thousands separator, or of four or more digits, within five words of "token" in any form ("82k-token", "1.2M tokens", "tokens: 82,000");
- a currency symbol or code next to a number ($, €, £, USD, EUR);
- the words "cost", "spend" or "price" within five words of a number that is not a percentage, a ratio ("about a quarter", "3×", "1 in 4") or a count of runs, goals or rounds.

Allowed exceptions are listed by exact string in the script: the contract byte limits (4,096 and 8,192 bytes, 600 bytes) and sample sizes ("3 runs", "12 known defects"). Every other match is a failure, which the author fixes by rewording as a ratio. Each ratio cites the totals it is derived from (G1022 Appendix A, or the G1037 report section), so a reviewer can recompute it.

## 6. Limitations section (candid)

1. **Routing is advisory.** The engine does not check which model or session ran a phase. Independence is label inequality (R5).
2. **No comprehension proof.** Disclosure controls what an agent is shown, not what it understands or obeys. The engine checks shapes, identities and freshness, not reasoning.
3. **What R1–R15 gave up**, one line each from DESIGN §5's "Lost" column. Among them:
   - tamper evidence and per-mutation receipts (R1);
   - the CLI-held policy approval (R3);
   - automatic staleness from instruction-text edits (R4);
   - path whitelists (R6);
   - reviewed relationship edits (R7);
   - native atomic stack merges (R8);
   - the propose/freeze release ceremony (R9). G1025 restores release lines without it: cutting is an owner approval and finishing is another, with no release lock, coordinator or receipts;
   - automatic lease renewal (R10);
   - runtime self-checks (R14);
   - a recorded approval of bootstrap (R15).
4. **The evidence base is small.** One synthetic experiment per review subject, and one dogfood repository that is private and anonymised (only its public report is cited). There is no controlled comparison with other tools (WD5).
5. **Cost depends on discipline.** A project can make its own graph expensive: the graph and prompts belong to the project.
6. **Git and GitHub are assumed.** The engine needs network access to the remote and write access to the Git directory, and integrate and merge use GitHub.
7. **Anything G1037 reports as not observed** (its A11 failure paths), listed as untested in practice.

## 7. What G1036 needs from G1037's report

G1037 §7 already promises most of this. The paper needs it in this form:

- **A stable path and section anchors** in the repository, so ledger rows of kind `report` resolve.
- **Engine build ids per node**, and the build at the release. The paper's checked build must be one of these, or the paper says how they differ.
- **The totals that ratios are derived from**: per-goal agent runs, correction rounds and budget used, tokens split into bookkeeping (CLI and card reading) and the work itself, wall-clock time, CI minutes, and owner items and waits. The paper publishes only ratios (WD8), but the totals must be in the report so the ratios can be recomputed.
- **The lens re-score**: recall, nit rate and tokens per round, relative to G1022's synthetic numbers.
- **Per-phase outcomes**, the A1–A17 results, the defect goals, and which failure paths were observed (A11).
- **The anonymisation** that G1037 §6 already guarantees. The paper adds no detail about the app.

If the report lacks an item, the paper says "not measured", rather than estimating it. A missing item is a finding against G1037 only when it was promised in G1037 §7.

## 8. Diagrams

Each diagram is a Mermaid block with `accTitle` and `accDescr`, followed by a short paragraph headed "In words" that carries the same content for print, screen readers and raw-text readers. Labels are text, never colour alone. Five diagrams:

- **D1, the disclosure loop:** Git state → frontier → `next` → `start` → task card → agent → `submit` → Git.
- **D2, the branch layout:** integration branch, `zzzops/goal/g<id>`, `zzzops/lease/g<id>/<node>`, `zzzops/work/g<id>`, `zzzops/policy/*`, `release/<n>`.
- **D3, the Release 1 default graph:** 15 nodes, discovery and delivery stages, human nodes marked.
- **D4, identities and staleness:** tree and change, and which input changes stale which records.
- **D5, stacked delivery and carry-forward:** G2 on G1's PR, and the restack after G1 merges.

## 9. Approach details and rejected alternatives

| Choice | Decided | Rejected, and why |
|---|---|---|
| Path | `docs/WHITEPAPER.md`, following the uppercase `docs/` names (WD3) | `docs/whitepaper/README.md`: a folder for one file. GitHub Pages: a new publishing system, outside the intent's "not a release-publishing tool" spirit, and not asked for. |
| Blog draft | `docs/blog/release-1.md`, committed and reviewed in the PR (WD4) | A review artifact under `.zzzops/reviews/`: integrate drops review commits, so the draft would not reach the integration branch and the owner would have no stable copy. A claude.ai artifact: not reviewable in the PR. |
| Print | GitHub Markdown, printed from the browser, plus "In words" text for every diagram | A PDF build: a toolchain to maintain, for little gain. |
| Diagrams | Mermaid with accessibility fields | Hand-drawn SVG: hard to review in a diff, and it drifts. |
| Trace | Generated from the real CLI through the existing fixtures | A hand-written trace: it cannot be checked against a build. |
| CI guard | None (§5.3) | A `test_whitepaper.py` in `dev-required-tests`: it couples every future engine goal to the paper. |
| Numbers | Ratios with sample sizes (WD8) | Absolute counts: refused by the owner. |

Root follow-up, recorded for `approve_merge`: if any engine or template change merges after G1036 and before Release 1's `approve_finish`, the root runs `whitepaper_check.py binding` and `trace` before answering the finish. If the output differs, the root captures a fix goal against the release line.

## 10. Risks

- **The dogfood run changes the engine late.** That is why writing waits for G1037. A change after G1036 is covered by §9's follow-up.
- **The claim outruns the evidence** ("reliable and cheap" on n=1). Mitigations: claims tagged argued must cite ledger ids; every ratio carries its sample size; limitation 4.
- **Naming the private app.** The paper cites only G1037's public report. Before publication, the implementer and `review_impl` run G1037's A15 name check on both new files; the root supplies the terms privately, and they are never committed.
- **Byline and the privacy scrub.** G1017 scrubbed the owner's name from `docs/design/` only. The byline is the owner's explicit choice (WD7), and the plugin manifest already names the author. The G1017 gate covers `docs/design` only, so it does not apply.
- **The concept inventory.** `concept_inventory.py` scans `docs/**/*.md` and `test_concepts` forbids certain words (for example "reversible"). The implementer runs the suite on the new files.
- **The blog draft drifts from the paper.** The ratio rule (§5.4) applies to both files, and the reviewer checks that every claim in the draft appears in the paper.

## 11. Testing (for `test_design` and `review_impl`)

The acceptance checks are commands with recorded outputs. Apart from the check script (§2), no permanent test is added.

| Id | Check |
|---|---|
| W1 | `whitepaper_check.py trace` reproduces Appendix B's excerpts exactly at the checked commit. |
| W2 | `whitepaper_check.py claims` resolves every ledger row, and every cited test passes. |
| W3 | The header names the checked commit and labels its build id as the checked dev build's. `zzzops --version` at that commit prints that build id. Once the tag exists, `whitepaper_check.py binding <tag>` passes over all of `plugins/zzzops` except the three manifests. |
| W4 | The ratio rule passes on both files (§5.4), and each ratio names its source and sample size. |
| W5 | README links `docs/WHITEPAPER.md`, and the link resolves on GitHub. |
| W6 | Every diagram has `accTitle`, `accDescr` and an "In words" paragraph. |
| W7 | The front half covers why, how it works, what it costs and when not to use it. The back half covers definition, mechanism, trace, evaluation, related work and limitations. The order is claim first. |
| W8 | The definition distinguishes concept loading in `docs/CONCEPTS.md` (WD6). Related work names the three approaches with no benchmarks (WD5). |
| W14 | Every decision is cited as `DESIGN §9 Dn` and every removal as `DESIGN §5 Rn`, and each resolves to the row the claim describes. |
| W9 | The removed concepts appear only as removals: heartbeats, receipts, storage locks, linear stacks and model-effort binding. |
| W10 | The limitations cover advisory routing, no comprehension proof, R1–R15, and G1037's not-observed paths. |
| W11 | The A15 name check is empty on both files (terms supplied privately). |
| W12 | The full validation suite passes, including `test_concepts`. |
| W13 | The blog draft makes no claim that is absent from the paper, links the paper, and states that the owner publishes it. |

## 12. Out of scope

- Publishing the blog post (WD4).
- Any external venue other than the repository.
- A PDF build, or GitHub Pages.
- Engine, template or prompt changes. A defect found while writing becomes its own goal.
- Benchmarks against other tools.
- Absolute costs.
- Naming or describing the private app beyond G1037's report.
- A permanent CI guard.

## 13. Responses to corrections

- **review_design:1:1:** fixed. §3 item 7 now cites DESIGN §9 D1 (with D2 for the spec text) for goal documents, D7 for leases, D12 with §4.1 as amended by G1022 for the default graph, D14 with §3.4 and §3.5 for identities and fingerprints, D11 for the policy branch, and the release gate (§2.5 W10; SPEC §3.1, §4.9) plus G1025's HISTORY §4 sections for releases. The bare D6 is gone. Ledger rows always use the forms `DESIGN §9 Dn` and `DESIGN §5 Rn`, and the script checks the quoted phrase against that row (§5.2, W14). Limitation 3 now says that R9 removed the propose/freeze ceremony and that G1025 restores release lines without it, and §3 item 7.8 says the same.
- **review_design:1:2:** fixed. The binding check now diffs all of `plugins/zzzops`, so skills, references, prompts and templates are covered. Only `plugins/zzzops/plugin.json`, `.codex-plugin/plugin.json` and `.claude-plugin/plugin.json` are excluded, and rendered skill-metadata provenance prefixes are stripped where they occur (§5.1). The header labels its build id as the checked dev build's, and the tag statement is about the source only. W3 is reworded to match.
- **Notes:** T1 is corrected: G2's design waits for G1's design through `deps.design.doc`. The ratio rule is broadened to suffixed and separated numbers near "token", currency, and cost words, with an exact-string allow list (§5.4). The cited-test fallback now applies to any trace step, including steps affected by G1037's fixes (§4).
