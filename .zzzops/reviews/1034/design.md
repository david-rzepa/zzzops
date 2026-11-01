# G1034 design: migration assigns each migrated goal a release

Attempt 1. Written against read_dev 8d8437a. G1017's design (revision 3) is the base for the docs/design rule.

## Outcome

When a repository is migrated, every goal created from an old issue carries a release that the owner confirmed. Nothing falls back silently to `settings.releases.current`.
- The triage proposal gains a **release column**. The skill proposes a release for each MIGRATE goal and MERGE group, says why, and the owner confirms or changes it at the one go-ahead.
- **Release order is checked before any goal is created.** A goal may not depend on a goal of a later release. Conflicts appear in the proposal with the ways to fix them, and the apply step never meets them.
- Step 5 passes `release` (and `priority` and `depends_on`) to `new` explicitly, and creates dependencies first.
- MIGRATING.md's "#695, all release 1" line becomes general guidance. The fact it recorded moves to the worked example, where it belongs.

**No engine change.** `new` already accepts `release`, and validation already refuses a dependency on a later release. The work is the skill, MIGRATING, the worked example, one DESIGN §7 line, and tests.

## What was found at read_dev 8d8437a

- **Skill, step 3** reads each issue with `gh issue view <n> --json title,body,state,labels`. The milestone is not read, so a release signal that GitHub holds is never seen.
- **Skill, step 4** has five classes (OBSOLETE, DONE, MIGRATE, MERGE, HUMAN) and no release or priority field. The proposal shows "counts per class, the MIGRATE list with new titles, and the HUMAN questions".
- **Skill, step 5** runs `zzzops new --file <F>` with `links: {"issue": <n>}` only. So `release` defaults to `settings.releases.current` (`cli.py:353`), and `priority` defaults to P2.
- **MIGRATING.md**:
  - line 18 already lists `release` among the fields to pass;
  - line 43 says "Release assignments from the old release-plan issue #695 are all release 1". That is a fact about this repository, not guidance.
- **DESIGN §7 item 3** (rev 6.3, moving to `docs/design/DESIGN.md` with G1017) lists the guide's contents. One bullet is "Release assignments from #695 (all release 1)".
- **The engine already enforces release order**, in three places:
  - `schemas.validate_goal` rule 4 (`schemas.py:783`), run by `new` before it pushes: "G<d> is in release <r>, after this goal's release <r'>". SPEC §3.3 rule 4.
  - `session.dependent_release_errors` for `edit`, and `verbs.py:938` for edits that move a dependency later.
  - Tests:
    - `test_engine_schemas.py:204` covers the rule at the schema level;
    - `test_engine_sync_edit.py:120` covers `edit`;
    - `test_engine_store.py:616` covers a retried `new` after `releases.current` moved.
  - **No test runs it through the `new` CLI**, so nothing pins that a refused `new` writes no goal branch.
- **What a release does today:**
  - it orders work, since release is the second sort key after stage (`frontier.py:545`);
  - it gates only nodes with `release_gate`, which in the default graph is `merge`: "waiting: release N" while N > `releases.current`.
  - A goal of a later release is designed, built and reviewed, and waits only to merge. The owner needs to know this to choose well, so the proposal says it.
