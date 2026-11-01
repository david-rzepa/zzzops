# G1016 review_design (attempt 1)

Reviewed `.zzzops/reviews/1016/design.md` (blob fc9eeed) against the spec and integration commit 54d7e83 (`card.py`, `render.py`, `verbs.py` start/claim/abandon/submit/renew, `frontier.py`, `fingerprint.py`, `records.py`). I also checked it against G1014's approved design (attempt 2) and G1000's design.

**Verdict: changes requested. There is one material finding, and the fix is small.** The rest of the design is sound, covers all six spec items, keeps to the no-fetch rule, and merges cleanly with G1014 and G1000.

## Finding

### F1. A reclaim card's new `stale_because` can downgrade a first-time phase to the `routine` tier (target: design)

`card.build` sets `cap = "routine"` whenever `s.get("stale_because") == ["inputs.base"]` (card.py:79-80). That rule was written for record-stale starts: a done record exists and only the base moved, so the work is effectively a rebase. The design now also puts the lease-since-claim staleness on reclaim cards, and says "the existing card rules keyed on `stale_because` … apply unchanged".

In the default graph, `test_design` (reasoning) and `implement` (bounded) both consume `inputs.base`. `base` re-runs whenever the integration branch moves, which happens often while other goals land. So the following is a common sequence:

1. `implement` attempt 1 starts with reason `new`.
2. The integration branch advances, and `base` re-runs.
3. The lease expires or is abandoned.
4. `start --reclaim` runs.

Attempt 2's card then has `stale_because == ["inputs.base"]`, with no record at all, and `run.capability` becomes `routine`. The root routes a full first implementation, or a test design, to the cheapest model tier. The same happens for a reclaimed `reopened` correction run whose only lease-side change is base.

**Consequence:** reclaimed substantive phases silently run on a weaker model. That is a quality regression this goal would introduce.

**Fix (pick one, and state it in §2):**
- Apply the routine downgrade only to staleness against a done record. The simplest way is to key it on the record-stale set rather than the union.
- Or apply it only when the abandoned lease's own reason was `stale`.

Add a test: reclaim a no-record `implement` after base moved, and check that `run.capability` is the node's own.

## Non-blocking notes (no change required for approval)

- **N1. Non-review `finding_effect` wording.** "a finding reopens that ancestor, and this phase re-runs after it" is true only when the ancestor's output changes. Liveness (frontier.py pass 1) ends when the target's `out_fp` changes, and that includes `responses`. A `disputed:` answer, or a fix that leaves the output unchanged, leaves this phase current, so it does not re-run. Suggested wording: "…; this phase re-runs if that ancestor's output changes." This fits the goal's purpose: cards should not mislead.
- **N2. Dogfood item worth folding in (cheap, same function).** `output_schema`'s artifact text is "artifact: write the file and pass it with --artifact". Workers confuse `card.artifact.path` with the file to pass. Suggested wording: "artifact: write it to a local file and pass that file with --artifact; `artifact.path` is where submit stores it". This is a one-string change in `card.output_schema`, which §4 already edits. It does not touch `value_of`.
- **N3.** `check_responses` lives in records.py and has no reader. Clipping with `"full": reader.blob_view(text)` means `done_record` either passes the reader in or builds `details` itself. This is an implementation detail, not a design change.
- **N4.** A crash-loop reclaim (`needs_human`, cap `lease`, with `--force --reclaim`) also carries a lease, but it is not in the `reclaimable`/`running` condition, so its card gets no lease-side `stale_because`. This is acceptable as a known gap. It could be included at no extra cost.

## Claims verified

- **Reclaimable state.** It has no `stale_because` (frontier.py:214), and `claim()` copies the state into `kind_state` with `stale_because=None` (verbs.py:285). The root cause is stated correctly.
- **Lease fingerprint parts.** Leases carry claim-time `Fp-Parts` (leases.py), and neither current `renew` nor G1014's `renew` rewrites them. So `stale_keys(L_old.fp_parts, parts)` is exactly "since the abandoned attempt started", and `claimed_at` (the lease chain's root commit) is the matching `since`.
- **Artifact parts.** Artifact parts are `<V>blob:<sha>` (fingerprint.py:16). Checkpoint parts are `change:` and map parts are `sha256:`, which correctly get no pointer.
- **Local fetch only.** Goal branches are fetched without depth or filter (store.py:108). The goal-commit diff is therefore local, and `git.exists` makes no network call.
- **No refusal regression.** `check_responses` is called only from `done_record` (verbs.py:442), inside `submit`'s `mutate` over freshly fetched state. The refusal code stays `validation`.
- **Renew key.** The top-level `renew` key is used only by card.py:89 and the shape test (test_engine_lifecycle.py:309). No doc depends on the key name.
- **Trace.** `NETWORK = {fetch, push, ls-remote}` (gitrun.py:16, :109) matches the proposed ZZZOPS_TRACE line.

## Merge check

- **G1014.** The `restart` argv matches `live_lease_entry`. The `render.restart_command` merge rule is fine. The design adds no second staleness helper, and that decision is recorded. G1014 adds `parts` to running states, which nothing here depends on: forced reclaim goes through `lease_state`, which re-evaluates without the lease. The CLI_USAGE `abandon` row is rebased on G1014's text.
- **G1000.** The top-level `changed` key skips `subject`, and G1000 D7 owns `previous.changed`. The filtered-lens sentence for `finding_effect` matches G1000 D2 (material claims reopen the work, and notes reopen only if the filter keeps them).
- **G1018.** The design does not touch `card.value_of` or checkpoint rendering, and checkpoint keys get no `changed` pointer.
