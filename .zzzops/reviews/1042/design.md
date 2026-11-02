# G1042 design: align the front page with Release 1

## Outcome and scope

The README describes what the Release 1 engine and shipped default workflow actually do. It remains a short, practitioner-first entry point: install, bootstrap, capture work, execute, then links to detail. Its core statement is durable goals on Git branches, a project-owned workflow, independent reviews and explicit human authority. Existing branding, the tagline, license, support address and compliance disclosures stay intact. This goal corrects claims, not the product's positioning or workflow.

This is documentation work plus a proposed, separately approved GitHub repository-metadata correction. It changes no engine contract, schema, prompt, policy or capability. No SPEC/DESIGN contract amendment or artificial HISTORY contract row is needed. Each changed or removed claim will be traceable in the PR body to the implementation-tip evidence.

## Evidence at design time

Read-only baseline: `de5640d1c5909ea924450aeea6450497a78946f6`, from the task card. The README already says `zzzops/goal/*` and the canonical plugin manifest already says “Agentic engineering with durable goals for autonomous coding agents.” The owner-reported GitHub Issues claim survives in the published default-branch README and the live GitHub description, not in dev's current README. The live description still says “manage durable goals in GitHub Issues”; topics still include `github-issues` and `project-management`.

The approved intent supplied by the root states that coding agents should carry long-running repository work through durable, reviewable goals without losing progress, priorities or control; the graph, prompts and policy belong to the project. It distinguishes branching support from deployment and release publishing. That intent is approved even though this repository's policy rollout has not yet installed `settings.intent`; do not claim the rollout already happened.

The dependencies' reviewed designs define the future wording for G1038 merge sync and tests-plus-code PRs, G1039 review carry and stage round budgets, and G1040 findings on blocked retry cards. They must not be advertised as shipped until their code reaches the implementation base. G1025 is already on the baseline: release/hotfix lines are optional under `settings.branching`, require `release_lines`, and use a separate line-goal graph. SPEC §5.8 and `engine/ops/lines.py` finish the approved line tip into the configured production branch and back-merge; they do not publish a release.

## Approach

### 1. Audit before editing

At implementation time, record the exact integration/base commit used and reread the whole README, each linked doc whose statement supports a README claim, the dependency changes, the canonical manifests, shipped templates/skills and current release workflow. Build a compact claim ledger in the PR body with columns: old claim or removed passage; replacement; evidence (code/doc path and relevant section); validation. Include claims confirmed unchanged when they explain the owner's reported drift, especially Git storage and publication to main. Do not put private dogfood details in this public ledger.

### 2. Update the README with bounded detail

Preserve its existing section order and working installation commands unless source evidence proves a correction necessary. Keep its opening short. Proposed opening, subject to ordinary editing and owner wording review at approve_merge:

> ZzzOps is an agentic-engineering workflow for developers who want autonomous coding agents to bootstrap repositories and carry long-running work through durable, reviewable goals. Each goal lives on its own Git branch. A workflow owned by your project coordinates agents, independent reviews, checks and human decisions, so work can stop and resume without rebuilding the plan from chat history.

Preserve the exact tested opening phrases `agentic-engineering`, `autonomous coding agents` and `bootstrap repositories`; this draft includes them. Replace “agents always know exactly what to do next” with the concrete stop/resume outcome rather than an absolute guarantee. One following sentence can say that ZzzOps ships an opinionated default graph that projects can customise; do not reproduce the entire intent document or add marketing claims.

The audit has these required decisions:

| Area | Wording and evidence |
| --- | --- |
| Goal storage | State Git branches, with `zzzops/goal/*`; GitHub supplies repository hosting and PR/check operations. Retain visibility and sensitive-data guidance. Evidence: SPEC §2.3, §3 and `docs/EXECUTION.md`. |
| Capture and owner interviews | Replace the unconditional “design starts at once” promise with “a worker starts the design; questions that need your choice come back to you before it proceeds.” Evidence: capture skill, design prompt, SPEC owner-question rules and G1026. Do not imply a human interview precedes every design. |
| Project ownership | Describe the shipped default as customisable configuration, not an inherent engine opinion. Evidence: SPEC §7, templates and approved intent. |
| Reviews | Briefly mention independent reviews through several lenses and material findings being corrected. Keep the lens catalog and filter mechanics in Execution. Evidence: G1022 and default workflow/prompts. |
| Human authority | Design and merge approvals, owner questions and consequential release-line choices are human items; delegated approvals do not let an agent invent owner decisions. Keep checks and merge approval distinct. Evidence: SPEC §3.6/§4.14, execution skill and G1026. |
| Sync and PRs | Once G1038/G1039 are on the implementation base, remove outdated rebase/carry guarantees from supporting Execution prose. Explain merge sync, checks and implementation review after sync, and reviewed work carried only under the documented clean-sync conditions. Mention tests-plus-implementation PR commits and conventional subjects only briefly in Execution; the README need not explain Git mechanics. Preserve dependency-order merging and stacks where still true. |
| Correction loops | Execution's current “3 runs per agent node” statement becomes the per-stage material-finding-round rule only when `round_budget` is required; otherwise it remains the legacy rule. Explain that behavior follows the repository's policy, not merely the installed engine version. G1040's retry correction language likewise distinguishes its capability gate; no internal `last_output` tutorial is needed. |
| Compatibility | Explain in one sentence that repositories declare required engine capabilities and an older plugin may require upgrading. `engine.min` is deprecated but still supported; do not say it was removed. Do not invent an engine semantic version separate from plugin release tags. Evidence: SPEC §4.5, CLI_USAGE Engine capabilities, G1027. |
| Release lines | A short optional paragraph or link describes release and hotfix branches when configured, with approval before finishing into production. Do not present them as bootstrap defaults or as tagging, deploying or publishing releases. Evidence: G1025 and SPEC §5.7–5.8. |
| Install/version claims | Recheck the directory link, immutable-tag guidance, pre-reset v2.x distinction, v3 first-release claim and `latest` mechanism against the release sources and `docs/CLAUDE_MARKETPLACE.md` / Maintaining. Preserve validated commands; qualify future release availability if it is not published yet. |
| Trust/support | Retain privacy/compliance links, support address, authentication/visibility statements, Python 3.10 requirement, affiliation disclaimer and no-server/telemetry/commerce wording. Existing tests pin these disclosures. |

