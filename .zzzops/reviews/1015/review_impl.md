# G1015 review_impl: independent review of b5a1a7b

Verdict: **approved**. No material findings.

Inputs: design rev 2 (`.zzzops/reviews/1015/design.md`), frozen tests cb8e7ba, implementation diff 54d7e83..b5a1a7b, checks (passed: 426 tests, 49 legacy tests).

## Specific checks

1. **Edits to non-frozen test files.** `git diff cb8e7ba b5a1a7b -- .agents` touches only four files, with four lines in total. Each line adds `migrate-zzzops-repository` to a hard-coded skill set or SKILL_UI map: `claude_plugin_acceptance.EXPECTED_SKILLS`, `test_claude_plugin_acceptance.EXPECTED_SKILLS`, and `SKILL_UI` in test_agent_plugin and test_marketplace_bundle. The new SKILL_UI tuple matches the skill's `agents/openai.yaml`. No assertion was removed or relaxed. Every check that keys on these sets now also covers the fourth skill, so the tests got stricter. The frozen files (test_engine_legacy.py, engine_fake_gh.py, engine_fixtures.py) are unchanged since cb8e7ba. `build_marketplace_bundle.py` still requires an exact skill set, now four.
2. **Bounded cost.**
   - `cmd_next` passes `legacy="check"`. `Session.render_next` defaults to `"cache"`, so the `next` embedded in submit, new and the other writes never checks.
   - `_status` gates a check on `can_check`: mode check/force, `snap.current` (not offline) and no `session.policy_ref`.
   - The check runs only when `due`: the cache is missing, the key differs, `retry_after` has passed, or the mode is force.
   - `ignored()` returns before any signal read or check.
   - `validate` uses `"force"`, so it always re-checks.
   - Local signals read blobs through the persistent `cat-file --batch`. The only extra process is one local `git config remote.R.url`. It is not a network verb, so it is not traced, and the budget tests stay byte-for-byte unchanged.
3. **Retry semantics.**
   - A success with an inactive item sets `retry_after` to null.
   - A success with an active item retries after 24 h.
   - Transient errors, GraphQL errors and malformed responses give `retry` with 24 h.
   - Non-transient auth stderr, gh not on PATH, or `gh_ok=False` from validate's `gh_problems` give `unavailable` with 7 days.
   - An `ls-remote` failure caps the retry at 24 h.
   - On failure, the last good `issues`/`issue_count`/`linked` are kept only when the key is the same, as §2 specifies.
   - `status()` catches every exception, so the check never fails a verb.
4. **importlib load of cleanup_legacy.py.**
   - The path is `Path(__file__).resolve().parents[2]/scripts/cleanup_legacy.py`, which is the plugin root's `scripts/`. That file is already in `package.REQUIRED_FILES`, so the self-check guarantees it exists in an installed plugin.
   - The module is registered in `sys.modules` before `exec_module`, which the dataclasses in that module need, and it is reused on later calls.
   - The module has no import-time side effects beyond constants (`main` is guarded).
   - I confirmed the load works in a fresh interpreter from a `git archive` extract of `plugins/zzzops`, which is the installed layout. `LEGACY_ROOTS` and both markers were returned, and a second call was idempotent.
   - Non-blocking nit: if `exec_module` ever raised, a half-initialised module would stay in `sys.modules` for the process, and every later call would fall back to `()` roots. Popping it in the `except` would be tidier. A damaged install is already reported by the package self-check, so this has no practical consequence.
5. **Privacy of the skill and EXAMPLE.md.** Neither contains a local filesystem path, username or machine name. The only identifier is the public repository URL `https://github.com/david-rzepa/zzzops`, which the design prescribes for the pre-reset clone. It is already used in MIGRATING.md and is not private. EXAMPLE.md refers to the owner generically and cites only public issue and PR numbers.
6. **PRIVACY.md.** The new bullet says: "a search of the repository's open issues for pre-reset ZzzOps labels and markers (issue numbers only, no bodies or comments)". This is accurate. The GraphQL document selects only `issueCount` and `number`. The body-marker match happens server-side through `in:body`, so no body is transferred.
7. **Policy files.** `git diff 54d7e83 b5a1a7b --stat -- .zzzops` lists only `.zzzops/reviews/1015/*`. No policy, workflow or prompt file changed.

## Other observations (non-blocking)

- Old-format policy: `store.read_state` puts the `legacy_policy` blocker before `not_bootstrapped`. It sets pause and `write_block`, and exit 4 is mapped in errors.py. `validate` lists it under `policy`. A `--policy-ref` preview reads the new policy, so the blocker does not show there.
- `OPTIONAL_SETTINGS` keeps `_check_shape`'s strictness for both known and unknown keys. Unknown `legacy` subkeys are still refused, and the new `bool` shape refuses non-booleans.
- CLI_USAGE says checks happen "again daily … after a failure". For gh unavailable or auth failures the interval is 7 days. SETUP.md says "at most once a day", which is correct. It is a wording nicety only.
- When the remote is not on GitHub and only local signals fire, the message says "open goal issues not yet counted". That wording could be more precise, but it is advisory.
