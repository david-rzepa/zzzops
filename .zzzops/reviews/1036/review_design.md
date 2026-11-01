# G1036 review_design, attempt 1

**Verdict: changes requested, for two findings.** The design honours all eight owner decisions. Its claims are bound to checks (a claim ledger, a trace from the real CLI, a ratio rule), its dependency on the dogfood report is explicit, and it keeps the private app out of the paper. The two findings:
1. Several DESIGN decision ids it plans to cite point at the wrong decisions.
2. The engine-binding check covers too little of the plugin to back the paper's claims.

I checked the design against read_dev `8d8437a`, against `docs/design/` on `zzzops/work/g1017` (which already has G1000's amendments), and against the goal state branches.

## Owner decisions WD1-WD8

- **WD1, both audiences, practitioner-first:** the front half covers claim, problem, how it works, cost and when not to use it. The back half covers definition, mechanism, trace, evaluation, related work and limitations. W7 checks the order.
- **WD2, progressive disclosure as the core claim:** stated first, with every section marked by the claim it supports, and "argued" claims required to cite ledger ids.
- **WD3 and WD4, repo page plus an external blog the owner publishes:** `docs/WHITEPAPER.md`, linked from README, and `docs/blog/release-1.md` as a draft only. W13 checks that the draft adds no claim the paper lacks. Committing the draft rather than leaving it as a review artifact is well argued, since integrate drops review commits.
- **WD5, brief related work:** at most about 400 words, three generic approaches, no products, no benchmarks.
- **WD6, the coined term:** defined as the frontier-and-card mechanism, and contrasted with agent-pulled concept loading (`docs/CONCEPTS.md`) and with similarity retrieval.
- **WD7, byline:** "David Rzepa" with the agents note. This is the owner's explicit choice, and it correctly sits outside G1017's docs/design-only scrub.
- **WD8, ratios and trends only:** a ratio rule in the check script; each ratio names its source totals and sample size; contract byte limits are allowed.

## Checked and correct

- **Section citations.** These exist and say what the design claims:
  - DESIGN §2.6 F2: "78% of the bytes are dependency steps" and an input step "averaging about 89 KB", which is about 22 times the 4 KB card bound, so "about twenty times" is fair;
  - SPEC §3.14 (task card, at most 4,096 bytes) and §3.15 (`next`, at most 8,192 bytes);
  - SPEC §4.9 (frontier) and §4.20 (card construction);
  - D13 (policy disclosure);
  - D5 (stacked dependencies).
- **Removal list.** The R1-R15 "Lost" items in §6 match DESIGN §5 (R1, R3, R4, R5, R6, R7, R8, R9, R10, R14, R15).
- **Dependency on the dogfood run.** It is clear. G1036 has `depends_on` `[1000, 1017, 1037]`, and G1037 depends on every Release 1 engine goal. §7 lists exactly what the paper needs from G1037's report (anchors, build ids, the totals behind each ratio, the lens re-score, A1-A17, the not-observed paths). It also says "not measured" rather than estimating when an item is missing.
- **Privacy.** The design never names the private app. The paper cites only G1037's public report, and the A15 name check runs with privately supplied terms that are never committed (W11).
- **No CI guard.** §5.3's case is sound: a dated paper pinned to a named build should not couple every future engine goal to its prose.

## F1 (target: design): several DESIGN decision ids point at the wrong decisions, and R9 conflicts with G1025

The plan cites decision ids from DESIGN §9 ("Decisions requiring human approval"). In that table:
- D1 is where goal state lives (per-goal branches);
- D2 is where the spec text lives;
- D3 is the merge decision (`approve_merge`);
- D4 is design approval;
- D5 is stacked dependencies;
- D6 is the implementation strategy;
- D12 is the default graph;
- D14 is code identity.

The design's §3 item 7 cites:
- "goal documents on per-goal branches … Git as the only store (**D2**)". The decision is D1; D2 is only the spec location.
- "the Release 1 default graph is G1022's 15 nodes (**D3**)". The decision is D12, plus §4.1 as amended. D3 is approve_merge.
- "Identities and staleness … fingerprints (**D4**)". These are D14 and §3.4/§3.5. D4 is design approval.
- "Releases … (G1025, **D6**)". D6 is the implementation strategy. Releases are W10's gate (§2.5 and SPEC's `release_gate`), plus G1025's amendment once it lands.

The ledger script would catch some of these through its quoted phrases, but only after the paper is written around them. Separately, limitation 3 lists "the release ceremony (R9)" as lost, while §3 item 7.8 describes G1025's release lines with `approve_finish`. Both cannot stand as written.

**Fix.**
- Correct the ids: D1 (with D2 for the spec), D12 plus §4.1, D14 plus §3.4/§3.5, and the release gate plus G1025's HISTORY §4 row in place of D6.
- Have the ledger cite sections, or `§9 Dn` explicitly, so the kind of citation cannot be confused.
- Reword R9 as "the propose/freeze ceremony was removed; G1025 restores release lines without it", and check that against G1025's merged contract.

## F2 (target: design): the binding check covers only the engine and templates, so it does not back the paper's claims

§5.1 proves "the engine and template sources are unchanged" with `git diff --quiet <checked> <tag> -- plugins/zzzops/zzzops ':!**/plugin.json'`. But:
- **Skills and references are outside that path.** The paper describes behaviour that lives in `plugins/zzzops/skills/` and `references/`: batching owner questions in the execute skill (G1026), the add-goal intent check (G1029), and the policy-update flow (G1024). A change to them between the checked commit and the tag would pass the check.
- **The exclusion is a no-op.** `plugin.json` is at `plugins/zzzops/plugin.json`, outside the diffed path. The manifests that semantic-release actually changes (`plugins/zzzops/plugin.json` and `.codex-plugin/plugin.json`) are not in scope at all.
- **The paper's build id is a dev id.** G1027's build id hashes the whole `PLUGIN_ROOT`, and the release bundle re-renders the manifests and skill metadata. The header's build id can therefore only name the checked dev build, not the release build. The design says this, but W3 should not imply more.

**Fix.**
- Diff `plugins/zzzops` as a whole, excluding only the version-bearing manifests (`plugins/zzzops/plugin.json`, `.codex-plugin/plugin.json`, `.claude-plugin/plugin.json`), and normalise or exclude any provenance lines that release rendering rewrites.
- State in the header that the build id is the checked dev build's, and that the tag statement covers the source.

## Non-blocking notes

- **T1 "G2 `design` ready too (discovery runs ahead)".** In the template, the `design` node has the input `dep_designs: {from: deps.design.doc}`, so G2's design waits for G1's design. Discovery runs ahead of delivery, not of the dependency's design. The trace will show the truth; fix the table so the implementer does not chase it.
- **Ratio regex.** `\d+(\.\d+)?k? tokens` misses `82k-token`, `1.2M tokens` and `tokens: 82,000`. Broaden it, for example to any number with a k/M suffix or a thousands separator within a few words of "token", minus the allowed byte limits.
- **The 15-node graph and the T9 release ops** depend on G1022 and G1025 as merged. The design already lets the implementer fall back to cited tests for T9. Name the same fallback for any trace step whose op names changed in G1037's fixes.