### 3. Make only supporting linked-doc corrections

`docs/EXECUTION.md` is in scope for the sync, review carry, budget, owner-interview and optional-branching sentences that the README relies upon. `docs/SKILLS.md` may need the capture row qualified so it no longer promises an unconditional design start. `docs/INITIALIZATION.md` may need the branching-specific branch-deletion advice, but G1031 already owns that correction: preserve its landed text, and if it has not landed, identify the pending dependency/follow-up rather than implementing a competing choice. Keep all other changes narrow. Inspect the real resulting files; do not blindly copy these design-time observations over dependency fixes.

### 4. Explain how dev reaches the published front page

For this repository, main is the default branch and dev is integration. Reconfirm that the release path brings the updated README to main: when branching is enabled, the cut snapshots dev and line finish merges the approved release tip into the configured production branch (SPEC §5.8); the README is part of that tree. If branching remains disabled here, `release finish` is not available and the intentional owner release into main remains a separate release action. Record the actual configuration and planned route in the PR body. Do not patch main directly, change the default branch or enable branching in this docs goal. Until that release lands, main may legitimately display the old front page; do not call it already fixed in the published product.

### 5. Propose GitHub metadata, then apply the approved values at merge

Proposed description:

> Agentic engineering for autonomous coding agents: bootstrap repositories and carry durable Git-native goals through reviewed work.

Proposed topic delta: remove `github-issues` and `project-management`; add `git-native` and `goal-management`; retain all other topics. These names already match the canonical plugin keyword vocabulary. No repository rename, visibility, homepage or default-branch change is proposed.

The PR body must display the exact description and topic delta. At approve_merge, the root explicitly includes this external change with the wording for the owner to review. A merge approval that does not cover metadata is insufficient: leave metadata pending and request that specific approval rather than infer it. After the approved PR merges, the root rereads the current description/topics, preserves unrelated concurrent edits, and runs the exact approved `gh repo edit --description ... --remove-topic ... --add-topic ...` correction, then reads it back. If a field has changed materially since review, reconcile with the owner rather than overwrite it. A metadata failure does not undo the code merge; report it as pending and retry the approved correction. Do not run the external write during design or implementation.

## Validation and acceptance evidence

This goal needs no new test framework or brittle prose-needle tests. Reuse the repository's existing checks: `python3 -m unittest discover -s .agents -p 'test_design_docs.py'` (including `test_relative_links_resolve`), `test_agent_plugin.py` (published disclosures), and `test_marketplace_bundle.py` (truthful positioning). Test_design may record the minimal relevant existing tests rather than a new slow Git journey. Record measured execution times. Required CI still covers the full product suite.

For changed linked docs not covered by the existing root-README link check, resolve their relative Markdown targets with the existing helper or a small read-only inspection and record the result; do not add a general link-checking subsystem. Inspect external installation/doc URLs for continuity with maintained source guidance; do not claim local link checks validate internet availability.

Review acceptance: (1) every changed/removed README claim appears in the PR evidence ledger with implementation-tip support; (2) relative links and existing disclosure/positioning checks pass; (3) wording is presented to the owner at approve_merge; (4) the main-release route is recorded accurately without an unauthorized main update; (5) exact metadata proposal and its approval/application status are visible. The implementation summary and PR body identify any supporting-doc correction deferred to an existing goal.

## Risks, alternatives and non-goals

The main risk is describing reviewed plans as current behavior. Re-audit after dependencies land, name optional policy gates accurately, and avoid version-specific guarantees that will drift again. The second risk is conflating the Git README merge with live GitHub metadata or release publication; keep their status explicit.

Rejected: a wholesale README/branding rewrite (not needed to correct drift); copying the entire intent/lens catalog/CLI into the front page (adds maintenance burden); asserting all engine capabilities are active in every project (incorrect); direct edits to main or silent metadata writes (outside this goal's reviewed delivery); new prose-pinning tests (brittle and unnecessary).

No owner question is open at design time: the tagline and positioning are preserved, and the opening/metadata proposal follows the already approved intent. The owner still reviews the concrete final wording and external metadata at merge as the spec requires. If implementation discovers a necessary change to branding or project direction, it must block with concrete options rather than expand this design silently.
