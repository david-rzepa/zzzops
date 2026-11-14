# G1047 design review

Approved with no findings. Independently reviewed the design/spec and current defaults parser/comparison, fixture helper/consumers, maintenance utility and SPEC §4.5. No other review was read.

- **Intent:** both recorded owner quotations authorize the removals. The design preserves repository ownership, current templates and generic behavior coverage; it does not reopen publication or installed-policy choices.
- **Simplicity:** current-hash receipts and explicit two-way comparisons remove historical reconstruction rather than replace it with another store or fixture framework. Full historical graph copies cannot be hidden elsewhere.
- **Truth:** opaque hashes no longer imply a newer plugin. Missing/invalid records are advisory with a current snapshot offered explicitly; the real newer-schema guard remains distinct. Reviewed absence stays quiet until a path reappears; fresh reviewed/declined receipts contain current shipped hashes, so local customizations can be retained without a repeating notice.
- **Adversary:** safe path/command quoting, no automatic copy/delete/merge and no read-time writes preserve customization safety. Capability floors are not weakened.
- **Concurrency:** explicit policy review remains the write boundary; comparison/read-only paths do not mutate policy or receipts. No new shared state or generic engine semantics are introduced.
- **Rollout:** retaining schema-1 parser/keys while changing advisory interpretation has no listed SPEC §4.5 trigger. The design preserves actual schema/capability guards and requires explicit contract/guidance supersession plus generated-package checks. Test helpers/fixtures/tests are owned and frozen in test_design; the archive-updater utility and runtime/doc removal belong to implement.
- **Experience:** manual handling is stated for absent/local-only paths. The retention map names unique generic coverage to preserve—including renamed filter edges and complete current/renamed real Git journeys—and requires an actual retained/replaced/deleted inventory, not blind failure deletion. Focused local checks precede unchanged full validation and exact-head delivery gates.

Implementation/test reviews must verify that promised retention inventory and receipt matrix against actual changes; this design approval does not claim those checks already pass. No repository files were edited and no new tests or infrastructure were proposed.
