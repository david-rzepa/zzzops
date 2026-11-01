# G1024 review_design (attempt 1): shipped-default policy updates

Reviewer: claude:e6ad/rd1025. Design revision 2, checked against read_dev 8d8437a.

## Verdict

**Changes requested: one finding.** The design meets the spec. The owner's original concern (the old engine told repositories when a default changed) comes back in the reset's style:
- policy stays explicit in the repository, with no fallback at run time;
- each repository has a provenance record;
- `next` and `validate` show a non-blocking item;
- updating and declining are both reviewed policy branches, run from the bootstrap skill;
- the engine stays read-only.

The history store is the right call. It is the only option that gives the "working diff command from the old default" the acceptance asks for, and that recovers this repository's G1016 drift exactly. The one problem is version skew between installed plugins. The comparison treats a recorded base that the running engine does not know as "upstream changed". So an *older* plugin would offer to reconcile the repository onto *its* older defaults, and its `reviewed` record would downgrade the bases.

There is no owner question. The fix has a clear winner, and every other choice stays inside this goal or is already settled by the spec, G1027 or G1017.

## Claims checked at 8d8437a

- **Template history:** 5 commits touch `templates/default` (4 at c3791a0, plus G1020). They hold 28 distinct blobs, which is the design's 26 plus G1020's 2.
- **This repository's files:** `test_design.md`, `implement.md`, `design.md`, `review_design.md` and `workflow.json` each equal a stored version that is not the current one. `POLICY.json` matches no stored version. The design's table holds. `approve_design.md`, `approve_merge.md` and `review_impl.md` are also historical versions, so they will appear too. That is fine.
- **The guard:** `integrate`'s policy-paths check (ops/integrate.py:104) covers only `POLICY.json`, `workflow.json` and `prompts`, as the design says.
- **The `next` cap:** `render.NEXT_LIMIT = 8192`, and the cap loop drops actions or needs_human to fit. A top-level compact item of about 600 bytes therefore displaces at most a few actions, as `legacy` already does. Its placement matches `legacy` (render.py:630, cli.py:229).
- **`policy_update` is not on dev,** so G1017's marker for this row (`engine contains "policy_update"`) first matches on this PR. That is correct.
- **G1027:** its design §205-207 says a separate file that older engines ignore needs no capability. G1024 follows that and adds none. The template's `engine.requires` change will reach repositories as an `update` of `POLICY.json`. This is consistent.

## Finding

**F1 (design): an older plugin treats a newer recorded base as "upstream changed", and its `reviewed` record downgrades the base.**
- In §3.3's last row, a base B that is null *or not in the history store* is listed as `upstream: changed` (when S is present) and `local: unknown`, with a `manual` apply and a local-to-new diff. The item's `record.reviewed` sets every base to the running engine's S.
- Version skew between installed plugins is normal in this repository. Two marketplace caches, 6747a5e and c3791a0, are in use today, and the Codex engine is on 15b59a5.
- Suppose a newer plugin wrote B = S_new, and an older one later runs `next`. B is missing from the older store, so the older plugin shows an `update` item that presents its own older template as "the new default", and an agent following "compare by hand" could adopt it. If the agent writes the offered `reviewed` record, B goes back to S_old. The newer plugin then lists the file again, and the record ping-pongs between versions.
- **Fix:** separate "unknown to this engine" from "unknown provenance".
  - A non-null base that is not in the running engine's store is reported as `local: unknown` with `upstream: unknown_base` ("recorded by a newer or unreleased plugin: upgrade the plugin to compare"). It gets no diff to the running template and no apply.
  - `record.reviewed` keeps such bases unchanged instead of resetting them to S, and is omitted when every listed file is in that state.
  - `null` (written by `inferred`) keeps today's manual compare.
  - §9's "builds from unmerged branches" risk degrades the same way.
- **Test:** a record written with a store that contains one more version than the running engine's produces no `upgrade` direction. Its `reviewed` record leaves that base unchanged.

## Notes (not findings)

- **`.zzzops/TEMPLATE.json` outside the integrate guard (known gap, §4/§9).** The gap is acceptable as reasoned. Guarding the file changes `git.integrate`'s behaviour, and under G1027 §143 that means a fingerprint bump plus a capability, which re-runs every integrate. The worst case is a goal diff that silences a notice, and the file is visible in review. An agent "fixing" the item in a goal diff is the G1023 failure mode, so the execute-skill line (§3.7) should say: "never edit `.zzzops/TEMPLATE.json` in a goal; use the bootstrap update". That is a text change.
- **Per-file applies can be inconsistent with each other.** Take a `removed` prompt, unchanged here (so `delete`), while the owner declines the `workflow.json` change that still references it. The result fails validation. Step 5 catches it, but the skill should say that a prompt's delete or copy follows the `workflow.json` decision. This matters for G1022's restructure.
- **G1025 coordination.** §7 discusses only `settings.branching`. G1025 also changes the shipped `workflow.json` (it adds `graphs.release`) and adds `approve_start.md` and `approve_finish.md`. Its PR must therefore run `.agents/template_history.py --write`. The history test enforces this whichever merges first, but the root should pass G1025 the same note as G1022.
- **The 8,192 cap.** Test 7 covers 30 files. With `files` capped at 10 paths, the compact form is bounded.
