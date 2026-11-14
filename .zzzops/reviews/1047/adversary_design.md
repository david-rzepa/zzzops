# G1047 adversarial design review

Approved with no material findings or notes.

The two removals are explicitly owner-authorized, while the design preserves current templates, installed-policy ownership and compatibility floors. Against `defaults.py` and SPEC §4.5 at `4bc7b4deba5f1a98595ab795cdb5c088c14b3c66`, its proposed schema-1 hashes remain opaque equality receipts rather than guessed version evidence. The genuine newer-schema guard stays separate and supplies no replacement receipt. Reviewed/declined receipts deliberately acknowledge the current shipped snapshot, including retained local customizations/deletions; reads do not write them. Explicit manual two-way handling replaces copy/delete/merge instructions, avoiding a silent data-loss path.

The large test migration is bounded by a retained-versus-retired behavior map, current and fully renamed real-Git journeys, explicit filter-edge renaming, and a required record of retained/replaced/deleted groups. It forbids hiding a historical full graph elsewhere or deleting unique generic behavior. All changed tests, helpers and fixture data belong to test_design before the freeze; implementation cannot silently repair frozen tests by weakening them. This is the correct phase boundary for reviewing coverage rather than accepting a smaller green suite unexamined.

Package inspection, focused real CLI/Git checks and unchanged full validation remain required. No new persisted keys, workflow/policy fields, record/finding keys or identity semantics are introduced by the defaults simplification, consistent with the stated capability decision. No release/main/paper-pin action is authorized.

Read-only design/source inspection; no repository edits or tests run. Future test review must substantiate the promised coverage map before implementation proceeds.
