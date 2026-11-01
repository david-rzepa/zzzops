# G1017 design: bring the engine design and spec into the repository

## Outcome

`docs/design/` in the repository holds the engine contract. It contains a scrubbed copy of the approved revision 6.3 DESIGN.md and SPEC.md, the completed implementation plan kept as a historical record, a short HISTORY.md that summarises the review history, and a README that says which document is normative for what. A card's `read_dev` can show them (`git show <commit>:docs/design/SPEC.md`), G1002 can cite them, and design goals such as G1000 and G1015 can amend them in their own PRs. Nothing new ships in the plugin.

This is a docs-only change: four files move, one file is new, and about six lines change elsewhere.

## What was found at read_dev (54d7e83)

- `git grep 'zzzops-design-reset\|DESIGN.md\|SPEC.md'` finds four hits, none of them a path to the external folder:
  - `plugins/zzzops/zzzops/zzzops.py:2` (`DESIGN.md §3.15, SPEC.md §6`)
  - `plugins/zzzops/zzzops/engine/__init__.py:1` (`DESIGN.md, SPEC.md`)
  - `docs/MAINTAINING.md:9` ("designed in the reset's DESIGN.md and SPEC.md")
  - `.agents/engine_fake_gh.py:1`, and `.agents/engine_fixtures.py:1` (`IMPLEMENTATION_PLAN §1.2`)
- About 60 more citations use only a section name: `DESIGN §10 item N`, `SPEC §4.14`, `REV6 H23`, `DESIGN C4`, and the `Step N` docstrings in `.agents/test_engine_*.py` (which name plan steps). They are spread over 23 engine modules and 20 test files. These stay valid as long as the section numbering is preserved, so they do not change. One sentence in MAINTAINING.md says where they resolve.
- No skill, prompt, rule, reference or template under `plugins/` cites the design documents. The external folder is cited by path only *inside* the source documents themselves:
  - DESIGN: 18 lines cite `reviews/`, `passes/` and `audit/`.
  - SPEC: 11 lines.
  - IMPLEMENTATION_PLAN: 10 lines, plus 20 absolute paths under `/home/<user>/Work/dev/…` in §0.1, §0.3, §0.4, step 0 and §5.
