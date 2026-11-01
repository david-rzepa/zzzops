# G1015 review_design

**Verdict: changes requested (3 findings).** The approach is sound. It brings back R11's "version changed" detection without the gate. The free local signals reuse `cleanup_legacy`. Network checks happen only on a key change and are capped at one GraphQL call. The design picks the right disclosure shape (a top-level `legacy` key, not `blockers` or `needs_human`), handles the old-format policy as a blocker before `not_bootstrapped`, and drops the alternatives for good reasons. Three gaps would change the design: the cost-contract amendment leaves out §3.15, one transient gh failure turns off the GitHub signal for a whole engine version, and the migrate skill depends on material an agent new to ZzzOps does not have.

I checked these claims against `54d7e83` and `64d5196`, and all of them hold:
- `store.read_state` reaches `not_bootstrapped` before any policy validation.
- `schemas.validate_policy` already special-cases `schema_version: 1` and sends the reader to MIGRATING.md.
- `_check_shape` requires every key.
- The old `POLICY.json` has `schema_version: 1` and `approval/backend/bindings/charter`, and no `settings`.
- `cleanup_legacy.LEGACY_ROOTS` and `LEGACY_SKILLS`, and the two ignore-block markers, exist at both commits.
- The old labels are `zzzops`, `zzzops:schema:v1/v2` and `zzzops-feedback`, which also carries `zzzops`. The old body marker is `zzzops-goal`.
- The new engine's remote names are `zzzops/{goal,work,pr,stack,lease,policy}`. `refs/zzzops/goal/<R>/*` is only a local fetch destination, so treating every remote `refs/zzzops/*` as legacy is correct.
- `ls-remote` is in `gitrun.NETWORK`, so the trace counts it.
- `GhError` carries a `transient` flag.

## Findings

### F1 (design): the bounded-cost amendment leaves out §3.15, so "§10 item 2 still holds" is not true as written
§10 item 2 requires per-verb counts "within the §3.15 counts". §3.15 gives `next` as 1 fetch and 0 GitHub API calls. On a cache miss the design adds one `ls-remote` and one `gh api graphql` to `next`, and `validate` always pays both. Only item 10 is amended. `CostBudgetTests.test_per_verb_round_trips` asserts `(1, 0, ["fetch"])` for `next`, and `test_cost_of_next_and_ops` asserts exactly one trace line. Both run on a cold cache, because `new` and the embedded `next` only read the cache. So both tests fail, and the design leaves two ways to fix them. One of them, "filter on `pr` calls", would hollow out the strongest no-GitHub assertion in the suite.

What goes wrong if this is ignored: the written contract and the CI budget disagree, and the easy fix of filtering weakens the tests that guard §10 item 10 against any future stray gh call.

Fix:
- Amend §3.15 as well. The `next` row becomes "1 fetch (+1 ls-remote on a legacy-cache miss)" and "0 (1 on a legacy-cache miss)". Add a `validate` row.
- Settle on one fixture approach: seed a matching clean cache through `legacy`'s own key function. Keep the existing totals assertions unchanged. Do not filter, and do not add an environment switch that turns the check off.
- Add a cold-cache budget test that asserts exactly 2 git calls (fetch and ls-remote) and 1 gh call (`api graphql`, without `issue view/list` or `comments`).
- Say where the amendment is recorded. `DESIGN.md` is not in this repository at `54d7e83`.

### F2 (design): a transient gh failure turns off the GitHub signal for the whole engine version
Any gh failure is cached as `github: "unavailable"` under the key, and `next` does not retry until the key changes. With `issues: null` and no local signals, the item is inactive. That is exactly the state of a half-migrated repository: the policy has already been bootstrapped, or the old files cleaned, but the old goal issues are still open. This repository was in that state before the 2026-10-31 triage. In such a clone, one network error, timeout, 502 (the fake gh already simulates one) or rate limit on the first `next` hides every open legacy issue until the next engine version. Since `ENGINE_VERSION` rarely changes, that can mean indefinitely, and only a `validate` the user has no reason to run brings it back. This defeats the spec's goal that users should not need to know to look.

