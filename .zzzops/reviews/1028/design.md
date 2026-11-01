# G1028 design: keep findings and their status straight across review rounds and goal edits

**Revision 2** answers `review_design` attempt 1.
- **F1:** `follows` ships as the G1027 capability `finding_follows` rather than an `engine.min` raise. Submit refuses `follows` until the policy requires that capability. Both merge orders against G1027 are stated (§6a, §9, D8).
- **F2:** a `follows` finding inherits `rounds` but never `upheld`. It is always `upheld: false`, so new text stays open to dispute and escalation (§3.3, D5, tests 9 and 9a).
- **Review note:** `carried_findings` lists every finding that is live after the edit only because it is carried (§3.1).

Revision 1 read at `read_dev` 8d8437a (G1000, G1020 and G1023 merged). Builds on G1017 design revision 3 (blob 42144d6): G1028 is G1017's case 3. `depends_on` is already `[1017]`, so this PR edits `docs/design/` and adds a HISTORY §4 row (§9). It coordinates with G1022 (approved: multi-lens reviewers and the finding `lens` tag) and G1026 (in design: `owner question:` findings) in §8.

## 1. Outcome

Four defects found while dogfooding Release 1 are fixed:

1. **Open findings no longer vanish when their review goes stale** (dogfood 29, 47). After a spec or `depends_on` edit, or after a sibling finding reopens an upstream node, an open finding stays live as long as the output it names is unchanged. It appears on the target's next card marked `stale_review: true`, and the target must answer it with `fixed:` or `disputed:`. The `edit` preview lists these findings, with the `--set` lines that waive them, so an edit can drop them on purpose.
2. **Restating a resolved finding is no longer refused as unknown** (dogfood 28, 46). The review card lists only open prior findings under `previous.findings` and lists the resolved ones separately under `previous.resolved`. A restated `resolved` is accepted. A restated `open` for a resolved finding is refused with "already resolved", and the refusal says how to reopen it.
3. **A partly fixed finding can be linked** (dogfood 44). A new finding may carry `follows: <prior id>`: the reviewer resolves the prior finding and raises what remains. The link is stored, shown on cards and listed on approval items, and it keeps the dispute count.
4. **Worker commands run from any directory** (dogfood 13, 42). Every command a worker is given carries `--repo <dir>`. This is a new global flag accepted by every verb. The "not inside a Git repository" error names the directory it tried and says to pass `--repo`.

## 2. What was found at read_dev

- **Liveness** (`frontier.frontier`, pass 1). A finding is live only if its carrier's record is fresh: `if not fresh[c] and t != c: continue`. A carrier is fresh when its recorded inputs still fingerprint to its `input_fp`. A spec edit changes `review_design`'s `spec` input, so the review is no longer fresh and its open findings on `design` stop being live. `design` is then `ready (stale)` with `corrections: []`. This is dogfood 47. Dogfood 29 has the same cause: `review_tests` raised findings on `design` and `test_design`. `design` re-ran, which made `review_tests` stale, so the `test_design` finding died, although `test_design` had not changed.
- **The finding still describes the target's current output.** Each finding stores `target_fp`, the target's `out_fp` when it was raised, and liveness already requires `target_fp == out_fp(target)`. When the carrier is stale but the target is unchanged, the defect the finding names is still present in that output. The freshness gate therefore drops findings that are still true.
- **Prior statuses** (`records.process_findings`). `prior` holds only the open findings of the review's latest record, so `unknown = set(status) - prior_ids` treats an already resolved id as unknown. `card.previous` lists every finding of the latest record, resolved ones included, with no flag. `output_schema` says "for every prior open finding". So a reviewer who restates the list it was shown is refused (dogfood 46, hit twice).
- **Statuses** are `open`, `resolved` and `waived` in records (`schemas.validate_finding`); submit accepts `open` and `resolved` (`_check_new_findings`). Nothing links a new finding to an earlier one.
- **Waiving** already exists: `edit --set 'records.<n>.findings[<i>].status="waived"'`, with a `note` (the skip refusal in `verbs.skip_refusal` prints these lines).
- **Commands** (`render.command`): `ctx.prefix + argv`, with no directory. `Session` calls `Git.discover(os.getcwd())`, which raises `environment: not inside a Git repository`, with `details.cwd` and no hint. `Git.discover` already accepts any directory inside the repository or a linked worktree, and resolves the primary worktree from it. `Session.__init__` already takes `cwd`. File arguments (`--output`, `--artifact`, `--file`) are opened relative to the process's working directory, not the repository.