- `--policy-ref` (#742) is on dev and in `CLI_USAGE.md`, but it is not in DESIGN or SPEC.
- G1000, G1001, G1014, G1015 and G1016 are all open, with their design or review phases still running. None of them has merged.
- Private data in the sources:
  - absolute local paths (all in the plan);
  - the owner's personal name in examples (`"decided_by": "David Rzepa"`, `"agreed with David …"` in DESIGN §3/§4 and SPEC §3.3/§3.4/§3.12);
  - example holder labels with hex session prefixes (`claude:7f3e9a10/design-1`, `claude:9c1d/implement-1`, `claude:c90b/…`, `codex:77e0/…`). They look synthetic, but this cannot be proven, so all of them are treated as session names.
  - `david-rzepa/zzzops` is the public repository slug. It is already in tracked files, so it is kept.
- `.agents/concept_inventory.py` scans `docs/**/*.md`, and `test_concepts` requires zero occurrences of "reversible" and "revertible". The three sources contain neither word, so adding them does not break the test. `prompt_stats.py` reads only `AGENTS.md`, rules, skills, references and prompts, so its budgets are unaffected.

## Approach

### Target layout

| Path | Source | Content |
|---|---|---|
| `docs/design/README.md` | new, about 40 lines | Normativity, how to cite, how to amend, and the pending amendments list. |
| `docs/design/DESIGN.md` | `DESIGN.md` rev 6.3 | Unchanged except for the scrub, the status line, and the revision-history block moved to HISTORY.md. |
| `docs/design/SPEC.md` | `SPEC.md` rev 6.3 | Unchanged except for the scrub, the status line, the "Sources" bullet rewritten, and the `--policy-ref` amendment. |
| `docs/design/IMPLEMENTATION_PLAN.md` | `IMPLEMENTATION_PLAN.md` | Kept as a historical record. It is the target of the `Step N` and `IMPLEMENTATION_PLAN §1.2` test citations, and its §3 deviation log records where the engine knowingly differs from SPEC. It is scrubbed as described below. |
| `docs/design/HISTORY.md` | new, written from `reviews/`, `passes/` and `audit/` | The review history, summarised (next section). |

`docs/design/` was chosen over `docs/` because there are five files plus a README. It keeps the contract separate from the user docs, and the README works as the folder's index on GitHub.

### What stays outside

These stay in the external folder and are not copied: `reviews/` (R0–R9, REV5_CHANGES.md, REV6_CHANGES.md), `passes/` (review2 prototype and walkthrough, review3–5 reports, and the review-5 Python model), `audit/` (A–G), and `DESIGN.html` and `SPEC.html`, which are generated renders that GitHub replaces.

Reasons:
- They total about 1 MB of superseded working material.
- The amendments they produced are already folded into rev 6.3.
- The review-5 model is code that nothing imports, and the plan already said never to import it.
- The reports quote session-era paths and are expensive to scrub.

If anyone later needs a report, it can be added under `docs/design/reviews/` by its own goal.

### How review history is summarised (HISTORY.md, about 150–200 lines)

1. **Revisions.** The "Revision history" block from the top of DESIGN.md (revisions 1 to 6.3) moves here, with its path citations rewritten. DESIGN.md keeps a single line pointing to it.
2. **Review sources.** One line each for every source the documents cite, using the short tags they already use:
   - `R0`–`R9`: the review reports;
   - `audit A`–`G`: the seven audit reports;
   - pass 2: prototype and walkthrough;
   - pass 3: consistency, evolution, generality, harness-platform, human-economics and model-check;
   - `x`, `x2` and `m4`: the review-4 cross-checks and model check;
   - `m5`: the review-5 model check.

   Each line gives the scope and the headline result. A header line says that the reports themselves are not in the repository.
3. **Amendment index.** This makes every cited amendment id resolvable:
   - REV5 A1–A4, with its B–E sections in one line each;
   - REV6 A1–A6, with B–E summarised by theme;
   - REV6 H1–H30, one line each (title plus one clause). The REV6 change list is 32 KB, so this is an index, not a copy.
4. **Amendments after approval.** Each in-repo change to the contract gets one row: goal, PR, sections touched and a one-line summary. The first row is `--policy-ref` (#742, applied by G1017). The next is G1017 itself ("moved into the repository; scrubbed; no semantic change").

Rule for future amendments: a goal that changes the contract edits DESIGN/SPEC in its own PR and adds one row to §4. The documents keep the revision label "6.3" plus this amendment list. No new revision number is invented for in-repo amendments.

### Reference rewriting inside the moved documents

| Found | Becomes |
|---|---|
| `reviews/REV6_CHANGES.md` (optionally with an id) | `[HISTORY](HISTORY.md#amendment-index)`, REV6 *id* |
| `reviews/REV5_CHANGES.md` | the same, for REV5 |
| `reviews/R<n>-….md`, `review<n>/…`, `passes/…`, `audit/<X>…` | The prose tag only (for example "review R5 §B", "audit report E", "the review-5 model"), without a path. HISTORY lists each tag. |
| SPEC's "Sources" bullet | One sentence: "Sources: the reviews and passes summarised in HISTORY.md." |
| `IMPLEMENTATION_PLAN.md`, `DESIGN.md`, `SPEC.md` named in each other | Relative links within `docs/design/`. |
| `.zzzops/reviews/1002/design.md` (an example artifact path) | Unchanged. It is engine data, not a reference to the folder. |

Citations like `R1 A3` and `x:C1` stay as they are. They are tags, not paths.

### Privacy scrub

1. **Absolute paths.** All of them are in IMPLEMENTATION_PLAN:
   - §0.1: the path list becomes the three relative links.
   - §0.3 "Where to work": becomes one sentence ("Done on branch `reset/engine-v2` from `dev` at `64d5196`; landed as #740.").
   - §0.4 and step 0: "the owner's other worktrees" replaces named paths.
   - §5 "Prompt for the implementing model": replaced by two sentences saying that the session was started from the plan, and that its rules are §0.4 and §0.6.
   - DESIGN and SPEC keep `~/.codex/rules/zzzops.rules`, which is a generic per-user install path.
2. **Personal names in examples.** `"David Rzepa"` becomes `"A. Owner"`, and "agreed with David" becomes "agreed with the owner".
3. **Session names.** Every example holder label is replaced from one fixed synthetic map, keeping the agent prefix and the hex length so the examples still match SPEC §1.7's format:
   - `7f3e9a10` → `0a0a0a01`
   - `9c1d4e7a` → `0a0a0a02`
   - `9c1d` → `0a01`
   - `c90b` → `0a02`
   - `77e0` → `0a03`

   Labels that repeat within one worked example stay the same as each other.
4. **Status lines** are rewritten:
   - DESIGN: "Revision 6.3, approved 2026-10-31 and implemented in #740. Amendments since then: HISTORY.md §4."
   - SPEC: the same.
   - Plan: "Completed 2026-10-31; a historical record. DESIGN and SPEC win."

   "Awaiting approval" and "nothing here authorizes source changes" no longer apply.
5. **Gate.** The implementation must show that this is empty:

   ```
   git grep -nE '/home/|/Users/|/tmp/|zzzops-design-reset|Rzepa|\bDavid\b|claude-1000' -- docs/design
   ```

   The repository slug `david-rzepa/` is allowed. The same grep, run without the slug exception over `plugins/`, `.agents/`, `README.md` and `AGENTS.md`, must show no `zzzops-design-reset`.

### Contract amendments from parallel goals

The rule: at G1017's `implement` time, the implementer runs `zzzops show <g>` for G1000, G1001, G1014, G1015 and G1016.

- **Merged to dev before `base`/`implement`.** The implementer applies that goal's contract change to DESIGN/SPEC, reading it from its merged diff and its approved design artifact (`.zzzops/reviews/<g>/design.md`), and adds a row to HISTORY §4.
- **Not merged.** The goal goes in the README's **Pending amendments** table (goal, affected sections, one line), and its own PR edits `docs/design/` once G1017 has merged.

G1017 never applies text from an unmerged design: that text is not yet approved or merged.

Expected sections. These are the implementer's starting points, to confirm against each goal's design.

| Goal | Change | Sections |
|---|---|---|
| G1000 | Parallel review lenses in the default graph | DESIGN §4.1, §10; SPEC §7 (default `workflow.json`), §8 prompts |
| G1001 | Idempotent `new` | SPEC §4.17, §3.13; DESIGN §3.15 |
| G1014 | `edit` warns when it changes a running phase's inputs | SPEC §4.19, §3.16 |
| G1015 | Legacy-installation detection | DESIGN §3.15 and §10 (the amendment its spec names); SPEC §4.1, §3.16 (`validate`) |
| G1016 | Card and lease-verb explanations | SPEC §3.14, §3.16, §6 |

At read_dev, all five are open, so the expected result is that all five are listed as pending.

Coordination note for the parallel goals: G1000 and G1015 should target `docs/design/` and not the external folder. If either reaches `implement` before G1017 merges, it can either depend on G1017 or leave its contract text in its design artifact, so that G1017's implement (or a follow-up) applies it. G1002 already depends on G1017.

**`--policy-ref` (on dev, applied now):**
- SPEC §6: the flag on `next`, `show` and `validate`. It is read-only, takes a ref or commit, refuses mutating verbs, and refuses `validate --policy` with it. Wording comes from `CLI_USAGE.md` and `engine/cli.py` at dev.
- SPEC §3.15 and §3.16: any output field it adds.
- DESIGN §3.15: one line on the verb surface.
- HISTORY §4: one row.

### Other in-repo changes

- **Root `README.md`, "What to read next":** one bullet, "[Design and specification](docs/design/README.md) — the engine contract (SPEC) and its rationale (DESIGN)."
- **`docs/design/README.md`:** the short normativity section.
  - SPEC is the contract: exact names, formats, algorithms and CLI.
  - DESIGN is the rationale and the record of decisions; it wins on *what* was decided (its existing precedence rule, restated).
  - IMPLEMENTATION_PLAN and HISTORY are records, not contract.
  - The plan's §3 deviations are known divergences between the engine and SPEC.
  - How to cite: `DESIGN §x`, `SPEC §x`, `REV6 H<n>`.
  - How to amend: edit in the goal's PR and add a HISTORY §4 row.
- **`docs/MAINTAINING.md:9`:** link `design/DESIGN.md` and `design/SPEC.md`, and add one sentence saying that the `DESIGN §`, `SPEC §`, `REV6 H<n>` and `Step <n>` citations in engine code and tests resolve to `docs/design/`.
- **`zzzops.py:2` and `engine/__init__.py:1`:** change the bare file names to `docs/design/DESIGN.md` and `docs/design/SPEC.md`. These are two docstring lines and the only shipped change. They give a reader of the installed plugin the repository location. They change the package digest, as any engine edit does, but not the version or the behaviour.
- **`.agents/engine_fake_gh.py:1` and `engine_fixtures.py:1`:** no change. `IMPLEMENTATION_PLAN §1.2` stays valid because the plan moves with its numbering intact.

### Does anything ship in the plugin?

No. `docs/` is outside `plugins/zzzops`, so nothing new is bundled, and the prompt budgets are unchanged. The only shipped bytes that change are the two docstrings above.

## Alternatives rejected

- **Copy `reviews/` and `passes/` verbatim.** This adds about 1 MB of superseded material, needs a large scrub, and the brief asks for a summary instead.
- **Leave IMPLEMENTATION_PLAN outside.** About 20 test docstrings cite plan steps, and its deviation log is the only record of where the engine knowingly differs from SPEC. Leaving it out would break those citations or force the log into SPEC.
- **Fold the deviation log into SPEC** so that SPEC is exact. This is a semantic edit to the contract and is out of scope for a move. It is a reasonable follow-up goal.
- **Put the documents under `plugins/zzzops/zzzops/references/` so they ship.** This adds about 470 KB to every install and counts toward the package. Workers already reach the documents through `read_dev`.
- **Rewrite every `DESIGN §`/`SPEC §` citation as a path.** That means about 60 edits across engine and tests for no gain, since one sentence in MAINTAINING resolves them all.
- **Apply text from unmerged parallel designs.** That text is not yet approved or merged and could diverge; listing it as pending is safe.
- **Leave the HTML renders in.** They duplicate the Markdown, and GitHub renders Markdown.

## Risks

- **Section numbering drift.** The engine and tests cite section numbers, so the move must keep every heading number. The diff check below covers this.
- **Merge conflicts with G1000 and G1015.** Both will touch the same sections. Whichever merges second rebases. The README's pending table and the HISTORY §4 rule make the expected edits explicit.
- **Missed private data.** Grepping for the named patterns is mechanical. A manual read of the plan's §0 and §5, the only dense areas, backs it up.
- **The concept inventory changes** because the new docs add occurrences to `docs/`. `test_concepts` asserts only that counts are positive and that "reversible"/"revertible" have zero occurrences. The sources contain neither word, but the gate re-checks after the edits.
- **The package digest** changes because of the two docstrings. This is accepted; if the owner prefers zero plugin churn, those two lines can be dropped without affecting anything else.

## Testing

A new `.agents/test_design_docs.py`, standard library only and under 1 s, with three tests:
1. `git ls-files` content under `plugins/`, `.agents/`, `docs/`, `README.md` and `AGENTS.md` contains no `zzzops-design-reset`. Under `docs/design/` it also contains no `/home/`, `/Users/` or `/tmp/` paths. The patterns are built by concatenation so that the test does not match itself.
2. Every relative Markdown link in `docs/design/*.md`, and the new links in `README.md` and `MAINTAINING.md`, resolves to an existing file.
3. Every amendment id cited in DESIGN.md or SPEC.md (the pattern `REV[56] [A-H]\d+` and the `H\d+` ids in REV6 contexts) has an entry in HISTORY.md.

Implement-time checks, recorded in the PR:
- **Headings unchanged:** `diff <(grep -E '^#{1,4} ' <src>) <(grep -E '^#{1,4} ' docs/design/<file>)` shows only the status and revision-history lines changing in DESIGN, the added `--policy-ref` content in SPEC, and the scrubbed plan §0.3/§5.
- **Small body diff:** the body diff against the external sources is limited to the scrub table, the status lines and the amendments.
- **Gates:** the privacy grep is empty, `python3 .agents/prompt_stats.py` budgets are unchanged, and the full `python3 -m unittest discover -s .agents -p 'test_*.py'` passes.
- **Rendering:** the documents render on GitHub (checked on the PR's file view), and `git show <dev>:docs/design/SPEC.md` works after the merge.

## Out of scope

- Any semantic change to the contract other than `--policy-ref` and the amendments of merged goals.
- Reconciling SPEC with the plan's deviation log (a possible follow-up).
- Copying review reports.
- Changing the `§` citations in engine and tests.
- Editing goal specs on state branches that cite the external path: they are historical records.
- The whitepaper (G1002).
- Deleting the external folder, which is the owner's decision.

## Decisions taken (owner has delegated approvals)

1. The path is `docs/design/`.
2. IMPLEMENTATION_PLAN moves too, as a scrubbed historical record.
3. Reviews, passes, audit and the HTML renders stay outside; HISTORY.md summarises them and indexes every cited amendment id.
4. Example holder labels and the owner's name are replaced with synthetic values; the public repository slug is kept.
5. Parallel-goal amendments: apply them if merged by implement time, otherwise list them as pending. Unmerged design text is never applied.
6. Nothing new ships; only two docstrings in shipped files change, to the in-repo path.
