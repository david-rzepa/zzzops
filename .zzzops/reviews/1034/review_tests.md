# review_tests G1034 (attempt 1): approved

Skill-text test: fails today on every assertion individually, phrases are load-bearing. Backstop tests pass by design; mutation (rule 4 release-order check disabled) makes the refusal test error, and the before/after remote goal-ref comparison pins that a refused new writes no ref. Non-blocking: loose confirm regex alternative; mutant surfaces as KeyError instead of an assertion message.
