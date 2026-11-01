# G1017 review_impl (attempt 1)

**Verdict: changes requested, on two findings.** The move is faithful, and the amendments I sampled match the merged code. SPEC §7/§8 now state only the engine's rules and point to `templates/default`, as the owner directed. The tests were not weakened: the implement commits leave `.agents/` untouched after the tests commit, and run_tests passed the full suite.

The two findings:
1. One private name survived the scrub. The repository is public, so this blocks.
2. The pending-amendments table and one DESIGN summary line are out of date.

## What I checked (tree d178bc8, base 8d8437a)

- **Scrub.** I grepped `docs/`, `README.md` and the new test for local paths (`/home/`, `/tmp/`, `/Users/`), the external folder, the owner's personal name, the session or scratchpad labels and `claude-1000`. Nothing found, apart from F1.
- **Amendments sampled against the code.**
  - **G1000:**
    - SPEC §3.1 rule 14 matches the filter checks in `schemas.validate_workflow`: an agent non-review node with `verdicts: object`, not skippable, a shared subject, an input from every lens that is not context, and `optional` exactly for skippable lenses.
    - §4.9's liveness rule (a lens finding waits for a fresh filter) matches `frontier.filter_verdicts`.
    - §4.18's skip refusal matches `verbs.skip_refusal`.
  - **G1016:** SPEC §3.16's `abandon` row (`expired`, `restart` with `--reclaim`, `hint`) and §4.12 match `verbs.py` (the `restart_command` and hint text).
  - **G1021:** SPEC §5.4 "No checks at all" matches `ops/integrate.py`:
    - `NO_CHECKS_MINUTES = 15`;
    - `min(15, ci_timeout_minutes) * 60` on an empty rollup;
    - `reason: "no checks appeared"` with the merge state;
    - the two options;
    - the pending reason `required checks pending: <names> (mergeable: <m>/<state>)`;
    - the `merge-tree --write-tree` local check, and the 60-second waits for an unseen head and UNKNOWN mergeability.
- **SPEC covers only the engine contract.** SPEC no longer names any default lens node (`truth_design`, `intent_impl`, `lens_*`: 0 hits). The graph, its table and the lens rationale live in DESIGN §4.1 (26 nodes, G1000). §7 lists the schema, validation, semantics, op and policy-reference rules that any graph must satisfy, and §8 states what the engine requires of POLICY, prompts and templates. One leftover example in §7 ("`filter_design` joins the seven design lenses …") is harmless. It is listed in G1022's row, so G1022 will update it.
- **Pending rows.**
  - **G1022:** the row lists the full section set from G1022's §12 (SPEC §3.1, §3.3, §3.6, §4.8, §4.10, §4.18, §4.20, §5.4, §7, §8.2, §8.3; DESIGN §3.8, §4.1, §10). The marker (`workflow.json lacks "\"truth_design\""`) is false today and becomes true with G1022's template.
  - **G1024:** the row matches G1017's design, and its directory marker `policy_update` is absent today.
  - **G1025:** the row matches G1025's design §15 word for word, and `git.line_sync` is G1025's op name (its design §5.4).

## Findings

### F1 (target `implement`): a private repository name is published in IMPLEMENTATION_PLAN.md

`docs/design/IMPLEMENTATION_PLAN.md:597`, in the Step 9 record, names the owner's private scratch repository as `david-rzepa/<private name>`. The name came over from the source plan, where it appears once. `PRIVATE_PATTERNS` does not cover it, so `test_private_data_is_scrubbed` passes.

The repository is public, and the private repository's name must not appear in it.

**Fix:**
- Reword to "a private scratch repository".
- Add a pattern that refuses any `david-rzepa/<repo>` other than `david-rzepa/zzzops` (for example `david-rzepa/(?!zzzops\b)`). Do not list the private name in the test, because that would publish it too.

### F2 (target `implement`): the pending table's closing sentence is out of date, and DESIGN keeps "12 nodes"

- **The README's closing sentence.** It says "G1026, G1027 and G1028 also depend on G1017; they get a row here once their designs name the sections they change". All three designs are now approved and name their sections.
  - G1026's design chose "case 3 without a pending row".
  - G1027 (§4) and G1028 (§9) are contract changes with known sections, so under this goal's own rule they should have rows. Proposed markers, both unlanded today:
    - G1027: `plugins/zzzops/zzzops/engine/__init__.py lacks "ENGINE_VERSION"`
    - G1028: `plugins/zzzops/zzzops/engine contains "carried_findings"`
  - G1029 depends on G1017 but changes only skill and prompt wording, so it needs no row. The sentence should say so, or say nothing about it.

  **Fix:** add the G1027 and G1028 rows, and reword the sentence to state G1026's and G1029's status.
- **DESIGN line 64.** "Estimated scale … Default DAG: 12 nodes" was not amended for G1000. §4.1's heading says 26 nodes. **Fix:** amend the line to "26 nodes (G1000)", or mark it as revision 6.3's estimate.