What goes wrong if this is ignored: the disclosure fails silently for exactly the users this feature is for.

Fix:
- Cache only permanent failures (gh not installed, not authenticated) for the key.
- For `GhError.transient`, store a `retry_after`, for example 24 hours or the next day. The cost stays bounded at about one call per day while failures last, and is zero once the call succeeds.
- Extend test 8 to cover the transient case and the permanent case.

### F3 (design): the migrate skill cannot be carried out by an agent that has never seen ZzzOps
1. **The triage classes depend on a document that is not shipped.** Step 4 ties OBSOLETE, DONE, MIGRATE, MERGE and HUMAN to "DESIGN §5 R1–R15", and OBSOLETE comments must "name the R item". `DESIGN.md` is not in the plugin or the repository. `MIGRATING.md` and the references contain no removal list. An agent in a user's repository cannot tell what was removed from what still matters, and that judgment is the core of the triage. Fix: ship a self-contained removal table in the skill's references. Each row gives the old feature or label family, the R id, and what replaces it or "removed, no replacement". Have EXAMPLE.md use those rows.
2. **The skill's inventory is not the set the detector counts.** Step 3 uses `gh issue list --label zzzops` and an unspecified "body-marker search". The engine counts `label:zzzops,zzzops:schema:v1,zzzops:schema:v2`, plus the body marker on issues without the `zzzops` label, minus issues that goal documents link. An issue that carries only a schema label, or a marker search worded differently, means the agent triages one set while the CLI counts another. After step 7 the item does not go away, and nothing says which issues remain. Fix: have `validate`'s `legacy` output include the counted issue numbers (the cache already keeps the first 100) or the exact search strings. Have the skill inventory exactly that set, using exact, copyable `gh` commands, for example `gh api graphql` with the same query, or `gh search issues --repo O/R --state open ...`.
3. **The carry-forward route points to a tag the user's repository lacks.** Step 5 says "to carry finished work forward, follow MIGRATING.md". That file's recipe runs `git worktree add ../zzzops-pre-reset zzzops-pre-reset`, and the tag exists only in the ZzzOps repository. Fix: in the skill, or in the MIGRATING.md edit the design already plans, say to clone `david-rzepa/zzzops` at that tag to decode old envelopes.

What goes wrong if this is ignored: the spec's main acceptance, users migrating without prior knowledge, is not met. Agents make up triage reasons, or loop on an item that never disappears.

## Points checked and accepted (no finding)
- **§10 item 10 amendment:** narrow and justified. It covers the `next` verb only on a key change, `validate` always, and never when ignored, embedded or offline. It reads no bodies or comments, so its cost does not depend on archive size. Test 11 covers that.
- **Tests that assert no gh calls:** once F1's seeded-cache approach is chosen, they stay meaningful. Tests 2, 6 and 7 assert zero calls in the steady state, when ignored, and when embedded or offline. Those are the right negative tests.
- **`engine.min` and `settings.legacy`:** correct for released engines. Every released 1.0.0 will have the key, and the `OPTIONAL_SETTINGS` path keeps the template and existing policies valid. One gap remains, and it does not change the design: pre-G1015 dev builds also report `1.0.0`, so `engine.min` cannot exclude them. Such a build sees `policy_invalid` (paused, writes refused) instead of `engine_too_old` (§10 item 21). CLI_USAGE should say "set `legacy.ignore` only once every clone runs an engine released at or after 1.0.0". Any later optional key must raise `ENGINE_VERSION`.
- **Determinism (§10 item 1):** the item renders from the cache, including `checked.at`, so two `next` runs on unchanged state stay byte-identical.
- **Remembered positives in other clones:** after a migration done in clone A, clone B still shows its cached item until B runs `validate` or its key changes. That is acceptable, because the item names `recheck` and the skill's first step is `validate`. An optional improvement: re-check an active cached result at most daily.
- **Linked-issue exclusion:** cancelled or closed goals' documents are not read, so an open old issue linked only from a closed goal counts again. That is advisory and dismissible, and is fine.
