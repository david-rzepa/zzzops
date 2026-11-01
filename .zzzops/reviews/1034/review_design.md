# review_design G1034 (attempt 1): approved

## Claims checked against dev 8d8437a
- `new` accepts `release`, defaulting to `settings.releases.current` (cli.py ~l.353). `schemas.validate_goal` rule 4 refuses a dependency on a later release and a dependency cycle, run before the goal is written. `request_key_of` / `scan_request_key` make a rerun of an identical file safe, and a changed release on rerun is refused: the design's "use `edit --set release=`" advice is right; `edit --set` exists.
- Skill step 3 reads `title,body,state,labels` with no milestone; step 4 has five classes and no release; step 5 passes only `links`. MIGRATING.md line 43 is the only `#695` in plugins/docs; the existing test pins `--json title,body,state,labels` (test_engine_legacy.py:570).
- G1004, G1008, G1013 are release 2, as stated. G1034 depends on G1017, so docs/design will exist in its base (it does not at 8d8437a, which is why the edit waits for the base).
- Rejecting a batch verb, dry run, required `release` and a helper script is reasoned; the undo stays inside this goal. No owner question.
- The design names only "the private app".

## Non-blocking
- A MERGE group needs one stated release rule (for example the earliest of its members' proposed releases, with the union of their dependencies), so the whole-set order check treats groups as single nodes.
- "the the private app" in Out of scope.
- Keep the skill test to a few load-bearing phrases (milestone field, "later release", dependencies first, explicit `release`); the CLI backstop test carries the behaviour.
