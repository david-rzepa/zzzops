# G1037 design review, attempt 4

Approved. The reviewed subject is design blob `982d3c13e410a3f3c6bf0584d8e1cce94d67cb06`, compared with `3d5740027b00e0543fd2d9a6c0eeae3c3447bbac` and checked against integration commit `de5640d1c5909ea924450aeea6450497a78946f6` and the reviewed G1038–G1040 designs. There are no open prior findings on this card and no new finding.

## Spec and owner decisions

OD1–OD8 are preserved verbatim with the existing identifying-word redactions. The nine-phase plan still covers migration of all open goals with releases, Release 1 execution, later-release holds, a real stacked dependent and post-dependency sync, a cut/sync/finish release, naturally encountered failure paths, defect goals, cost reporting and the lens re-score. The write-up remains generic, and app-specific plans and evidence remain in the private journal.

The new text does not waive deployment approval: design approval authorizes only the planned repository work; staging and production each require their own owner approval. Staging and finish are tied to the same release tip, and a moved tip requires renewed decisions. The app's promotion steps stay outside the engine. Routine delegated approvals are distinguished from consequential owner choices, review-raised owner questions and deployment decisions; the actual decision-maker must be recorded. No deployment or private-app mutation was performed for this review.

The design still excludes new scrub machinery, per-write gates and history-wide scans. A15 remains the one prepublication name/slug check on the report and this goal's public artifacts. No identifying app information appears in the reviewed artifact or this report.

## Dependency adoption

The revision fixes the important distinction between an engine feature being present and the run opting into it. Phase 3 retains template requirements and explicitly requires `release_lines`, `merge_sync`, `round_budget` and `blocked_findings`, with `finding_follows` required when that record form is used. A18 verifies the installed policy and both engines rather than assuming that copying POLICY activates everything.

This matches the settled dependency designs:

- G1038 revision 3 gates merge mode on `merge_sync`; preserves forward history; uses scoped frozen tests and HEAD; squashes the PR onto the recorded synced base rather than an unrelated later trunk tip. The run adopts these rules and supersedes the older worker instruction to reorder test fixes before implementation. Empty tests or implementation parts are allowed as the dependency specifies.
- G1039 revision 3 keeps the recorded change identities only when its per-node clean predicate accepts the sync. The revision explicitly allows conservative staling for altered goal lines and hand resolutions that are not accepted whole-side unions. The non-context `review_impl.inputs.base` edge and after-sync prompt are adopted together so implementation review re-runs even when the subject checkpoint is carried; verification re-runs for the changed tree. The per-stage budget is observed under `round_budget`, with no new counter or forced carry.
- G1040 revision 2 requires the new design step 4 before or together with `blocked_findings`. The plan includes that pairing, distinguishes answered from unanswered owner questions and genuinely stale carriers, and observes surviving live corrections/refusals/check recurrence only when they occur. It neither manufactures failures nor claims unobserved paths passed.

The current integration tip has `release_lines`, `finding_follows`, `lens_findings` and `lenses` but not the pending friction-fix capabilities. The design accurately requires all dependencies to merge before the real run and installation of the resulting merged build in both harnesses. It does not pretend those capabilities are already available. An unavailable harness delays the observation instead of producing an assumed pass.

G1026 uses history-backed human decisions and has no `owner_answers` capability; the plan no longer invents one. `sync_carry` is likewise correctly rejected as a provisional name. Branch retention advice and provenance recording are adopted from their owning dependency designs without expanding this goal into an engine change.

## Feasibility, authority and validation

The revised base row is accurate: stack-ready engine operations may advance before dependencies merge, while this real run waits for all dependency merges as an explicit root precondition. The engine's existing `lines.finish` uses the approved recorded tip and rejects a moved live tip; separate outside-engine staging evidence remains a run obligation. No deploy-aware engine extension is proposed.

A1–A20 give the later test writer and independent implementation reviewer concrete checks. The new A18 checks adoption; A19/A20 distinguish observed behavior from cases covered only by dependency tests. Cost totals remain recomputable from the privately held per-holder data, with only anonymized totals published. The existing owner-checkout snapshot and freeze checks remain. No permanent test helper, new stored format or custom graph is introduced.

The material risks are named: production impact, mixed builds, accidental removal of merge mode, adoption gaps, naming, owner load and dependency delay. Abort preserves the new engine and branches. Required separate approvals and the public/private boundary remain intact.

No design change is needed. No new owner question meets the project's threshold.

## Dogfood notes

None. This was a read-only source and design review followed by the contracted review submission.
