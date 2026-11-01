# G1015 review_tests (attempt 1)

Reviewed: tests checkpoint a19c52f (base 54d7e83, change c65da4ce): `.agents/test_engine_legacy.py` (new, 40 tests), `engine_fixtures.World.add_clone` / `seed_legacy_cache` / `drop_legacy_cache` / `legacy_cache`, and the `api graphql` handler in `.agents/engine_fake_gh.py`, against design revision 2 (blob fb5b419).

Verdict: **changes_requested**, one finding (F1). Everything else is sound.

## What I checked

**Coverage of design §7.** All 14 items have tests, often more than one: cache/key (1, 2, plus purity of `cache_key`), cold-cache budget for `next` and `validate` (3), both old-policy shapes with `next`/`start`/`new`/`validate` (4), the item clearing after migration (5), each local-signal family including LEGACY_ROOTS loaded from `cleanup_legacy.py` and the 10-entry cap (6), ignore plus the schema cases (7), embedded and offline runs (8), transient, GraphQL-error, auth and no-gh failures, with last counts kept (9), the daily re-check of an active item (10), the counted set with `queries` equal to what the fake received and `truncated` at 101 (11), linked-issue exclusion in `next` and `validate` (12), package (13), and bounded cost (14).

**Existing cost and journey tests keep their meaning.** The seed uses `legacy.cache_key(ENGINE_VERSION, REMOTE_URL, ())` and `legacy.write_cache`, the engine's own code. `REMOTE_URL` is the configured `remote.origin.url`; insteadOf rewrites it only when the remote is used. A fresh World clone has no local signals, so the key matches and `next` makes no check. There is no off switch, and the old assertions are untouched. The seed also cannot drift: `test_fixture_seeds_a_clean_cache_with_the_engine_key` checks that `next` on the seeded clone makes `(["fetch"], [])`, so a different runtime key would fail it. All trace-based suites (store, journeys, github) build clones through `add_clone`. Clones made outside World (environment, identity) do not assert traces.

**Fixture edits are minimal and do not collide with G1001.** G1015 adds one line to `add_clone` and three methods after it, in the hunk at about line 192. G1001 (c2a6bcc) changes `World.new` at about line 263. The two hunks are disjoint. The G1015 tests call `w.new(...)` in a way that works with either version. `seed_legacy_cache` skips on `ImportError`, so the fixture is safe before implementation.

**The tests fail for the right reason before implementation.** I ran them in a detached worktree at a19c52f under the scratchpad, then removed it.
- `test_engine_legacy.py`: 40 tests, 17 failures and 15 errors. Every one is the missing feature: `cannot import name 'legacy'`, no `legacy` key, no `ls-remote`/graphql in the trace (`1 != 0 : ['fetch']`), `not_bootstrapped` instead of `legacy_policy`, `unknown key 'legacy'`, and missing skill files or `SHIPPED_SKILLS` entry.
- 8 tests pass already. They are regression guards: invalid new-format policy is not legacy, unknown subkeys and non-bool values are refused, the template has no key, the retired name is not reused, writes make no check, offline writes no cache, and linked-only gives no item.
- Full suite: 417 tests. The only failures are those 32. The fake and fixture changes break nothing existing.

**Fake gh.** The search-term parser handles the two design strings correctly: comma-OR labels, `-label:`, and a quoted phrase with `in:body`. It records the received query strings, caps `nodes` at `first` (at most 100) while `issueCount` is the full count, and produces `truncated` at 101. The auth fault matches the design's stderr, with gh's exit 4. I also ran both design query strings against the real GitHub search on david-rzepa/zzzops (read-only). `label:zzzops,zzzops:schema:v1,zzzops:schema:v2` parses as an OR, so the strings themselves are fine.

## Findings

### F1 (target test_design): the fake's graphql handler accepts documents that real GitHub rejects

`graphql()` takes the aliases and `query:` arguments from the document and ignores the rest. For each alias it always returns `issueCount`, `nodes[{number}]` and `pageInfo`, whatever the document selects. I probed it with three documents that real GitHub refuses, and the fake answered each one with data and exit 0.

| Document | Real GitHub (checked live) |
|---|---|
| `search(query:$l, first:100)` with no `type:` | `Field 'search' is missing required arguments: type` |
| `nodes{number}` with no `... on Issue` | `Selections can't be made directly on unions (see selections on SearchResultItem)` |
| `issueCount` not selected | the field is absent, but the fake returns it anyway |

So an implementation whose document is malformed passes every test in this file. In production, every check then fails as a non-transient GraphQL error. By design that becomes `github: "retry"` every 24 hours, so the item never shows issue counts. The failure is silent, and green tests would hide it. The card asks for faithfulness, and this is the one place the fake stands in for GitHub's contract.

Requested change, small and local to `engine_fake_gh.graphql`. For each alias:
- require a `type: ISSUE` argument;
- require that the document selects `issueCount`, and `number` inside `... on Issue { … }`;
- otherwise `die` with the real messages above (`GraphQL: …`, exit 1);
- return only what was selected, or at least leave out `issueCount` when it is not selected.

Then add one direct probe of the fake to `test_engine_legacy.py`. The fake is reusable test infrastructure, so it needs direct verification. The probe should send:
- a well-formed two-alias document, expecting the counts and the `nodes` cap;
- the three malformed forms, each expecting a failure.

## Notes (not blocking)

- **Live gh in `validate` tests.** `validate` always checks. A World without `FakeGitHub` (for example `test_engine_policy_ref`, which calls `validate` twice) would use the real `gh` on PATH. HOME is isolated, so gh is unauthenticated and `gh_problems` skips the call. The exception is a runner with `GH_TOKEN` in the environment: there, the suite would make a live search for `repo:test/repo`. CI does not set `GH_TOKEN` for the product tests today. The implementer may want `isolated_env` to drop `GH_TOKEN`/`GITHUB_TOKEN`, or give `World` a `gh` stub by default.
- **Test 14's `comments` field.** The fake ignores it, so the 0-versus-2,000 comparison is carried by the "no `comments` in any argv" assertion, not by any real difference in work. That is acceptable under the current design.
