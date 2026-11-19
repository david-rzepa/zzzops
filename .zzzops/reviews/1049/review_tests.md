# G1049 test re-review, attempt 4

Approved. The new real Git/CLI regression publishes a blocked producer segment, replaces only that segment with unverified history while retaining accepted ancestry, then requires the runnable retry to fail without changing either goal or work refs. This covers the remaining finding. Previous test review findings remain resolved.

The writer measured 19 tests in 59.919 seconds on the old implementation, with the new test stopping at the absent capability. I independently ran the new focused test (1.048 seconds), confirming the same pre-implementation capability rejection. This is red setup evidence only: the implementation review must confirm the test actually reaches and passes the provenance refusal, alongside the other acceptance tests. The 60-second suite cost is justified by real Git/CLI histories and repair safety; there are no artificial sleeps.
