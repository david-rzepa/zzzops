# G1029 design: flag at capture when a goal departs from the project's intent

Revision 2. It answers review_design:1:1 (F1): a `Project intent:` paragraph is spec text that an agent can write, so on its own it could hide a departure from every human view. Revision 2 changes four prompts and one test, and still changes no engine code.
- **The skill (D4):** Amend and Proceed require the owner's own words, given in the conversation. With no owner present, the goal is created without the paragraph, and the design's Intent lens raises the departure.
- **No skipped approval:** the skill never offers to skip `approve_design` for a goal with the paragraph, and removes that skip if the paragraph is added later by `edit`.
- **The lens (D3):** it honours the paragraph only when the paragraph quotes the owner's words with a date.
- **The approval prompt (D5, new):** `approve_design.md` shows the paragraph next to the lens verdicts.
- **Test 2:** the label must also appear in `approve_design.md`.

Read at dev 8d8437a. Builds on G1017 revision 3 (docs/design and its amend rule). It is coordinated with G1022 (approved: project intent is judged at design time only, by the Intent lens of the multi-lens `review_design`), G1026 (approved: owner questions) and G1027 (capabilities).

## Outcome

When the add-goal skill captures a goal, it compares the goal with `settings.intent` **before** it runs `new`. If the goal pulls against the intent, the skill quotes the intent sentence it conflicts with and offers the owner three ways on:
1. change the goal;
2. amend the intent, through a reviewed `zzzops/policy/*` branch whose text the skill drafts;
3. proceed, with the departure recorded.

When the departure is recorded or an amendment is pending, the design's Intent lens sees it, so the lens judges the design against the accepted departure instead of raising it again from scratch. A placeholder or absent intent skips the check, and the skill says the intent is not captured yet.

**The engine does not change.** The change is three prompt files (the add-goal skill, the Intent lens and the design approval), one contract paragraph and a few test lines.

## What was found at read_dev (8d8437a)

- **`add-zzzops-goal/SKILL.md`** has five steps: write the spec; agree skips; create with `new --file`; dispatch `design`; create child goals only after approval. It says nothing about intent.
- **`settings.intent`** is `("optional", "textmap")` in `SETTINGS_SHAPE`, with the keys `purpose`, `serves`, `not` and `principles`. Each value is text or a list of text.
  - `schemas.intent_warnings` emits `intent_placeholder` when a value starts with `TODO:`. `Session.warnings` adds it to every `next` and `show` output.
  - An **absent** intent warns nothing. This repository's `.zzzops/POLICY.json` has no `intent` at dev, so here `next` is silent.
- **`cmd_new`** builds the goal document from `title`, `spec`, `priority`, `release`, `depends_on`, `skip` and `links`, then prints `created` and `next`. It never reads `settings.intent`. Any output it printed would come after the goal exists.
- **How intent reaches a card.** `card.build` adds `card["policy"] = {k: settings[k]}` for an agent node that declares `policy`.
  - In the shipped 26-node graph, `intent_design` and `intent_impl` declare `policy: ["intent"]`.
  - In G1022's 15-node graph, only `review_design` does (G1022 D6).
  - In both graphs, every design-stage reviewer has the input `spec` from `goal.spec`. **So text in the goal's spec already reaches the Intent lens's card, next to `policy.intent`.**
- **`lens_intent.md`** has three parts: a heading; one paragraph with question (1) goal intent and question (2) project intent, plus the `TODO:` → `--blocked` rule; and an "On code:" line, which G1022 deletes.
- **`spec`** is in `GOAL_FIELDS`, so `edit --set` can change it, and its limit is 16 KB.
- **Policy branches.** A `zzzops/policy/*` branch raises the `policy_branch` blocker: new work is paused everywhere until the branch lands or is deleted. `new` still succeeds, because `require_writable` does not check the pause.
  - `validate --policy-ref` and `next --policy-ref` preview such a branch.
  - MIGRATING says an intent change stales the intent nodes of every open goal, without counting against the budget.
- **Prompt budget.** `prompt_stats --check` measures capture at 2,363 of 3,700 estimated tokens. `test_routed_workflow_signals_are_present` requires the capture signals in the skill.

## Approach

### D1. Where the comparison runs: in the skill, before `new`

The comparison is a judgement, so the capturing agent makes it, while the owner is still in the conversation. It needs one read, which already exists:

```
git show <coordinator.commit>:.zzzops/POLICY.json      # settings.intent
```

`coordinator.commit` comes from the `zzzops next --all` the skill already runs in step 1 to list dependencies. That run's `warnings` also show `intent_placeholder`.

