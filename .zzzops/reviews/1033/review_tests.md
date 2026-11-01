# G1033 review_tests, attempt 1

**Verdict: changes requested, for one finding: the second recorded command.** The tests themselves match design revision 2, would fail without the implementation, and are not brittle. But `run_tests` runs every recorded command, and the second one runs the repository's entire CI validation instead of what proves this goal.

Subject: the tests at `47a0333` (base `b452cd7`). The design is revision 2 (`606311b`).

## The tests against design revision 2

- **The assertions check only the package's own entry.** `package_check_entries()` keeps only entries that start with `plugin package` (which covers both failure forms of `cli.package_check`) or that contain `skill discovery metadata`. Git and gh entries are ignored. `run_full_validate()` runs `sys.executable <plugin>/zzzops/zzzops.py validate` (not the `sh` launcher) in an isolated home, in a one-commit repository pushed to a bare origin with `zzzops.integrationBranch main`.
- **Positive case** (`test_generated_claude_marketplace_passes_the_full_package_check`):
  - It builds with the canonical version (development) and with `2.0.0` (official).
  - It asserts each shipped `SKILL.md` description starts `ZzzOps v<version> — <channel> plugin.`, that there is no package-check entry, and that `policy` is exactly the `not_bootstrapped` message, which proves `validate` got past setup. That message matches `store.py:314-315`.
  - Before the fix, the canonical-version leg fails on both the channel prefix and the package entry.
- **Negative case** (`…_fails_on_a_wrong_channel_build_with_a_claude_hint`):
  - It re-renders one `SKILL.md` on the wrong channel with the real `render_skill_metadata`.
  - It requires exactly one package entry naming that file, `Claude Code` and `claude plugin update zzzops@zzzops`, and no "Codex". That proves the assertion can fire and that the layout-4 hint reads the sibling `marketplace.json` name.
  - Before the fix, the hint says Codex, so this fails too.
- **Hint for each layout** (`test_agent_plugin`):
  - The layouts covered: the Claude cache under `CLAUDE_CONFIG_DIR` (with the `mk` segment in both commands); the Claude cache under the default home; the Codex cache under `CODEX_HOME`; the Codex cachebuster; the generated marketplace run in place (`generated-mk` from its `marketplace.json`); a source checkout with both catalogs (gives `None`); and an unrecognised layout (gives the neutral text, as the detail's suffix).
  - `HOME` and `USERPROFILE` are both replaced, so `Path.home()` is isolated on POSIX and Windows.
  - The canonical tree's status now carries `harness`.
- **One shared rule.** `channel_for_version` is tested, including that a `+codex.` cachebuster does not change the channel.
- **`test_plugin_cachebuster`:** a failing cachebustered copy names the Codex marketplace and `harness == "codex"`.
- **The pinned helper.** `test_claude_plugin_acceptance` pins `require_no_package_check`. It passes with gh-only entries and with an empty list. It raises on either package form and on the bare bug text, even when that is mixed with gh entries. It also raises on malformed reports (`None`, `[]`, a missing `environment`, a string `environment`).
- **Native coverage is kept in sync.** Both new marketplace ids are added to `NATIVE_COVERAGE` (`run_product_validation.py`) and to `REQUIRED_NATIVE_IDS` (`test_ci_selection.py`), so the selection test enforces that they stay listed.

## F1 (target: test_design): the second recorded command runs all of CI's Linux validation, not what proves this goal

`python .github/scripts/run_product_validation.py --platform linux`, with no shard arguments, takes the `linux_validation()` path:
1. `python -m unittest discover -s .agents -p 'test_*.py'`. This is the entire suite: about 600 test methods, more than 1,300 test ids with subtests and generated cases. It runs serially in one process, although CI spreads it over 8 shards and 2 workers.
2. `npm run test:plugin` and `npm run test:release`. These need Node and the `node_modules` from `npm ci`, which means network access on a fresh worktree. CI installs these only on shard 0.
3. `prompt_stats.py --check` and `compileall`.

That makes `run_tests` slow and dependent on the environment (Node, `npm ci`, network), and a failure anywhere in the repository fails this goal's `run_tests`. Command 1 already covers everything this goal changes:
- the six modules: bundle, agent plugin, cachebuster, acceptance, CI selection and release validation;
- `test_ci_selection`, which checks the new native ids against `NATIVE_COVERAGE`.

The full suite is `dev-required-tests`' job on the PR.

**Fix.** Drop the second command. If a cross-check of the selection wiring is wanted, add a fast, offline one, for example `python -c "import runpy; m=runpy.run_path('.github/scripts/run_product_validation.py'); m['select_native_tests'](m['discover_native_tests']())"`, which fails on a missing id. Keep command 1 as it is.

## Non-blocking notes

- **The acceptance wiring is untested.** Nothing checks that `claude_plugin_acceptance.main()` actually calls `require_no_package_check` for both the generated runtime and the installed runtime. CI's `validate-claude` leg would still pass if `main` forgot one call. The bundle test covers the regression itself, so this is defence in depth. A source-level assertion (two calls in `inspect.getsource(main)`) would close it cheaply.
- **The `NO_POLICY` assertion pins the exact `not_bootstrapped` text.** That is fine as a proof that setup passed, but a later reword of that message will need this constant updated.
