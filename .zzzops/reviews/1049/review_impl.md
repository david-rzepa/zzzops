# G1049 implementation re-review

The previously reported first-attempt scope and stale concurrent claim defects are fixed. The capability-enabled path now includes final candidates in ambiguity checks and reviewer context. Workspace claims refetch and repeat the full start validation while holding the gate, including live same-node and other-node workspace lease checks.

I independently ran the three real-Git regressions for initial mixed candidates and both concurrent-start cases; all passed. The run also emitted a `ResourceWarning` about a Git subprocess pipe, which does not affect these outcomes and is not a material finding for this change. The full recorded verification passed.
