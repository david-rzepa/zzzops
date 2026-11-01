# G1015 review_tests (attempt 2)

Reviewed: tests checkpoint cb8e7ba (base 54d7e83, change 1a122e6), interdiff from a19c52f: `.agents/engine_fake_gh.py` graphql handler, `engine_fixtures.isolated_env`, and the additions to `.agents/test_engine_legacy.py` (test 14, FakeGhGraphqlTests, IsolatedEnvTests).

Verdict: **approved**. F1 is resolved and there are no new material findings.

## F1: resolved

The handler now tokenizes the document and parses each alias's arguments and selection set. Before it executes or records anything, it rejects: a missing `type` argument, a direct field other than `__typename` under `nodes` (the union error), and a search with no selection set. One bad alias rejects the whole document. It returns only the fields that were selected. It refuses a non-ISSUE type and any field it does not model, comments included, with "not supported by the fake", so the fake does not quietly widen the contract.

**Error format: the writer is right, and my prior review was wrong.** I checked it read-only against live GitHub with gh 2.100.0 on 2026-10-31:
- `search` without `type`: exit 1. stdout has `{"errors":[{"path":["query","search"],...,"message":"Field 'search' is missing required arguments: type"}]}` and stderr has `gh: Field 'search' is missing required arguments: type`.
- `nodes{number}`: exit 1. The path is `["query","search","nodes","number"]` and the message is the union text, the same in both places.
- No selection set: exit 1. The "Field must have selections (...)" message matches the fake's constant character for character.
- A well-formed `issueCount`-only document returns only `issueCount`.

So the `GraphQL: ...` prefix I cited came from an older gh. The fake's stdout JSON (path and message), its `gh: <message>` stderr and exit 1 all match current gh. I accept it.

**Direct tests.** I ran FakeGhGraphqlTests and IsolatedEnvTests at cb8e7ba: 9 tests, all pass. They cover the well-formed two-alias document through both `-f` and `--input -`, the 150/2 counts with nodes capped at 100, `first:10` with `hasNextPage`, the three malformed forms, a bad second alias, `issueCount` left out when not selected, and comments refused. The rejection tests also check that no search was recorded.

## Notes from attempt 1: addressed

- **isolated_env** now drops GH_TOKEN, GITHUB_TOKEN, GH_ENTERPRISE_TOKEN, GITHUB_ENTERPRISE_TOKEN, GH_HOST and GH_CONFIG_DIR. IsolatedEnvTests sets all six and checks that neither `World.env` nor `cli_env()` carries any of them. The test restores the environment afterwards.
- **Test 14** now checks the received documents, whether they came on argv or stdin: there are exactly 2 and neither contains `comments`. It also checks the final cache, `("ok", [1, 2, 3], 3)`, and that it is the same for 0 and 2,000 comments. Because the fake refuses a comments selection, an implementation that reads comments would end with `github: retry`, so the test now has real discriminating power.

## Regression run

Full suite at cb8e7ba, in a temporary worktree that I removed afterwards: 426 tests. The only failures are the same 17 failures and 15 errors in `test_engine_legacy`, all of them the missing implementation as in attempt 1. Every other suite passes.

## Minor, not blocking

- When there are several errors, live gh prints each message on its own stderr line (`gh: m1\nm2`). The fake prints only the first. The design records only the first stderr line, and no test asserts multi-error stderr, so this has no effect.
- The `graphql_error` fault still uses the old `GraphQL: Something went wrong...` text. It is classified as "any other non-transient error → retry", so the prefix does not matter. A later cleanup could make it `gh: ...` for consistency.