**Rejected:**
- **`new` printing `settings.intent`.** It would arrive after the goal exists, which is too late for "say so before the goal is created". It would also add about 1 KB to every `new` output (the card budget is 4 KB, `next` 8 KB) for something the skill reads once.
- **A `new --check` or dry-run mode.** It is engine surface for a check that the engine cannot itself make.
- **The engine flagging a departure.** The engine has no judgement. A keyword match would raise false alarms and miss the real departures.

Spec item 1 names "`zzzops new`'s output" as a place to compare. Item 3 leaves the engine split to this design and asks for the smallest engine change, and here that is none. **The spec's "say so before the goal is created" is met only by the skill.** This is a choice whose undo stays inside the goal: a later goal can add an output key without breaking anything. So it is decided here, not put to the owner.

### D2. Where a recorded departure lives: a closing paragraph of the spec

For options 2 and 3, the skill ends the spec with one paragraph that begins with the fixed label `Project intent:`:

```
Project intent: departs from not: "A general project-management suite." Accepted as is. Owner (2026-11-01): "<their words>".
Project intent: departs from principles: "<sentence>". Amendment on zzzops/policy/intent-<topic> (PR #N): "<amended text>". Owner (2026-11-01): "<their words>".
```

This paragraph is the goal's `intent_note`, and it takes no schema change:
- It reaches the Intent lens in both graphs through the existing `spec` input. It also reaches the design worker, who must design within it, and, through D5, the owner at `approve_design`. The `Owner (<date>): "<words>"` part is required: it is what the lens checks (D3).
- It round-trips through Git like the rest of the spec: `show`, `edit --set spec=…` and the request-key hash all handle it already.
- Changing it later with `edit` stales `design` and the design reviews. That is correct, because the goal's terms have changed.

**Rejected: a goal field `intent_note`.** It would need all of the following:
- a goal-schema change and a new engine capability (G1027), or an `ENGINE_VERSION` bump, plus `engine.min` on every repository that uses it;
- a new input selector (`goal.intent_note`) on the Intent lens node of both graphs, which is a `workflow.json` change and a policy branch in every adopting repository;
- fingerprint wiring and tests.

All of that would carry the same text that the spec already carries to the same reader. The cost of the paragraph is weaker structure: the engine cannot list "goals with an accepted departure". Nothing in the spec asks for that list, and `git grep 'Project intent:'` over the goal refs answers it if anyone needs it.

### D3. The Intent lens reads the paragraph

`templates/default/prompts/lens_intent.md` gains one paragraph, placed after the existing one:

> If the spec ends with a `Project intent:` paragraph that quotes the owner's words with a date, the owner accepted that departure when the goal was added. Do not raise it again: judge whether the design stays within it, and raise any further departure. A paragraph without the owner's quoted, dated words accepts nothing. A departure is covered by an amendment only once `policy.intent` holds the amendment. In either case, until then, treat the departure as not accepted.

The quote is the evidence the lens can check, because the paragraph format of D2 requires it. A fabricated quote cannot be detected by any prompt. That is why the paragraph also always goes in front of the owner at `approve_design` (D5), and the owner sees there what was recorded in their name.

- An **unrecorded** departure is still raised as today: a material finding naming the intent sentence. G1026's instruction decides whether it carries the `owner question:` prefix. Its two options are change the goal or amend the intent, which changes the project's direction, so it usually will. G1029 adds no G1026-specific text, so neither goal waits on the other.
- **Amend case.** The open policy branch pauses all new work, so the goal's design runs only after the branch lands (and the lens then sees the amended `policy.intent`), or after it is deleted (and the lens sees a departure that is no longer covered, and raises it). Both outcomes are correct without any engine state.
- **G1022.** G1022 keeps `lens_intent.md` as `review_design`'s Intent lens and edits its paragraph and its "On code:" line. G1029 adds a separate paragraph, so whichever goal merges second resolves at most a trivial, adjacent-line rebase conflict. No dependency is added. That would stale an approved design for a one-line merge.

### D4. The add-goal skill (spec acceptance 1)

A new step 2 goes after "Write the spec". The old steps 2–5 become 3–6. Draft text, about 1.3 KB, roughly 330 tokens, so capture stays well under 3,700:

> 2. **Check it against the project's intent** before creating it. Read `settings.intent` with `git show <coordinator.commit>:.zzzops/POLICY.json` (the commit from `next`). If it is absent, or `next` warns `intent_placeholder`, skip the check and tell the human the project's intent is not captured yet (the bootstrap skill captures it). Otherwise judge whether the goal pulls against it: it serves someone other than `serves`, works against `purpose`, does something in `not`, or breaks a `principles` entry. If it does not, say nothing. If it does, quote the sentence and say why, then offer three ways on:
>    - **Change the goal** so it no longer conflicts.
>    - **Amend the intent.** Draft the amended sentence for the human to rewrite in their words, then put it in `.zzzops/POLICY.json` on a `zzzops/policy/intent-<topic>` branch, reviewed as a PR like any policy change. Preview it first with `zzzops validate --policy-ref <branch>`. Tell the human that while the branch is open, all new work is paused, and that landing it re-runs the intent review of every open goal.
>    - **Proceed** with the departure recorded.
>
>    Only the owner chooses, in their own words in this conversation. For the last two, end the spec with one paragraph: `Project intent: departs from <key>: "<sentence>".`, then either `Amendment on zzzops/policy/<topic>: "<text>".` or `Accepted as is.`, then `Owner (<date>): "<their words>".` The design's Intent lens and `approve_design` read it. With no owner present, create the goal without the paragraph and report the departure: the Intent lens will raise it for the owner.

Step 3 (skips) gains one sentence:

> Never offer to skip `approve_design` for a goal whose spec has a `Project intent:` paragraph. If an `edit` adds one, drop that skip in the same edit.

Without an owner present, the root agent captures goals from dogfood findings and similar sources. The goal then carries no paragraph, so the Intent lens finds the departure as an ordinary material finding. Under G1026 it becomes an `owner question:` (change the goal, or amend the intent), batched with the owner's other questions. No path lets an agent accept a departure on the owner's behalf.

The step reuses the bootstrap skill's rule, "record their words; never write the intent for them": the skill drafts, and the owner decides the text. When a goal is amended at capture, the skill runs `new` first and then pushes the policy branch. The goal's design then waits for the branch, as described in D3.

### D5. Approval shows the recorded departure

`templates/default/prompts/approve_design.md` gains one bullet:

> - Read the goal's spec (`zzzops show G --json`, `goal.spec`). If it ends with a `Project intent:` paragraph, show the paragraph verbatim next to the lens verdicts, and say that the owner accepted this departure from the project's intent at capture.

`approve_design` has no `spec` input, so this is guidance to the presenting agent, which reads the spec with `show`. It is not a new node input. A new input would change `workflow.json`, stale `approve_design` on every open goal, and need a policy branch in every repository. The prompt is the same in the 26-node graph and in G1022's graph.

The paragraph cannot get past the owner later either. An `edit` that adds or changes it changes `goal.spec`, which stales `design` and everything after it, so `approve_design` runs again and shows the paragraph. Together with D4's no-skip rule, every goal that carries the paragraph reaches a human approval that shows it.

### Worked against this repository's approved intent (intent-zzzops.json)

| Request | Verdict | What the skill says |
|---|---|---|
| G1029 itself | No conflict. It enacts the fifth principle. | nothing |
| "Sync goals to a Jira board, both ways" | `not`: "A second source of truth beside Git." and "A general project-management suite." | Quote both. Offer: one-way export (change the goal), amend `not`, or proceed with the departure recorded. |
| "Publish the plugin to PyPI on merge" | `not`: "A deploy, CI or release-publishing tool: its release support is a branching strategy." | Quote it. A one-off release script outside ZzzOps is a change to the goal. |
| "Auto-approve a design when every lens approves" | It pulls against `not`: "An engine that invents human decisions or acts without authority." The principle "approvals may be delegated" makes this a judgement call. | Flag it, because the decision moves from the owner to the engine, and quote both sentences. Amending is the natural path, for example "…delegated, including to a unanimous review, when the owner opts in." |
| Template intent (`TODO:` values) | `intent_placeholder` is warned | "The project's intent is not captured yet", and the check is skipped. |
| This repository at dev (no `intent` key) | absent | The same message as for the placeholder. |

Before writing this table, `schemas.intent_warnings` and `_check_shape` were run on the example intent: there were no warnings and no shape errors. The template intent gives `intent_placeholder`, and an absent intent gives nothing. That is why the skill checks for absence itself.

## Interfaces and data

- **Engine:** none. No CLI output, goal field, POLICY key or capability changes, so G1027 is not involved.
- **Shipped prompts:**
  - `skills/add-zzzops-goal/SKILL.md`: step 2 as in D4.
  - `skills/add-zzzops-goal/SKILL.md`, step 3: the no-skip sentence.
  - `zzzops/templates/default/prompts/lens_intent.md`: the paragraph in D3.
  - `zzzops/templates/default/prompts/approve_design.md`: the bullet in D5.
