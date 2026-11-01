# G1033 review_design, attempt 2: re-review of design revision 2

**Verdict: approved.** Revision 2 fixes review_design:1:1 and takes all three notes. I have no new findings.

I read the diff from rev 1 (`2adddad`) to rev 2 (`606311b`) and checked it against read_dev `8d8437a`.

## Prior finding

- **review_design:1:1: resolved.**
  - Every `environment == []` assertion is gone. In its place, the tests assert that no entry starts with `plugin package` and that no entry contains `skill discovery metadata`.
  - I checked `cli.package_check()` (`cli.py:242-249`). Its two failure forms are `plugin package check failed: …` and `plugin package: …`, so the prefix covers both. Git and gh entries are ignored, so the tests pass in CI without a token and on machines without gh.
  - The new negative case is a build with one `SKILL.md` rendered on the wrong channel. It proves the assertion can fire and that the hint names Claude Code.
  - Rejecting a fake `gh` on `PATH` is reasonable: these tests are about the package, not gh.

## Notes taken

- **Platform coverage** is now stated correctly. The test id goes into `NATIVE_COVERAGE` and runs through `sys.executable …/zzzops.py validate`, so Windows and macOS exercise the paths and line endings too.
- **Exact-dict assertions** on `package_status()` will be grepped for at implement.
- **The `<m>` hint segment** comes from the cache directory, which Claude names after the marketplace's `name`. A code comment says this. For an in-place run, `<m>` is read from the sibling `marketplace.json` `name`.

The approach, the cause and the hint design are unchanged from revision 1, which I verified then: the reproduction, the fix restoring `ok: true`, and the layouts the harness detection relies on.
