# G1016 design: cards and lease verbs explain restarts, staleness and findings

Read at integration commit 54d7e83. Coordinated with G1014 (approved design, attempt 2) and G1000 (design under review).

Attempt 3. It fixes review finding F2 (review_design:2:1): a checkpoint override must be a full 40-hex sha, so ref names such as `HEAD` and short shas are refused instead of resolving in the main repository (see §4a). It also settles the `previous.output` rule on purpose (§2: it stays `== ["def"]`).

Attempt 2 fixed F1 (reclaim cards could downgrade capability to `routine`; see §2, "Capability and `previous.output`") and took notes N1, N2 and N4, and the checkpoint wording fix (dogfood item 17).

## Outcome

- `abandon` prints the command that restarts the phase.
- A card whose inputs changed since the previous attempt says which inputs changed and how to see the change. This covers reclaim cards too, which today say only `reason: reclaim`.
- A `submit` refused over `responses` lists the findings to answer, with their text.
- `output_schema` says what a finding does. It also says checkpoint keys are optional and that an override is a full 40-hex sha. `submit` and `edit` refuse ref names and short shas there. The card has one clearly labelled renew command.
- CLI_USAGE documents what `ZZZOPS_TRACE` records.

No new fetches, records, lease fields or record-schema changes. The only tightened input check is the checkpoint override (§4a). FP_VERSION and ENGINE_VERSION do not change.

## Ownership with the parallel goals

| Item | Owner | What stays in G1016 |
|---|---|---|
| CLI_USAGE `abandon` row ("the next `start` needs `--reclaim`") | **G1014** §6 | Add "prints `restart`" to that row, rebased on G1014's wording |
| `restart` command shape `start G X --as <LABEL> --reclaim` | **G1014** (`render.live_lease_entry`) | `abandon` output uses the same shape (see 1) |
| Staleness of a *running* lease (edit preview, `renew inputs_changed`) | **G1014** | Nothing. G1016 covers only the *card* issued by `start` |
| Finding shape for filtered lenses (`impact`, `material`), notes, `previous.changed` for re-reviews | **G1000** | Only the sentence that states the consequence (see 4) |
| Re-review "what changed" (`subject` staleness) | **G1000** D7 | The `changed` pointer below skips the `subject` key |

## Approach

### 1. `abandon` prints the restart command (verbs.abandon)

Add `"restart": command(ctx, ["start", str(g), X, "--as", LABEL, "--reclaim"])` and `"hint": "The node is now reclaimable: a plain start is refused; run restart."` to the success output. This is the same argv G1014 puts in `live_lease_entry["restart"]`. **Merge rule:** whichever goal lands second factors the shared argv into `render.restart_command(ctx, g, X)` and uses it in both places. That is a two-line change, so neither goal waits for the other. With `--force` the output is the same, since the restarter is whoever runs it.

### 2. `stale_because` and `changed` on every started card (verbs.claim, card.build)