- **Release values:** an integer ≥ 1 (`schemas.py:719`), with no names or list of releases. There is no "no release" value. In this repository, the migrated backlog goals G1004–G1013 have release 2, which is the owner's later release. G1013 was the "P3 backlog goal outside the release" in EXAMPLE.md.
- **the private app (G1035's target), read-only `gh issue list`:**
  - 12 open issues, none with a milestone;
  - no release labels;
  - every issue has a `zzzops:priority:P2` or `P3` label;
  - #48 has `zzzops:status:blocked`.
  - So for the private app the proposal comes from priority labels, the body (dependencies, blockers) and the owner's direction. G1035 §5.3 already drafts that proposal. Milestones matter for other repositories.
- **Old engine (64d5196):** release plans lived in a release-plan issue (`releases.py`; here #695), with assignments in comment envelopes. The skill never reads comments. The plan issue's body, if it has one, is a source, and so are milestones and labels.

## Approach

### 1. Skill step 3, inventory: read the milestone

`gh issue view <n> --json title,body,state,labels,milestone`. Comments are still never read. The existing test `assertIn("--json title,body,state,labels", text)` still matches, and it is updated to the new field list.

### 2. Skill step 4, triage: a release per goal

A new paragraph after the five classes. Proposed wording (implement may tighten it):

> **Release, priority and dependencies** for each MIGRATE goal and each MERGE group:
> - **Release:** a whole number, 1 or more. Propose one from, in order:
>   1. the issue's milestone, or a release label;
>   2. the old release-plan issue's body, if the repository had one;
>   3. its dependencies (no earlier than any of them);
>   4. its priority and the owner's direction.
>
>   Map milestone names to numbers once, in one table the owner confirms (for example `v2.0` → 2). Propose releases at or after `settings.releases.current`. A goal planned for no upcoming release goes to the release after the last planned one. There is no "no release".
> - **Priority:** from the `zzzops:priority:P<n>` label, else P2.
> - **Dependencies:** from the body ("depends on #n", "blocked by #n"):
>   - a dependency on a MIGRATE or MERGE issue becomes that goal;
>   - a dependency on a DONE or OBSOLETE issue is dropped;
>   - a dependency on a HUMAN issue waits for the answer;
>   - an existing new-engine goal is used as it is (read its release with `zzzops show <id> --json`).
> - **Check release order now:** no goal may depend on a goal of a later release, and dependencies may not form a cycle. `new` refuses both, so a conflict found at step 5 would leave the migration half applied. List each conflict with its fixes: move the dependent later, move the dependency earlier, or drop the dependency. The owner picks one.

The proposal line changes to: the counts per class; the MIGRATE list with new titles, **release, priority and dependencies**; the milestone mapping, if any; the release-order conflicts; and the HUMAN questions. Add one sentence the owner reads: "A goal of a later release is still designed and built; it waits only to merge, until that release is current." The go-ahead confirms each goal's release.

Batch workers (EXAMPLE.md's method) add `release`, `release_why` and `depends_on_issues` to their JSON line. Root merges the batches and runs the order check over the whole set. The check needs every goal, so a batch cannot do it alone.

### 3. Skill step 5, apply: explicit fields, dependencies first

> MIGRATE: create goals in dependency order (each goal after the goals it depends on), so that `depends_on` can name their new ids. Each file passes `release`, `priority`, `depends_on` and `links: {"issue": <n>}` explicitly. If `new` refuses anyway, stop and show the user; the goals already created are correct, and the rest resume after the triage row is fixed. To change a release later, use `zzzops edit <id> --set release=<n>`, which checks the goal's dependencies and dependents.

A rerun of the same `new` stays safe (G1001). If the owner changes a release between a failed and a resumed apply, a rerun of an already created goal is refused ("request_key … already created G<id> with different contents: release"). That is the right outcome: it says to use `edit`.

### 4. MIGRATING.md

- Line 18: unchanged. It already lists `release`. Add "(confirmed by the owner at triage; see the skill)".
- Line 43: replace the #695 sentence with general guidance:

  > Each migrated goal takes the release the owner confirmed at triage (the skill's step 4: from the old milestone, labels or release plan, its dependencies and priority). Releases are whole numbers; a goal waits only at its `merge` while its release is after `settings.releases.current`. A goal may not depend on a goal of a later release.

### 5. EXAMPLE.md

It is a dated record of this repository's migration, so it gets one line under "Owner decisions": "Releases: from the release-plan issue #695. The next release's goals became release 1, and the backlog became release 2 (G1004–G1013)." The worker output line already lists the fields used then (`mvp`, `priority`). It is history, so it is not rewritten.

### 6. docs/design

By G1017's behavioural test, this goal **does not change the contract**: no verb, flag, output, schema, algorithm or op changes. The skill and MIGRATING are not under SPEC §8. But DESIGN §7 item 3's bullet "Release assignments from #695 (all release 1)" describes the guide, and it would become wrong. So the PR:
- edits `docs/design/DESIGN.md` §7 item 3: the bullet becomes "**Release assignments:** proposed per goal at triage and confirmed by the owner; release order is checked before any goal is created";
- adds a HISTORY §4 row: `G1034 | #<pr> | DESIGN §7 | migration assigns each goal an owner-confirmed release (skill and MIGRATING; no engine change)`.

G1034 already has `depends_on: [1017]` (G1017 case 3), so its base contains `docs/design/`. It needs no pending row, because its sections were unknown when G1017's inventory was taken and it changes no contract section.

## Alternatives rejected

- **`new --check` (a dry run).** It validates one file against goals that exist. A migration's dependencies point at goals that do not exist yet, so a dry run cannot check the batch. That is the case the spec cares about.
- **A batch verb (`new --plan F` with local keys for unborn goals, all-or-nothing).** It would give a real pre-check and atomic apply, but it adds a new CLI surface, a schema, multi-ref atomic creation and SPEC §3.13/§4.17 changes. It would be built for a step that runs once per repository and has about 12 to 30 goals. The order check is simple arithmetic over a table the owner reads anyway. `new` stays the backstop, so a mistake costs a stopped apply, not a wrong goal. This is the "keep the engine change minimal" call. If G1035 shows the manual check failing, a follow-up goal can add the verb.
- **Make `release` required in `new` files.** That would break the add-goal skill and every scripted `new`. It would change SPEC §3.13 for every user to fix one skill. Passing it explicitly is enough.
- **A helper script in `scripts/`** to check the triage JSON. A shipped file needs packaging, digest entries and tests, all for a check the root can do over one table. Rejected for now, with the same follow-up path as the batch verb.
- **Infer releases with no owner confirmation.** The owner's instruction is that releases are assigned as part of the migration, and the old signals are often missing (the private app has none). A proposal plus confirmation fits the skill's one go-ahead.

## Interfaces and data that change

| Item | Change |
|---|---|
| `skills/migrate-zzzops-repository/SKILL.md` | step 3 field list (`milestone`); step 4 release, priority and dependency paragraph, and the order check; proposal contents; step 5 explicit fields, dependency order and stop-on-refusal |
| `references/MIGRATING.md` | lines 18 and 43 |
| `skills/migrate-zzzops-repository/references/EXAMPLE.md` | one owner-decision line |
| `docs/design/DESIGN.md` §7, `docs/design/HISTORY.md` §4 | one bullet, one row |
| Engine, CLI output, schemas, policy, goal documents | none |

The skill grows by about 1.2 KB, to about 6.3 KB. The migrate skill is a cold path outside `prompt_stats`' enforced budgets (`capture`, `execution`, `always-loaded`), so no budget moves.

## Coordination

- **G1035 (the private app dogfood)** depends on this. Its §5.3 draft table (Issue, Class, Release, Why) is the shape this design gives every migration. Its D-rel defect (§8.1) is this goal.
- **G1025 (release branching):**
  - once release lines exist, a goal's release also chooses its target branch: an open `release/N` for release N, else the integration branch. `new` then defaults to the *effective* release, not `releases.current` (G1025 D11).
  - Because step 5 passes `release` explicitly, migration does not depend on either default.
  - The only overlap is one skill sentence: "Propose releases at or after `settings.releases.current`." **Handoff for the root to send to G1025:** "G1034 adds to migrate-zzzops-repository step 4: 'Propose releases at or after `settings.releases.current`.' When G1025 lands, amend it to the effective release, and add that a release with an open line targets `release/N`, while a finished release is not assigned (`new` warns `release_finished`)."
  - No dependency either way. The two goals touch different lines of different files, except this one sentence, which G1025's PR edits if G1034 merged first. If G1025 merges first, G1034's implement uses G1025's wording, since its `base` contains it.
  - In a fresh migration (the private app) no line exists yet, so the question does not come up there.
- **G1029 (intent check at capture):** migration also creates goals with `new`, so G1029 may want its intent check on each MIGRATE goal. That is G1029's scope. This design adds no intent column. If G1029 extends the check to migration, it adds its column next to release in step 4 and its option to the go-ahead. The two goals edit different paragraphs of SKILL.md, so a conflict there resolves at `base`. No dependency is needed.
- **G1017:** already a dependency (case 3). This design follows its rule (§6 above).

## Risks

- **Manual order check missed.** `new` refuses the conflicting goal, and the apply stops with the earlier goals created. Recovery is the skill's resume instruction, plus `edit --set release=`. The new CLI-level test pins that a refused `new` leaves no goal branch.
- **Owner fatigue on long backlogs.** One release per row across 100+ issues is a lot to read. The proposal groups MIGRATE rows by release, so the owner confirms groups and changes exceptions.
- **Milestone names that are not ordered numbers** (`MVP`, `Q3`). The one confirmed mapping table makes the choice explicit.
- **The release meaning changes under G1025.** The coordination handoff covers it. Until then, the proposal's sentence about the merge gate is accurate.

## Testing

1. **Skill text test** (`.agents/test_engine_legacy.py`, `PackageTests`), `test_skill_assigns_a_release_per_goal`. It checks that SKILL.md contains:
   - `--json title,body,state,labels,milestone`;
   - a step 4 paragraph naming the release, its confirmation by the owner, and the rule "may not depend on a goal of a later release";
   - step 5 passing `release` and creating dependencies first.

   It also checks that MIGRATING.md no longer contains `#695` and does contain "later release". The existing `--json` assertion is updated to the new field list.
2. **CLI-level backstop test** (`.agents/test_engine_store.py`, next to the G1001 `new` tests):
   - `new` with `"release": 2` stores and outputs release 2;
   - `new` with `"release": 1, "depends_on": [<the release-2 goal>]` is refused with `validation`, naming "release 2";
   - no new `zzzops/goal/g*` ref exists afterwards.

   This pins the behaviour the skill relies on. No engine code changes.
3. **docs:** G1017's `test_design_docs.py` (links resolve; no landed goal pending) runs on the PR unchanged.
4. `prompt_stats` runs unchanged. The migrate skill is not budgeted, and no signal is added: the skill test is more precise than a `WORKFLOW_SIGNALS` entry, and migrate is not a budgeted workflow.

## Out of scope

- A batch or dry-run creation verb, and any change to `new`, `validate` or schemas.
- Release names, release lists in policy, and raising `releases.current` (a policy branch, as today).
- Release lines, targets and the effective release (G1025).
- The intent check on migrated goals (G1029).
- Running the the private app migration (G1035).
- Re-triaging this repository's already migrated goals.
