# G1037 independent Adversary design review

Decision: **changes requested** for one material release-evidence gap. No prior findings exist on this card. Read the complete card, both instruction blobs, spec and design attempt5 (`982d3c13e410a3f3c6bf0584d8e1cce94d67cb06`), OD1–OD8 and current policy/runtime at read_dev `edb9b2c9aa317220a8e1340f27c40b6a4b6a1b5a`. No other reviewer artifact was read. No app write, deployment or harness/model invocation was made.

## Material finding on design

Phase7 and A10 bind staging/production approval to the release tip alone, but an unchanged release tip does not prove that finishing into a moved production target deploys the staged code. At read_dev, git.line_finish checks the recorded line head and mergeability; a nonconflicting target-only commit survives the merge without changing that head. Extend the private release runbook and A10 evidence to capture the target tip and actual promotion candidate tree/artifact alongside the staged identity. Re-evaluate before the irreversible promotion whenever either relevant tip changes; if equality to accepted staging is lost or unproven, stop and re-stage/re-obtain the separate owner approvals rather than treating the unchanged release head as sufficient. Clarify that external staging evidence becoming stale is a root procedure, not an automatic engine guarantee. This needs no app/engine deploy-flow redesign or new privacy machinery.

Impact: A direct nonconflicting production-branch change during the run can be merged and deployed even though it was absent from the staged build, while both recorded approvals still name the same unchanged release tip; the owner and app users receive untested/unapproved combined code.

Read-only source evidence: `engine/ops/lines.py::finish` checks that the current line head equals recorded T, then obtains production target P and asks only `local_conflict(P,T)` before merging the PR at head T. `engine/ops/integrate.py::local_conflict` returns success for a conflict-free three-way merge. No recorded production base or staged-candidate tree is compared there; the existing mechanism must not be represented as automatically invalidating external staging evidence.

A tiny fictional temporary Git repository demonstrates the gap without touching the private app: stage a release change, advance production with an unrelated new file, then merge-tree. The release tip remains unchanged, the merge has no conflicts, and its tree differs from the staged tree. Private result: `g1037-adversary-release-target-proof.json`. The requested fix is procedural evidence for the already-decided OD3/OD6 content/approval boundary, not a new owner product choice or an engine feature.

## Other adversarial checks

The public/private split is explicit: app-specific facts, raw transcripts and migration detail stay in the private journal, public quotes redact identifiers, and A15 does the owner-selected bounded name/slug check. OD8 intentionally rejects scrub machinery, so this review does not recreate it, a deny-list, a history purge workflow or a per-write privacy gate. The review itself contains no private app name, slug, path, hostname or business fact.

Both harnesses must actually participate; unavailable participation delays the observation rather than becoming a pass. Build/capability and node-by-harness records plus private transcripts can support that evidence. Current observed Codex runtime is f017a54d3e9f; actual Claude model participation/matching runtime remains unverified, not accepted by this review. The last observed Claude weekly refresh (Nov5,07:00 Mexico City) is a Claude observation and is not a Codex refresh time. No usage reset is permitted.

Migration requires inventory/triage with releases, an owner go-ahead and an explicit old-policy mapping. Only prior approvals actually given may be carried. Later releases stay held rather than being executed speculatively. Local committed work is pushed per migrated goal; the owner's dirty/uncommitted checkout stays out of scope and fresh clones isolate run changes. Any branch housekeeping must be pre-listed and stop on file impact; deletion still needs the owner. Abort preserves the new engine and branches rather than destroying new-format evidence or restoring an older writer.

Failure paths prefer natural occurrences, deliberately lapse only safe leases/use real policy changes, never plant bad app work and allow honest not-observed outcomes. Carry/stale and blocked-finding observations are not forged to meet acceptance. Defects go through separate generic goals; release/design/deployment authority is not delegated by a goal. Staging and production remain real, separately owner-approved steps; the material finding above tightens the proof of what those approvals cover.

## Dogfood notes

None.