**Root cause.** For a reclaimable node, the frontier state is `{"name": "reclaimable", "lease": L, "fp", "parts"}`, with no `stale_because`. `claim()` copies it into `kind_state`, so the card prints `reason: reclaim` and nothing else, even when the abandoned attempt's inputs differ from today's. A ready-stale start already has `stale_because` (from the record's `fp_parts`), but nothing shows *what* changed.

**Staleness keys.** In `claim()`, whenever `st0["lease"]` exists, set the two sets below. That covers `reclaimable`, forced `running`, and (N4) a crash-loop `needs_human` state with cap `lease` taken with `--force --reclaim`.

```python
rec_sb = set(stale_keys(r["fp_parts"], parts)) if r and r["input_fp"] != fp else set()   # against the done record
sb = rec_sb | set(stale_keys(L_old.fp_parts, parts))                                    # plus since the abandoned attempt started
kind_state["stale_because"] = sorted(sb) or None
kind_state["record_stale"] = sorted(rec_sb) or None
```

For a ready-stale start (no lease), `claim()` sets `record_stale = stale_because`, since the frontier computed that set against the record. A `new` or `reopened` start has neither.

The union matters for display. On attempt 3, after a stale attempt 2 was abandoned, the new worker must still learn that its inputs differ from the last accepted output, because it never saw attempt 2's card. The card shows the union as `stale_because`. `record_stale` is internal to `kind_state` and is not printed.

**Capability and `previous.output` (fix for F1).** Both existing rules that read `stale_because` in `card.build` assume a done record whose inputs moved. They now read `record_stale` instead:

- `record_stale == ["inputs.base"]` gives capability `routine`. Only the base moved since the accepted output, so the work is a rebase.
- `record_stale == ["def"]` adds `previous.output`. **Decision:** keep today's exact match, only moving it from `stale_because` to `record_stale`. `previous.output` comes with the hint "If it still holds, resubmit it." (card.py:193). That advice is safe only when the node definition is the only thing that changed. If `def` moved together with `spec` or an upstream output, the previous output answers an older question, and inviting a resubmit would be wrong. Widening to `"def" in record_stale` would also change behaviour outside this goal's scope.
- `reason == "retry"` still wins and gives `reasoning`, as today.

Lease-since-claim staleness never changes capability. A reclaimed first attempt (`new`, no record) or a reclaimed `reopened` correction (record current, so `record_stale` is empty) keeps the node's own capability, even when its only lease-side change is `inputs.base`. Base re-runs whenever the integration branch moves, so this is the common case for `implement` and `test_design`. Keying the rule on the record set is simpler than looking at the abandoned lease's reason, and it stays correct after several reclaims.

**Reuse of G1014.** G1014's `live_input_changes` compares a before portfolio with an after portfolio. At reclaim there is no before portfolio, only the abandoned lease's recorded `Fp-Parts`. The reusable piece is the comparison G1014's `renew` makes: `stale_keys(L.fp_parts, current parts)`. G1016 uses the same expression and adds no second helper. **Decision:** no shared function, because it would be a one-line wrapper. Recorded here so reviewers do not ask for one.

**Pointer.** New `card.changed(session, res, n, old_parts, new_parts, since) -> dict`. It returns one entry per stale key that has a cheap, local pointer:

| Key | Entry | Source |
|---|---|---|
| `inputs.k`, selector kind `goal` (e.g. `spec`) | `{"diff": "git diff <old goal commit> <goal tip> -- goal.json"}` | old commit = `git rev-list -1 --first-parent --before=<since> <goal tip>`. Local: goal branches are fetched in full (store.py:108) |
| `inputs.k` of type artifact | `{"diff": "git diff <old blob> <new blob>"}` | both blobs read straight from the parts strings (`<V>blob:<sha>`). Validated as 40-hex. If the old blob is not local: `{"note": "previous version not available"}`. **No fetch** |
| anything else (`deps.*` maps, checkpoints, plain node outputs, `def`, `policy.*`, `subject`) | none | the key alone is shown. The current value is already on the card. `def` keeps `previous.output`. `subject` belongs to G1000 |

`since` is the abandoned lease's claim time (`claimed_at(s, L_old.tip)`, the existing helper) for a reclaim. For a record-stale start it is the record's `finished_at`. If both apply, it is the earlier of the two. **Known limit:** for a record-stale start, an edit made during the previous attempt, before its submit, falls before `finished_at` and is missing from the diff. The key is still listed. Making this exact would need a new record field, and with it a schema change and an engine gate, which is out of proportion here. During a running attempt, G1014's `renew inputs_changed` reports such edits.

The card gets `"changed": {...}` next to `stale_because`, only when it is non-empty, so existing cards stay byte-identical. Each entry is about 120 bytes, and `shrink()` needs no change.

### 3. `submit` refusal lists the findings to answer (records.check_responses)

`check_responses(responses, corrections)` already runs inside `submit`'s `mutate`, against the live findings fetched at submit time. On a key mismatch it gains `details`:

```json
{"respond_to": [{"id": "review_design:2:1", "from": "review_design", "target": "design", "text": "…", "upheld": false}],
 "no_longer_live": ["review_design:1:3"]}
```

- `respond_to` covers the missing ids. `from` is the carrier, taken from the `(carrier, finding)` pairs in `res.live[X]`. `check_responses` takes an optional `carriers` map (id to carrier), which `done_record` builds next to `corrections_of`. That is its only caller (verbs.py:441), and the existing argument stays unchanged.
- Text over 600 bytes is clipped, with `"full": reader.blob_view(text)`, the same pattern as card corrections.
- The hint becomes "Findings arrived while you ran: answer each in `responses` with 'fixed: …' or 'disputed: …' (drop the ones under no_longer_live), then resubmit." The refusal code stays `validation`.

### 4. `output_schema` states the consequence (card.output_schema)

Add a sentence to the `findings` text, built by a new `card.finding_effect(graph, n)` so that G1000 has a single place to extend:

- review node: `… for new ones. Each open finding reopens its target: it re-runs and must answer it in responses.`
- non-review node: `optional: [{"target": <ancestor node>, "text": …}]; a finding reopens that ancestor; this phase re-runs if that ancestor's output changes.` (N1: liveness ends when the target's output fingerprint changes. A `disputed:` answer, or a fix that leaves the output the same, leaves this phase current.)

**Merge rule with G1000:** G1000 owns the finding shape for reviews that declare `review.filter`. Whichever goal lands second adds to `finding_effect` the filtered branch: "A finding with material: true reopens its target; a note (material: false) reopens it only if the filter keeps it." No other G1016 code reads G1000's fields.

**Checkpoint keys (root's added item, dogfood items 9 and 17).** `submit` accepts an omitted checkpoint key and uses the suggestion or the work-branch HEAD (verbs.done_record). Today's text ("the suggested checkpoint if any, else HEAD") led a worker to submit the literal `"HEAD"`, which is refused. The text becomes:
`checkpoint (optional): omit the key to default to the suggested checkpoint if any, else your work branch's HEAD (a phase that adds no commit keeps its previous checkpoint). To override, give {"commit": "<full 40-hex sha>"}; ref names such as HEAD and short shas are refused. If a restack rewrote the previous checkpoint, submit refuses with checkpoint_required and asks for one.`

**Artifact keys (N2).** Workers confused `card.artifact.path` with the file to pass. The text becomes:
`artifact: write it to a local file and pass that file with --artifact; artifact.path is where submit stores it.`
It still starts with `checkpoint`, which the journey tests match on (test_engine_journeys.py:43). The CLI_USAGE **Outputs** paragraph gets the same "optional" wording.

### 4a. Checkpoint overrides must be a full sha (fix for F2)

**Root cause.** At 54d7e83, `validate_submit_output` (schemas.py:933) accepts `{"commit": <any str>}`. `done_record` (verbs.py:459) resolves it with `s.git.rev_parse(c)`, and `GitRun.run` defaults to `cwd=self.primary` (gitrun.py:79), so a ref name resolves in the **main repository**, not the goal worktree. `{"commit": "HEAD"}` therefore becomes the main checkout's HEAD, usually an integration commit, which is an ancestor of the work branch and so passes the ancestry check. The base is silently recorded as the checkpoint. Branch names behave the same way or resolve to unrelated commits. A short sha is unambiguous only by luck.

**Change.**
- schemas.py:933: the override must satisfy `isinstance(v, dict) and set(v) == {"commit"} and isinstance(v["commit"], str) and SHA.match(v["commit"])`, reusing the existing `SHA` (schemas.py:13, lowercase 40-hex). Message: `a checkpoint override is {"commit": "<40-hex sha>"}; omit the key to use the default`. Code `validation`, as today. This is a submit-input check only: record shapes, `RECORD_KEYS`, FP_VERSION and ENGINE_VERSION are unchanged.
- verbs.py:459-464 stay: `rev_parse` still checks that the sha exists (a full sha that is not a local object is refused with "does not exist"), and the ancestry check still refuses a sha outside the work branch. With a full sha, `rev_parse` is the identity, so the cwd no longer matters.
- verbs.py:917 (`fill_current_records`, the `{"commit"}`-only completion run by `edit`): before `rev_parse(cp["commit"])`, refuse with `validation`, `records.<n>.<k>.commit must be a full 40-hex sha`, when `SHA.match` fails. Also refuse with `validation`, `records.<n>.<k>.commit <sha> does not exist`, when `rev_parse` returns nothing. Today `rev_parse` returns None there (gitrun.py:131-133), and None is passed on to `ident.code_tree` and stored as the commit. This path has no ancestry check, and adding one is out of scope: there is no lease or work branch at edit time.
- Prompts: `.zzzops/prompts/test_design.md:8` shows `{"tests": {"commit": "<sha>"}}`. It becomes `"<full 40-hex sha>"`. `implement.md:8` ("else HEAD") becomes "else your work branch's HEAD; omit the key unless you override".
- CLI_USAGE **Outputs** paragraph: the same wording as the card.

**Why not resolve in the worktree instead.** Running `rev_parse` with `cwd=` the goal worktree would make `HEAD` work. But a worker's session may not be in that worktree, the main checkout's `HEAD` is still a trap for anyone reading the docs, and an omitted key already means "my work branch's HEAD". One spelling per meaning is simpler: omit for the default, a full sha for an override.

### 5. One renew entry (card.build)

Remove the top-level `renew` prose. Fold it into the command:
`"commands": {"renew": {"argv": [...], "command": "zzzops renew …", "when": "every 30 minutes (timeout 120); after any pause, renew first"}, …}`.
`lease.renew_every_minutes` and `lease.timeout_minutes` stay. **Decision:** merge rather than relabel, because two keys named `renew` were the confusion, and the size cost is the same. The `test_card_shape_and_size` key list drops `renew`. Workers' instructions saying "the card's `renew` command" still read correctly.

### 6. CLI_USAGE: `ZZZOPS_TRACE`

Add one line after the verb table: "`ZZZOPS_TRACE=<file>` appends one JSON line per network call (`git fetch`, `push`, `ls-remote`, and every `gh` call) with `cmd`, `rc` and `ms`. Local git commands are not traced." This matches gitrun.py:109 (`NETWORK`) and gh.py:58-62.

## Interfaces that change

| Where | Change |
|---|---|
| `abandon` output | adds `restart`, `hint` |
| task card | `stale_because` also on reclaim cards (union of lease and record staleness); new optional `changed`; top-level `renew` removed; `commands.renew.when` added |
| `output_schema` text | findings consequence sentence; checkpoint "optional" / omit-the-key wording; artifact `--artifact` vs `artifact.path` wording |
| `card.build` capability | `routine` downgrade and `previous.output` keyed on record staleness only (`kind_state.record_stale`, not printed) |
| `submit` `validation` refusal on responses | `details.respond_to`, `details.no_longer_live`, new hint |
| `submit` checkpoint override | must be a full 40-hex sha; ref names and short shas get `validation` (F2) |
| `edit` `{"commit"}`-only record completion | same full-sha rule; a missing commit is refused instead of stored as null |
| prompts `implement.md`, `test_design.md` | checkpoint override wording |
| CLI_USAGE | `abandon` row (+`restart`, on G1014's text), Outputs paragraph, `ZZZOPS_TRACE` line |

## Alternatives rejected

- **Record the claim time in records** so the goal diff is exact for record-stale starts. This adds a strict `RECORD_KEYS` entry, which older engines reject, so it would need an engine-version gate. Out of proportion.
- **Show old and new values inline.** They do not fit the 4 KB card, and the old value of a plain input is only a hash.
- **Let plain `start` reclaim an abandoned lease.** This changes `--reclaim` semantics, which guards mass expiry and dirty worktrees. Printing the command is enough.
- **A separate `findings_effect` key in `output_schema`.** Keys there are output keys, and workers and tests treat them that way.

## Risks

- **Committer-date lookup** for the old goal commit. Engine commits use the session clock, so if two edits land in the same second the diff can start one commit late. It is a pointer, not a gate, and `stale_because` stays exact.
- **Card size.** `changed` adds about 120 bytes per pointer key. Only goal-field and artifact keys get one. The existing size test also covers a reclaim-after-edit card.
- **Merge conflicts** with G1014 (`render.py`, CLI_USAGE row) and G1000 (`card.output_schema`) are confined to the two merge rules above.

## Tests

- **Abandon** (test_engine_lifecycle.py): `abandon` returns `restart.argv == ["start", g, "design", "--as", "<LABEL>", "--reclaim"]`. Running it with a real label succeeds, and a plain `start` is still refused with `not_ready`.
- **Reclaim after a spec edit:** start `design`, then `edit --set spec=…`, `abandon`, and `start --reclaim`. The card has `reason: reclaim`, `stale_because == ["inputs.spec"]`, and a `changed["inputs.spec"].diff` whose output (run with git) contains the new spec line. Control: abandon and reclaim with no edit, and the card has neither key.
- **Union:** a record-stale attempt 2 is abandoned, then reclaimed with no further edit. Attempt 3's card still lists the record-stale keys.
- **Capability (F1):** start `implement` (no record, reason `new`), advance the integration branch so `base` re-runs, then `abandon` and `start --reclaim`. The card has `stale_because == ["inputs.base"]` and `run.capability == "bounded"` (implement's own), not `routine`. Same check for a reclaimed `reopened` correction run on `design` after base moved: its capability is `architectural`. Control: a ready-stale `implement` whose record is stale only on `inputs.base` still gets `routine`, both on plain `start` and after an abandon and reclaim.
- **Crash-loop reclaim (N4):** a `needs_human` crash-loop node with a live lease, taken with `--force --reclaim` after a spec edit, gets `stale_because == ["inputs.spec"]`.
- **Artifact pointer:** a reclaim after `design` re-ran upstream gives `changed["inputs.doc"].diff == "git diff <old> <new>"`. With the old blob deleted locally, the entry is the "not available" note, and the trace shows no extra fetch (`ZZZOPS_TRACE` line count unchanged).
- **Submit refusal:** start `design`. A review raises a finding on it while it runs (submitted with a second agent). Then `design` submits without `responses`. The refusal has `details.respond_to[0]` with the finding's id, `from`, `target == "design"` and text. A response to a finding resolved meanwhile appears in `no_longer_live`.
- **Card snapshot** (4, 5): for a review card, a non-review card and a checkpoint-output card, assert the `findings` text contains "reopens" (and, for the non-review card, "if that ancestor's output changes"), the checkpoint text starts with "checkpoint (optional)" and contains "omit the key" and "full 40-hex sha", the artifact text contains "artifact.path", there is no top-level `renew`, and `commands.renew.when` mentions the interval. The existing journey tests pass unchanged (prefix matching).
- **Checkpoint override (F2)** (test_engine_schemas.py, next to `test_submit_outputs`): `validate_submit_output(g, "implement", {"summary": "s", "code": {"commit": v}})` returns a non-empty error list containing "40-hex" for `v` in `"HEAD"`, `"main"`, `"zzzops/goal/g1"` and a 12-char short sha, and also for an uppercase 40-hex string. It returns `[]` for `"a" * 40`. End to end (test_engine_lifecycle.py): an `implement` submit with `{"code": {"commit": "HEAD"}}` is refused with `validation` and nothing is recorded. The same submit with the work branch's full HEAD sha succeeds. A full sha of a commit outside the work branch is still refused ("is not in the work branch"), and a well-formed sha that is not an object is still refused ("does not exist").
- **Record completion (F2):** `edit --set records.implement.output.code={"commit":"HEAD"}` with `input_fp: "current"` is refused with `validation` naming the full-sha rule. A full sha that does not exist is refused with "does not exist". A real full sha is completed to `{commit, base, tree, change}` as today.
- **Docs:** the CLI_USAGE lines are present, and `prompt_stats.py --check` passes.

## Out of scope

- Staleness of running leases, and edit previews (G1014).
- Filtered-lens finding fields, notes, and re-review diffs (G1000).
- Pointers for `deps.*` maps, checkpoints, `def` and policy keys beyond the key name.
- Exact claim-time diffs for record-stale starts.
