# G1036 review_design, attempt 2: re-review of design revision 2

**Verdict: approved.** Revision 2 fixes both of my attempt-1 findings and takes all three notes. I have no new findings.

I read the diff from rev 1 (`96ea4d2`) to rev 2 (`ac8bbd5`), and checked every new citation against `docs/design/` on `zzzops/work/g1017`.

## Prior findings

- **review_design:1:1: resolved.**
  - The decision ids now match DESIGN §9: D1, with D2 for the spec text; D7 for leases; D11 for the policy branch; D12 with §4.1 as G1022 amends it; D14 with §3.4 and §3.5. D5 and D13 were already correct.
  - The new SPEC citations all exist with the right subjects:
    - §4.4, the per-goal compare-and-swap write;
    - §4.7, `code_tree` and `change`;
    - §4.8, fingerprints;
    - §4.12, leases;
    - §4.21, carry-forward;
    - §3.1, where `release_gate` is a workflow field, which the §4.9 frontier evaluates.
  - The DESIGN sections cited (§3.3 workflow definition, §3.7 leases) exist too.
  - Decisions are now always cited as `DESIGN §9 Dn` and removals as `DESIGN §5 Rn`, and the script checks the quoted phrase against that table row (W14).
  - R9 is reconciled with G1025: the propose/freeze ceremony was removed, and release lines come back without it.
- **review_design:1:2: resolved.**
  - The binding diff now covers all of `plugins/zzzops`, so skills, references, prompts and templates are inside it. It excludes only the three version-bearing manifests, all of which exist at those paths.
  - Rendered provenance prefixes are stripped only if a rendered copy is ever committed on the tagged branch, and the ledger records which case applies.
  - The header labels its build id as the checked dev build's, and the tag statement is limited to the source. W3 matches.

## Notes taken

- **T1** now says G2's design waits for G1's design (`deps.design.doc`): discovery runs ahead of delivery, not ahead of a dependency's design.
- **The ratio rule** now catches suffixed and comma-separated numbers near "token", currency, and cost words. Its exceptions are an exact-string allow list for the contract byte limits and for sample sizes.
- **The cited-test fallback** now applies to any trace step, with fixed step ids so the ledger is unaffected.

The owner decisions WD1-WD8, the dependency on G1037's report, and the privacy handling are unchanged from revision 1, and remain sound.
