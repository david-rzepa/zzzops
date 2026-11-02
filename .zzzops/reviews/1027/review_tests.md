# Review of tests, G1027 (attempt 4)

Decision: approved.

Scope: delta from the previously approved 4c8c5c6 to 1a15ad2.

- `git diff 4c8c5c6 1a15ad2 -- .agents` contains one change: in `.agents/test_engine_schemas.py`, `CanonTests.test_errors_have_exit_codes` expects 27 exit-1 codes rather than 28.
- Design (revision 2, section 4) removes `engine_too_new` from `errors.py`, `cli.py`, `store.py` and the SPEC and DESIGN error and exit-code tables. It had no emitter, so exactly one exit-1 code disappears. 28 to 27 is the correct, minimal update.
- No other test file changed, so the earlier approval otherwise stands.