## 3. Approach

### 3.1 Findings carried from a stale review (item 1)

**Rule (SPEC §4.9).** In pass 1, a finding on another node (`t != c`) whose carrier `c` is not fresh is still live when all of these hold:
- the carrier is an agent or human node, not an op;
- the finding is open, and its `target_fp` equals the target's current `out_fp` (the existing condition);
- the carrier is a filtered lens (G1000) and the filter's latest done record, fresh or not, did not judge the finding a `note`. A material finding is carried. A non-material finding is carried only with the verdict `keep`.

Such a finding is **carried**. A finding from a fresh carrier works exactly as today.

**Why op findings are excluded.** An op re-observes, and its findings are rebuilt on each run with fixed ids (`op_findings`). A stale `run_tests` or `integrate` record means the observation is out of date (for example, the base moved). Carrying its failure would reopen `implement` for a test result that may no longer hold. Today's behaviour is kept: the op re-runs and raises the finding again if it still holds.

**Why the target's fingerprint is the test.** A carried finding stops being live as soon as its target produces a new output. That is the same moment it stops for a fresh carrier today. The stale review then re-runs (it is stale anyway). Its card shows the finding under `previous.findings`, with the target's response, and the reviewer resolves it or keeps it open. No new state is stored. Carrying is a frontier rule over records that already exist, so it works the same for every cause of staleness: a spec or `depends_on` edit, a sibling finding that reopened an upstream node (dogfood 29), a `def` or policy change, or a base move.

**Card.** Each correction entry gains `stale_review: true` when its carrier is stale. `output_schema.responses` adds one sentence when any correction has it: "A `stale_review` finding came from a review whose inputs have since changed: answer it `fixed:` if your output handles it, or `disputed:` with the reason if the change made it moot." Submit already requires a response for every live correction (`check_responses` over `corrections_of`), so these findings now get answers in the record.

**Edit preview (SPEC §3.16).** `edit` (both the dry run and the applied result) gains `carried_findings`. It lists every finding that is live after the edit only because it is carried (its carrier is in `stale`), whether or not it was already carried before the edit. That covers a second edit, and a material lens finding that becomes carried before its filter has run, so the root sees the complete waive list: `{"goal", "id", "from": <carrier>, "target", "text": <clipped to 120>, "waive": "--set 'records.<carrier>.findings[<i>].status=\"waived\"' --set 'records.<carrier>.findings[<i>].note=\"<who waived it, and why>\"'"}`. A root that means to drop a finding adds those `--set` lines to the same edit. An edit that waives them carries nothing. The applied edit prints `warning` when `carried_findings` is non-empty and nothing was waived: "N open finding(s) stay live on their targets after this edit; see carried_findings".

**Plumbing.** `frontier` returns a fifth value, `stale`: the set of carriers with a done record that is not fresh. `GoalResult` gains `stale: set`. There are two call sites, both in `frontier.py` (`portfolio` and `all_terminal_current`). `card._carrier` already finds a correction's carrier, and `stale_review` is `carrier in res.stale`.

### 3.2 Resolved findings on review cards and in submit (item 2)

- **Card (SPEC §3.14).** `previous.findings` lists only the open findings of the review's latest record (`target != n`), each with `follows` when it has one (§3.3). A new `previous.resolved` lists the resolved and waived ones as `{"id", "status", "text": <clipped to 120>}`. This is enough for the reviewer to avoid raising them again or to cite them in `follows`. Both lists are bounded by one round's findings: a record keeps only the findings that were open going into its round, plus the new ones.
- **`output_schema.findings`:** `[{"id": <id>, "status": "open"|"resolved"} for every finding in previous.findings, {"target"?: <node>, "text": …, "follows"?: <id>} for new ones]. Ids in previous.resolved need no status. When a prior finding is partly fixed, resolve it and raise what remains with "follows": <its id>.` The G1000 sentence about what a finding reopens follows unchanged.
- **Submit (SPEC §4.14, `process_findings`).** Ids given a status are checked against the latest record's findings with `target != X`, of any status:
  - an open one: as today;
  - a resolved or waived one given `resolved`: accepted as a no-op. It is not copied into the new record, which matches what happens to it when it is left out;
  - a resolved or waived one given `open`: refused with `validation`, "already resolved: <ids>", hint: "A closed finding cannot be reopened by status. Raise a new finding with \"follows\": \"<id>\" for what remains." For a waived one the message says "already waived".
  - an id not in the record: refused as today, "unknown finding ids: …". `details.needs_status` lists the open ids so the reviewer can see which ones need a status.
