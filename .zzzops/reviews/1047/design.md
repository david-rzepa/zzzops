# G1047: remove historical template and workflow baggage

Source: dev `4bc7b4deba5f1a98595ab795cdb5c088c14b3c66`. Remove the shipped archive and obsolete full-workflow fixtures coherently, preserving current templates, repository ownership and generic engine coverage.

## Owner decisions

Authorizations relayed by the coordinator on 2026-11-14:

- Template history: “Yeah I think we can get rid of that tbh, barely anybody uses zzzops anyway”. This authorizes retiring history-backed inference/reconstruction/three-way upgrades.
- Historical workflow fixtures: “Again, seems like clutter to me if we don’t even use those old workflows”. This authorizes retiring graph12/graph26 and their layout-transition/golden baggage, not deleting unique generic behavior tests.

## Defaults contract

Keep `templates/default` and the existing schema-1 `TEMPLATE.json` parser/keys. Hashes are opaque last-reviewed equality receipts, never evidence that one plugin is newer. Preserve the actual newer-schema guard, which offers no replacement receipt; unchanged policy/capability floors remain enforced.

Compare current shipped path/hash presence with the receipt. A different opaque hash produces an ordinary review notice, never an upgrade-plugin warning. Missing/invalid receipts report that condition and offer the current shipped-hash snapshot for explicit review, without guessing an inferred historical base. Missing/invalid records never block work.

A legacy `removed` entry means reviewed absence: quiet while the current template lacks the path, a reviewable addition if it reappears. Newly reviewed/declined receipts contain exactly the current shipped `files` snapshot, retiring old tombstones. Consequently review/decline quiets the current notice even when local customizations or deletions are deliberately retained; a subsequent shipped change prompts review again. Merely reading never writes these receipts.

Every notice row offers explicit manual handling. When both files exist, show a correctly quoted `git diff --no-index` between local and current shipped files. For absent/local-only paths explain the comparison limitation and preserve the local choice. Never emit automatic copy/delete, historical old/new diff or `merge-file` application instructions. Local-only additions remain untouched. Remove `HISTORY_DIR`, `history_ids`, inferred-base logic and archive-dependent classification, keeping advisory isolation and safe paths/quoting.

No new capability/schema is needed: this changes advisory comparison output, with no SPEC §4.5 trigger—no new persisted keys, policy/workflow fields, operations, leases or fingerprint semantics. Update SPEC/DESIGN/HISTORY and bootstrap/MIGRATING guidance with the explicit supersession.

## Test migration and ownership

`test_design` owns all changed tests, test helpers and fixture data; accepted paths remain frozen during implementation. First make `engine_fixtures.TEMPLATES` use the shipped default, derive current default-node names from shipped15 and cover all graph nodes in the rename map, and extend renaming to `review.filter`. Adapt Sim/World/Autopilot readiness and generated object/cost/filter-verdict outputs, reusing existing current-Pilot logic without circular imports or another framework. Then migrate consumers. Do not conceal a copied full historical workflow inline or under another name.

| Retain on current graphs or small explicit scenarios | Retire only historical assertions |
|---|---|
| Current and fully renamed real Git capture-to-merge/stacked journeys | Frozen 12/26-node graph and prompt copies |
| Independent reviewers, filter joins, material/notes, skips, correction/dispute and owner-answer behavior | Exact old lens layout/count/prompt equality and layout-upgrade classes |
| Frontier/dependency/lease ordering and declared-input identity | Old node-name fingerprint snapshots |
| Carry/sync/frozen tests, budget rounds and normalization/allowlist properties | Historical replay/golden JSON whose sole claim is old-layout identity |
| Safe current comparison, opaque/null/missing/invalid/newer-schema receipts, decline, deletion, read-only previews and quoting | Archive/seed/reconstruction/three-way tests |

Apply this map to lenses/lens_polish/review_lenses, merge_sync, owner_questions, branching, sync_card and g1038/node_def_fp_1.1/g1039 fixture consumers. Preserve any unique generic case from removed classes as a focused current or genuinely small scenario assertion. Record the actual retained/replaced/deleted groups with reasons in the test output; passing by blindly deleting failures is unacceptable. Migration tests should pass against unchanged engine semantics; new defaults-contract cases demonstrate the intended missing behavior before runtime changes.

`implement` owns only defaults runtime simplification, archive and `.agents/template_history.py` deletion, bootstrap/reference/contract documentation and package cleanup. It must not repair frozen tests directly; send defective tests back to `test_design`. No generic engine semantic or installed-policy change is authorized.

## Verification and boundaries

Run focused migrated helper/journey/lens/frontier/carry/defaults modules with real local Git/CLI fixtures first, then unchanged configured full validation. Inspect generated/installable package contents: current templates remain; history/graph12/graph26 and live references to them are absent. Check prompt budgets, links and whitespace. Main risks are lost coverage, renamed filter edges and misleading receipt handling; the retained-case map, full current/renamed journeys and receipt matrix address them.

Reject archive deletion with broken consumers, a new compatibility store, and hidden historical graph copies. No policy branch/rewrite, unrelated migration removal, release/main/paper-pin actions, infrastructure or banked reset. Root verifies current head/CI before any authorized admin merge.
