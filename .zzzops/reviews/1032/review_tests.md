# review_tests G1032 (attempt 1): approved

5 skill/doc tests fail today and 3 engine tests pass by design. Mutation (a swallowed api call to a rules path in ops/merge.py) makes the fake-gh guard fail, so it detects coupling. Non-blocking: some skill assertions are weak or already satisfied; graphql rulesets queries are not covered; the repo-read-403 sentence is untested.