- The `missing` check ("give a status for: …") is unchanged and covers only open findings.

### 3.3 `follows` (item 3)

**Shape.** A new finding in a submit output may carry `follows: <id>` (submit output, SPEC §3.10; `_check_new_findings` adds `follows` to the allowed keys, a string matching `FINDING_ID`). The stored finding (SPEC §5.1 finding keys; `FINDING_KEYS`) gains optional `follows`. Findings without it are unchanged.

**Validation in `process_findings`** (review nodes only; a non-review node's finding with `follows` is refused, as a status is today):
- `<id>` must be a finding of this node's latest record (any status). Otherwise: "follows: <id> is not a finding of <X>'s previous review".
- If `<id>` is open, this submission must give it `resolved`. Otherwise: "follows: <id> is still open; resolve it, and let the new finding carry what remains". Keeping both open would leave the target with two findings for one defect.
- Two new findings may follow the same id (a finding split in two).

**Inherited fields.** When `target` is omitted, it defaults to the followed finding's target, not the subject. When the targets match, the new finding takes `rounds = followed.rounds + 1` if the target's response to it was `disputed:` (an agent target), else `followed.rounds`. This is the same arithmetic as a finding kept open, so "resolve and follow" cannot reset the dispute count that escalates to the human (`frontier.escalates`, rounds ≥ 2). When the targets differ, it starts at `rounds: 1`.

**`upheld` is never inherited.** Every new finding, `follows` or not, starts at `upheld: false`. `upheld` records that the human sided with the reviewer on that finding's text. An upheld finding cannot be disputed (`check_responses`) and never escalates (`escalates`). The reviewer writes a follow-up's text freely. If that text inherited `upheld`, the reviewer could add demands the human never saw, and the target could neither dispute them nor reach the human. A follow-up of an upheld finding is therefore disputable. It keeps the `rounds` count, and a finding is upheld only after it has escalated, so that count is already ≥ 2. The follow-up therefore goes to the human as a `dispute` item as soon as it is live (`escalates`: rounds ≥ 2 and not upheld). The human sees the new text and upholds or waives it. A follow-up of a finding that was never disputed starts below 2 and escalates only after a dispute, as any finding does.

**Display.**
- Card corrections: `follows: <id>`, plus `follows_text` (the followed finding's text, clipped to 120 characters) when that finding is still in a record.
- Review cards: `previous.findings` entries carry `follows`.
- Approval items (SPEC §3.15): `facts` gains `follows: <new> ← <old>, …` (or `none`) beside `waived` and `disputed`. The PR body is not changed here (`facts` is not in it today).

**Rejected:** a third status `partly`. It would need its own liveness, filter and escalation rules, and a target response that is neither fixed nor disputed. With `follows`, statuses stay binary and the remaining defect is an ordinary open finding.

### 3.4 `--repo` (item 4)

- **Flag (SPEC §6).** A new global flag, `--repo DIR`, is accepted by every verb, beside `--remote`, `--integration` and `--policy-ref`. `cli.session` passes it to `Session(cwd=…)`, so `Git.discover` resolves the primary worktree from it. DIR may be any directory inside the repository or one of its linked worktrees (a goal workspace included). The process does **not** `chdir`, so file arguments stay relative to the caller's directory, as today. `validate --policy` without `--dir` defaults to `<repo>/.zzzops` when `--repo` is given.
- **Printed commands (SPEC §1.6).** `render.Ctx` gains `repo: str | None`. `render.command` appends `--repo <repo>` to `argv` and to the command text when it is set. `Session.ctx(worker=True)` sets it to `git.primary`. Worker-facing output uses it: the task card's `commands` (submit, blocked, renew, abandon), `renew`'s `abandon`/`restart`, `abandon`'s `restart`, and submit refusal hints that print a command. `next`, items, `show`, `edit` and `validate` do not: the root runs them in the repository, and leaving them out keeps `next` under its 8,192-byte limit.
- **Error (SPEC §1.5).** `not inside a Git repository: <cwd>`, with the hint "Run zzzops from the repository, or pass --repo <a directory inside it>. Task-card commands already carry --repo." When `--repo` itself is not inside a repository, the message says "--repo <DIR> is not inside a Git repository".
- **Card size.** About 35 bytes per command text (×4) plus the same in `argv`. `shrink` drops `argv` first, so the net cost after shrinking is about 140 bytes. Compacting resolved findings in `previous` (§3.2) saves more than that on round-2+ review cards.

**Rejected:**
- A `cwd` key on each command. Agent shells often reset their directory between calls (this worker's harness does), so a worker would have to remember to type `cd <cwd> &&`. A command that carries its repository can be pasted as is.
- Locating the repository from the lease. The lease is a ref inside the repository, so nothing outside the repository can find it.
- An environment variable (`ZZZOPS_REPO`). It is invisible in printed commands, and every worker would need it set.
- `-C DIR` (Git's spelling). The argument parser takes only long flags, and every existing flag is a long one.

These are the designer's choices. The flag is a new, additive name in CLI input, but no other option clearly beats `--repo` against the constraints above (§10).

## 4. Interfaces and data that change

| Where | Change | Compatible? |
|---|---|---|
| `frontier.frontier` | carry rule; returns `(st, cur, live, notes, stale)` | internal; two call sites |
| `GoalResult` | `stale: set` | internal |
| Card `corrections[]` | `stale_review`, `follows`, `follows_text` (optional keys) | additive |
| Card `previous` (reviews) | `findings` open only; new `resolved` | changes listed content; prompts already say "every prior finding" of `previous.findings` |
| Card `output_schema` | `findings` and `responses` wording | text |
| Card / renew / abandon commands | `--repo <primary>` appended | additive flag |
| Submit output (review) | new finding key `follows` | additive input |
| Stored finding | optional `follows` | **older engines refuse it** (unknown key); capability `finding_follows`, see §6a |
| `engine/capabilities/finding_follows.txt` | new (G1027 form) | additive |
| Submit refusals | "already resolved"/"already waived"; `details.needs_status` | message text |
| `edit` output | `carried_findings`, `warning` | additive |
| Approve items | `facts`: `follows: …` | text |
| CLI | global `--repo DIR` | additive |

No goal-schema bump: G1000 added `impact`/`material` to findings the same way, and G1022 adds `lens`. The stored key is gated by the capability `finding_follows` instead (§6a).

## 5. Behaviour walk-throughs

- **Dogfood 47 (spec edit after changes_requested).** `review_design:1` raises F1–F4 on `design` and stops at changes_requested. The root edits `spec`. The preview lists F1–F4 under `carried_findings`. After the edit, `review_design` is stale, but `design`'s output is unchanged, so F1–F4 are carried. `design` is `ready (stale)` and its card lists F1–F4 with `stale_review: true`. The designer answers all four and resubmits. Now `design`'s output has changed, so F1–F4 are no longer live. `review_design` re-runs, sees F1–F4 in `previous.findings` with the responses, and gives each a status.
- **Dogfood 29 (sibling reopen).** `review_tests:2` raises A on `design` and B on `test_design`. `design` answers A and re-runs. That makes `review_tests` stale. B is carried, since `test_design` is unchanged. `test_design` re-runs (stale on `design`), and its card has B with `stale_review: true`.
- **Op not carried.** `run_tests` fails and raises a finding on `implement`. Then the base moves. `run_tests` is stale, so its finding is not carried. `implement` re-runs for the base (routine) and `run_tests` re-observes.
- **Partly fixed.** `review_design:2` gives F1 `resolved` and raises G `{"text": "the rollback half is still missing", "follows": "review_design:1:1"}`. G targets `design`, with F1's rounds and `upheld: false`. The design card shows `follows` and `follows_text`. `approve_design`'s `facts` shows `follows: review_design:2:1 ← review_design:1:1`.

## 6. Risks

- **Mixed engine versions.** An engine without `follows` in `FINDING_KEYS` refuses a goal whose record holds it, and treats the goal as invalid. A new build in one clone could write the key while an old build in another clone, or the root's, still reads the goal. The capability gate in §6a closes this. The other changes (carrying, cards, `--repo`, refusals) store nothing new and need no capability.
- **Noisy carries after a large spec rewrite.** Findings about text the edit replaced are now carried. Remedies: the preview lists them with waive lines, and a target can answer `disputed: the spec edit removed this`. A dispute costs a re-review round only if the reviewer keeps the finding open.
- **Escalation of carried disputes.** A carried finding that was already at rounds ≥ 2 escalates to the human as a dispute, as it did before the edit. This is intended: the dispute was never settled.
- **Lens carry depends on the filter's last verdicts.** A non-material lens finding that no filter ever judged is not carried (it would only have been a candidate). A material one is carried even before its filter has run, because a filter only promotes and never demotes (G1000).
- **Card size.** About +140 bytes for `--repo` after `argv` is dropped, minus the saving from compacting resolved findings. The card-budget tests are re-measured (§7, test 12).
- **Merge conflicts with G1022.** Both edit `process_findings`, `_check_new_findings`, `FINDING_KEYS` and `card.previous`, and both add an optional finding key. The edits are small and next to each other. Whichever goal merges second resolves them through its `base` re-run. I recommend no dependency, so neither goal waits for the other (§8).

## 6a. Rollout: capability `finding_follows` (G1027 §3.6)

The stored `follows` key is a new finding key. Under G1027's rule (approved, blob 0c556c2, §3.6 "What ships with a new capability"), this goal ships a capability instead of raising `ENGINE_VERSION`/`engine.min`.
- **Name:** `finding_follows`. File `plugins/zzzops/zzzops/engine/capabilities/finding_follows.txt`: "Finding key `follows` on review findings: a new finding names the prior finding it narrows (G1028)."
- **Write gate.** Submit refuses a new finding with `follows` unless the policy requires the capability. It refuses with `validation`, "follows needs the policy to require finding_follows (settings.engine.requires)", and the hint names the policy branch. The check uses G1027's required set, `requires ∪ legacy_caps(min)`. So the first `follows` is written only after every engine that writes to the repository has been made to have the capability, because the floor check refuses writes from an engine that lacks it. This replaces revision 1's claim that "only the new engine accepts it", which did not protect old builds in other clones.
- **Rollout.** After merge, push `zzzops/policy/requires-finding_follows`, which adds `finding_follows` to `settings.engine.requires`. Follow G1027's §4 steps and MIGRATING wording: upgrade, and never remove the key. Until that branch lands, reviewers use resolve plus a plain new finding, as today. The card's `output_schema` mentions `follows` only when the policy requires the capability, so no reviewer is told to use a refused key.
- **Both merge orders** (as G1027 §5 does for G1022):
  - **G1027 merges first:** this PR adds `finding_follows.txt` and appends `"finding_follows"` to the pinned `SHIPPED` set in `.agents/test_engine_capabilities.py` (G1027 test 6). The gate reads the required set directly.
  - **G1028 merges first:** no capability form exists yet. This PR follows the rule in force at its merge: `ENGINE_VERSION` goes to the next minor at merge. The gate is "`engine.min` ≥ that version", and the rollout raises `engine.min` to it through a policy branch. When G1027's implement re-runs on the new base, it adds `"<that version>": (…already mapped…, "finding_follows")` to `LEGACY_VERSIONS`, adds `finding_follows.txt`, and turns the gate into the required-set check. Policies that raised `engine.min` keep working through the map. This PR's description carries one line saying this for G1027's implement.
  - **No dependency edge on G1027.** An edge would serialize this goal behind G1027 for a one-file swap. The root passes this paragraph to G1027's implement as a note if G1028 merges first.
- **G1022 interaction:** independent. G1022 ships `lenses`, this goal ships `finding_follows`, and the files never conflict.

## 7. Tests

New file `.agents/test_engine_findings_rounds.py`, using the existing fixtures (`engine_fixtures`, the `graph12` fixture graph and a fixture filtered-lens graph, so the tests do not depend on the shipped default graph that G1022 replaces):

1. **Edit keeps findings** (acceptance). After a changes_requested `review_design`, `edit --set spec=…`: the preview lists `carried_findings` with waive lines. The next `design` card has the findings with `stale_review: true`. Submit without responses is refused with `respond_to`, and with responses it is accepted. The re-run review's `previous.findings` holds them with the responses. A `depends_on` edit behaves the same way.
2. **Waive in the same edit.** The edit with the waive `--set` lines leaves `design` with no corrections, and `carried_findings` and `warning` are empty.
3. **Dogfood 29.** The sibling-reopen scenario of §5: `test_design`'s card carries B.
4. **Carry ends with the target's output.** Once the target resubmits, the carried finding is no longer live and `next` does not show it.
5. **Op findings are not carried.** A `run_tests` finding goes non-live when `run_tests` is stale on the base, as today.
6. **Lens carry.** For a stale lens: a material finding is carried; a non-material `keep` is carried; a non-material `note` stays a note; an unjudged non-material finding is not carried.
7. **Restated resolved** (acceptance). Restating `resolved` for an already resolved id is accepted, and the record does not hold it again. Restating `open` for it is refused with "already resolved" and the `follows` hint. A waived id gives "already waived". A made-up id gives "unknown finding ids" with `details.needs_status`. The card's `previous.findings` lists only open findings and `previous.resolved` lists the rest.
8. **`follows` round-trip** (acceptance). It is stored on the record and validated by `validate_finding`. It is shown on the target's card (`follows`, `follows_text`), on the next review card's `previous.findings`, and in the approve item's `facts`.
9. **`follows` validation and inheritance.** Refused: an id not in the previous review, an id still open, `follows` on a non-review node. When `target` is omitted, it defaults to the followed finding's target. `rounds` is inherited, so a disputed finding followed by a new one escalates on the next disputed round. `upheld` is always false. With a different target, the new finding starts at rounds 1.
9a. **Following an upheld finding** (F2). The human upholds F, and the reviewer resolves F and raises G with `follows: F`. G has `upheld: false` and F's rounds (≥ 2), so `next` shows a `dispute` human item for G at once, with G's text. A `disputed:` response to G is accepted by `check_responses`. After the human upholds G, a dispute of it is refused. A follow-up of a never-disputed finding (rounds 1) does not escalate until it has been disputed and kept open.
9b. **Capability gate** (F1). `follows` is refused when the policy does not require `finding_follows`, with a message naming the capability, and accepted when it does. In the G1028-first order, the same test uses the `engine.min` form. `output_schema` mentions `follows` only when it is required. The capability file exists and is in `SHIPPED` (G1027 test 6) when G1027 has merged.
10. **`--repo`** (acceptance). The card's submit and renew commands, run in a subprocess from a temporary directory outside the repository, succeed; a relative `--output` resolves against that directory. A linked worktree path works as `--repo`. Without `--repo`, the error names the directory and the hint names `--repo`. `--repo` naming a directory outside any repository gives its own message.
11. **Printed commands.** Card, renew and abandon commands carry `--repo`, and `next` actions do not.
12. **Card budget.** The existing budget tests in `test_engine_card_budget.py` still pass with `--repo` and `previous.resolved`.
13. **Docs.** `test_engine_docs` (or the G1017 guard) passes with the `docs/design` edits and the HISTORY row. `CLI_USAGE` lists `--repo` and `follows`.

## 8. Coordination

- **G1022** (approved). Its `lens` tag and this goal's `follows` are sibling optional keys on new and stored findings. The lens-carry rule (§3.1) is written against `graph.filter_of` and the filter's verdicts, so it holds for G1022's multi-lens reviewers. A `follows` link stays within one reviewer node, so it may cross lenses of the same reviewer. G1022 D8 says a lens skip keeps the node's open findings. This goal additionally keeps them live when the reviewer goes stale because the lens set changed (`lenses` staleness). No dependency either way. The overlapping edits are listed in §6.
- **G1026** (in design). An `owner question:` finding is material, so it is carried. This matters for G1026's flow: when the owner's answer leads the root to edit the spec, the review goes stale, and without G1028 the owner question would vanish from the next design card. Flag for G1026's designer: today a stale input outranks `retry` in `frontier`, so an edit made while `design` is blocked waiting for the owner gives a `reason: stale` card. That card does not show `answer` (the card shows `answer` only for `retry`). G1026 should either show the record's `answer` on any card whose record holds one, or tell the root not to edit while an owner question is pending. That fix belongs to G1026, not here. G1026 may also list owner questions in approve items next to the `follows` facts line; the two additions do not interact.
- **G1019** (card `previous` bound) builds on `previous.resolved`, which already bounds the resolved part.
- **G1016 / dogfood 8** (findings arriving during a run). Untouched: `check_responses` already reports `respond_to`, and carried findings go through the same path.

## 9. Contract edits in this PR (G1017's rule)

This PR edits `docs/design/SPEC.md` and `DESIGN.md` (both are on its base through `depends_on: [1017]`) and adds a HISTORY §4 row:
- SPEC §4.9: the carry rule and the `stale` carrier set.
- SPEC §4.14: prior statuses (closed ids, restatement, the refusals) and the `follows` rules and inheritance.
- SPEC §3.10: submit output `follows`. SPEC §5.1 (finding keys): stored `follows`.
- SPEC §3.14: card `corrections[].stale_review`, `follows`, `follows_text`; `previous.findings` open only; `previous.resolved`; `output_schema` wording; `--repo` on commands.
- SPEC §3.15: `facts` `follows`. SPEC §3.16: `edit` `carried_findings` and `warning`.
- SPEC §1.5, §1.6, §6: the environment error and hint, printed worker commands, the global `--repo`.
- SPEC §4.5 (capabilities): `finding_follows` in the list of shipped capabilities, and the `follows` write gate. In the G1028-first order, this is instead the `engine.min` version note that G1027 later maps.
- DESIGN: one line in the findings section saying findings are judged against the target's output, not the carrier's freshness.
- HISTORY §4 row: `G1028 | #<pr> | carried findings (stale_review, edit carried_findings); closed ids on review cards and restatement; follows; --repo | SPEC §1.5, §1.6, §3.10, §3.14, §3.15, §3.16, §4.5, §4.9, §4.14, §5.1, §6`; capability `finding_follows`.

`plugins/zzzops/zzzops/references/CLI_USAGE.md`: `--repo` with the global flags, the Outputs paragraph (`follows`, closed ids need no status), and the `edit` row (`carried_findings`). Shipped prompt templates are not changed. `output_schema` carries the instructions, so this repository's `.zzzops/prompts` copies (policy paths, which a goal PR cannot edit) do not drift.

## 10. Decisions

| # | Decision | Rejected |
|---|---|---|
| D1 | Carry is a frontier rule: a stale agent or human carrier's open finding stays live while its target's output is unchanged. | Requiring every carried finding to be waived in the edit: it blocks every spec edit after a review, and it misses dogfood 29, where no edit happened. Copying findings into the edit's records: it rewrites history and needs new state. Carrying only edit-caused staleness: the frontier would have to know the cause, and dogfood 29 would stay broken. |
| D2 | Op findings are not carried. | Carrying them: stale observations would reopen code. |
| D3 | `edit` previews carried findings with waive lines. | A new `--waive` flag: `--set` waiving already exists and is what `skip_refusal` prints. |
| D4 | Closed ids on review cards move to `previous.resolved`; a restated `resolved` is a no-op; a restated `open` gives "already resolved". | Accepting a restated `open` as a reopen: it would revive a finding whose target has already answered it, outside the response flow. |
| D5 | `follows` on new findings, inheriting `rounds` only; always `upheld: false`. | A `partly` status (§3.3). A `follows` that resets rounds: it lets "resolve and follow" dodge escalation. Inheriting `upheld`: it puts new text beyond dispute. |
| D6 | Global `--repo`, printed on worker-facing commands only. | A `cwd` key, the lease, an environment variable, `-C` (§3.4). Printing it on every command: it adds to `next`'s byte limit for no gain, since the root runs in the repository. |
| D7 | No dependency on G1022 or G1026. | Serializing them: the overlaps are small textual conflicts. |
| D8 | `follows` ships as capability `finding_follows`, with a submit gate on the required set; both merge orders against G1027 are covered (§6a). | Raising `engine.min`: G1027, which is approved, removes it. Relying on "only new engines accept it": an old build in another clone still reads the goal. |

None of these needs the owner. D1–D5 change only how the engine handles findings it already stores. Undoing them stays inside this goal's code, except for the optional `follows` key, whose rollout is fixed by G1027's approved capability rule (D8). For D6, one option dominates for the reasons given.

## 11. Out of scope

- Dogfood 8 (findings that arrive during a fan-out run) and dogfood 22/G1019 (bounding `previous` overall).
- Showing `answer` on a stale retry card (flagged to G1026, §8).
- `--repo` on `next`, items and `show`.
- A `partly` status, and `follows` from human answers or ops.
