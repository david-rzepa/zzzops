# G1000 review_design: independent review

**Verdict: changes requested, with two findings.** The design delivers the spec. The lens set, the filter, `skippable`, `settings.intent` and the re-review pointer each serve a stated requirement, and the experiment's conclusions hold on its own data. Two gaps would change the design:

- **F1:** the filter's freshness does not cover the findings it judges, so a note can avoid the filter without anyone seeing it.
- **F2:** rollout steps 2 and 3 have no owner and no trigger. G1000's merge would unblock its dependents while this repository still runs the old graph. Step 2 also conflicts with a pin the owner has set.

I checked the claims against `read_dev` 54d7e83.

## Claims checked against the code

- **Context inputs gate readiness.** `frontier.resolve` resolves every input, including context inputs. So `base` waits for `filter_design`, as §11 says. The draft's Concurrency finding cc2 was rightly judged false.
- **Fingerprints.** `node_def_fp` is an allowlist (`fingerprint.py:38`). Adding `skippable` changes no fingerprint. `review` is hashed, so `review.filter` only affects new nodes.
- **Policy validation.** Rule 6 already reports `settings has no key` for a declared policy key (`schemas.py:411`). A missing `settings.intent` therefore fails `validate --policy` as D4 claims.
- **Optional intent key.** `_check_shape` requires every key in a shape dict. Making `intent` optional, with extra keys allowed, needs a small new shape kind. §6 implies this; implement should know.
- **Budget.** The limit is `3 × agent nodes`, so 6 → 20 agents gives 18 → 60 (`frontier.py:452`). Skipped agent nodes still count toward the limit.
- **Old-engine safety.** `reviewed` is not shape-validated, and 1.0's `card.previous` skips entries without a `change`. A 1.0 clone can read 1.1 records from an old graph. It rejects the new finding keys (`FINDING_KEYS`), workflow fields and settings keys as unknown, so it fails closed. The engine.min raise in step 2 is a safe extra layer, not the only protection.
- **Independence.** `start` checks independence only through `graph.subject(X)` (`verbs.py:174`). A filter is not a review, so implement needs the filter's subject from the lenses' `review.filter`. §7 implies this.

## Findings

### F1 (design): filter freshness does not cover the lens findings it judges

§7 says a filtered lens's finding is live only if the filter's latest record is fresh, and the finding is `material` or has the verdict `keep`. The filter's fingerprint comes from its inputs: `spec`, `doc` and each lens's `summary` (`fp_parts` hashes input values only). A lens's findings are not part of the filter's fingerprint.

So a lens can re-run without the design changing and produce the same one-line summary with a new non-material finding. The filter then stays fresh. The new note has no verdict, so under the §7 rule it is neither live nor judged.

The design itself names the cases where a lens re-runs alone:

- the intent herd (a `settings.intent` change stales only `intent_*`);
- a lens prompt `rev` bump;
- the def-stale card, which says "If it still holds, resubmit it".

**Consequence.** A finding the reviewer labelled a note bypasses the independent filter without any record. The experiment shows these are exactly the harmful cases that matter: I32, GT3 and GT8 were all labelled notes and recovered only by the filter's `keep`. This breaks the spec's "never let the filter silently drop a material finding" and "errs toward keeping".

**Fix.** Choose one of these:

- Put the candidate set (ids and `material` of open lens findings) into the filter's `fp_parts`, so a changed candidate set makes the filter stale.
- Or make the liveness rule fail safe: an open non-material finding with no verdict from the filter's latest record is live, as if kept.

Add a test: a lens re-runs on a policy change with an unchanged summary and a new note, and the target is not left current without a filter verdict.

### F2 (design): rollout steps 2–3 have no owner and no trigger, and step 2 conflicts with an owner pin

§12 lists the steps but not who runs steps 2 and 3, or when. G1000 closes when its PR merges in step 1. That unblocks G1002 (the whitepaper) and G1003 (the dogfood run), which depend on G1000. This repository would still be on the 12-node graph. Nothing in the graph or the design makes steps 2–3 happen first.

The spec's "adopt it in this repository's .zzzops/" and "this repository's own intent is written … with the owner" could then lapse silently. G1003 would dogfood the old graph.

Step 2 also says "refresh the Codex and Claude Code plugins". The owner has said Codex must stay on the 15b59a5 plugin copies until they say otherwise, because another agent is using them. Raising `engine.min` to 1.1.0 makes that agent's 1.0 engine report `engine_too_old` part-way through its work.

**Fix.** In D8 and §12:

- State that the root opens `zzzops/policy/engine-1.1.0` right after G1000 merges. An open policy branch already blocks all workflow work, so dependents cannot start on the old graph.
- Make the Codex repoint an explicit owner go-ahead, listed on the `approve_merge` item.
- Then open `zzzops/policy/lenses`, where the owner approves the intent text.

This is a few lines; no mechanism is needed.

## Notes (non-blocking)

- **The experiment's conclusions follow from its data.** I recomputed from C.1–C.3:
  - claim-only rule: 29 blocking, loses I25 and I32;
  - blind filter: loses 9;
  - D2: 37 blocking, 11% not harmful, loses I25;
  - replay: claim-only loses GT3, GT6 and GT8; D2 loses GT6;
  - filter promotions: 8/8 correct;
  - prompt control: 41% vs 37%.

  One slip: the filter's demotions of material claims were wrong in **11** of 13 cases (in3, tr5, re2, co2, ne1, ad2, ad3, mi2, mi3, mi4, ux1), not 10. The conclusion is unchanged.
- **Coverage is extrapolated, not measured.** The "merged seven 31/32" figure is the union of 15 separately prompted lenses; the merged §4 prompts were never run. The seven base lenses as actually run (intent, simplicity, truth, adversary, concurrency, migration, experience) cover **28/32**, with harmful coverage still **23/24**. Only I12, I21a and I41 (adopt-only) depend on merging. D1 holds on measured data; reporting it that way would be more honest.
- **The filter node is worth its cost.** The spec requires the filter to be independent of the reviewer, which an engine rule alone cannot provide. The data shows it recovers three harmful issues that self-labelling loses, for about 1/8 of a round's cost. D2's "promote, never demote" rule keeps it from repeating R2's failure. The node is justified.
- **26 nodes is the simplest form on this engine.** One node per lens is the only way to get parallel, independent, separately skippable reviewers. The two subjects mirror each other, as the spec asks.
  - With skips, the floor is two lenses plus the filter per subject: about 10 agent runs per goal, against 6 today. Small projects are served, provided add-goal actually proposes skips.
  - The code-lens set is unmeasured, and §16 is honest that it is.
- **Budget, in rounds.** One design round now costs up to 9 correction runs (design + 7 lenses + filter) instead of 2. So 60 allows about 6–7 full rounds per subject where 18 allowed 9. §14's "grows from 18 to 60" reads more generous than it is; one sentence would fix that.