- **Convention:** the spec paragraph is `Project intent: … Owner (<date>): "<words>".`. The skill, the lens prompt and the approval prompt must spell the label the same way, and a test holds them to that.
- **`docs/design/` (G1017's rule, case 3: G1029 depends on 1017):**
  - DESIGN §3.12, "Capture flows into discovery", skill side: one bullet for the capture-time intent check, the three options (only the owner chooses), the `Project intent:` paragraph read by the Intent lens and shown at `approve_design`, and no `approve_design` skip for such a goal.
  - Every SPEC or DESIGN passage that quotes or summarises the Intent lens prompt (§8.2's lens prompts, once G1000's and G1022's amendments are applied): one sentence on the paragraph.
  - The implementer greps `docs/design` for `lens_intent`, `Intent lens` and `add-goal` at the PR's base, and edits every hit that describes these two behaviours.
  - A HISTORY §4 row: G1029, the PR, the sections changed, and "capture-time intent check (skill only); Intent lens honours a departure recorded with the owner's dated words; approve_design shows it".
  - The goal's README pending row is deleted if one exists.

## Tests

1. **`prompt_stats`:** capture's `WORKFLOW_SIGNALS` gains `"settings.intent"`, `"Amend the intent"` and `"Project intent:"`, so a later edit that distils the skill cannot silently drop the check. `prompt_stats.py --check` passes. Capture is about 2,800 tokens of its 3,700.
2. **Label agreement** (in `.agents/test_agent_plugin.py`): the literal `Project intent:` appears in all three files: `add-zzzops-goal/SKILL.md`, `templates/default/prompts/lens_intent.md` and `templates/default/prompts/approve_design.md`. The skill also contains `Never offer to skip \`approve_design\` for a goal whose spec has a \`Project intent:\` paragraph`, and the lens prompt contains `accepts nothing`.
3. **The spec reaches the lens.** This is an engine-free check, because the engine records nothing new: a template test asserts that the node declaring `policy: ["intent"]` at the design stage also has the input `spec` from `goal.spec`. In the 26-node graph that node is `intent_design`. In G1022's graph it is `review_design`. The test looks the node up by its `policy` field, not by name, so it holds on both graphs and through G1022's rebase.
4. **`test_design_docs.py`** passes: amendment ids resolve, and no landed goal is pending.
5. **Manual acceptance, recorded in the PR body:**
   - capture the four rows of the table against a scratch policy that holds `intent-zzzops.json`, and against the template's `TODO:` intent;
   - for the amend row, run `validate --policy-ref` on a local `zzzops/policy/intent-test` ref;
   - capture the Jira row with no owner present: the goal is created with no paragraph, and the departure is reported;
   - quote the skill's words for each row.
6. The full `python3 -m unittest discover -s .agents -p 'test_*.py'` passes.

The spec's engine test ("round-trips and reaches the Intent lens's card") applies only "if the engine records anything". It records nothing. Test 3 checks the one link that the design relies on.

## Rollout

- **Other repositories** receive the new skill with the plugin. The lens paragraph is template text: a repository that copied `lens_intent.md` adopts it through its own policy branch. Until then, its lens may raise again a departure that the owner already accepted, and the owner answers that finding by pointing to the paragraph. Nothing breaks.
- **This repository** has no Intent lens yet: its `.zzzops/` is the 12-node graph with no intent. The intent and the lens arrive with G1022's `zzzops/policy/lenses` branch. If G1029 merges first, that branch copies the updated prompt. If it merges later, the root adds the paragraph to that branch, or to a follow-up policy branch.

## Risks

- **False alarms at capture.** A rigid reading would flag every goal. The step says "pulls against", tells the agent to say nothing when nothing conflicts, and requires a quoted sentence. The table shows the intended threshold.
- **Missed departures.** The capture check is cheap and done by one agent. It is a first filter: the independent Intent lens at design time remains the guard (G1022 D6).
- **Pausing the portfolio.** Pushing an intent branch pauses all new work. The skill says so before the owner chooses option 2, and the existing "warn before ending a session with a policy branch open" rule still applies.
- **An agent writes the paragraph itself** (F1). A paragraph without the owner's dated words is ignored by the lens (D3). A paragraph with them always reaches a human approval that shows it (D4, D5). A fabricated quote is the remaining risk. It is the same trust the engine already places in `decided_by` and `quote` on every human record, and approval exposes it to the owner.
- **The label drifts** between the skill, the lens and the approval prompt: test 2 catches it.
- **The owner's words.** The skill drafts, and the owner's text is what lands. This is the bootstrap rule, restated in the skill.

## Out of scope

- Engine output or state for intent at capture, including `new` printing the intent or an `intent_note` field (D1, D2).
- The Intent lens's other questions, and G1026's owner-question mechanics.
- Landing an intent for this repository; that is G1022's policy branch.
- Re-checking open goals when the intent changes. The existing staleness of intent nodes already does this.
