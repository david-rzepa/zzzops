# G1037 review_design (attempt 2)

**Verdict: approved.** Design attempt 3 (blob c495b11) applies OD8. The privacy rule is now a convention:
- the app is never named;
- public artifacts are generic;
- identifying words in owner quotes are replaced by `[redacted]`;
- A15 is a name and slug check of the report and this goal's artifacts.

The diff from attempt 1 touches only the OD list, §3's review and `review_impl` rows, the precondition list, A15, §6, the risks and the new §11. The run plan itself is unchanged and was already sound (see attempt 1).

## Prior finding

- **review_design:1:1: resolved.** It is superseded by OD8. The history-wide scan, the per-write gate and the deny-list tuning it was about no longer exist. The remaining A15 is scoped to the report and this goal's artifacts, which avoids the false positives in dev's history that the finding described.

## Notes (non-blocking)

- **The goal spec is out of step with OD8.** Its last paragraph still says this goal's public artifacts "are scanned against the journal's deny-pattern list before every write". The root should edit it to match OD8. Otherwise `review_impl`'s check against the spec will flag the dropped gate.
- **`review_tests` row (§3).** It still says "OD1 to OD7". It should include OD8.
