# G1037 review_design (attempt 3)

**Verdict: approved.** I checked the design diff from c495b11 to 3d57400 (`previous.changed`). It changes only two things:
- the revision note;
- the `review_tests` row, which now says "OD1 to OD8".

The spec edit replaces the per-write deny-pattern sentence with OD8's convention, quoting the owner. The convention is to never name the app, keep public artifacts generic, use `[redacted]` in quotes, and check the name and slug once before publishing. The spec and design now agree, and both of my earlier notes are addressed. Nothing else moved. review_design:1:1 was already resolved.
