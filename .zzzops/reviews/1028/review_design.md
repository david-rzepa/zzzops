# G1028 review_design (attempt 1)

**Verdict: changes requested, on two findings.** The design fixes all four spec items with small, well-placed changes:
- the carry rule is a frontier rule over records that already exist, so it fixes dogfood 29 and 47 without new state;
- closed ids move to `previous.resolved`, and restating them is accepted or refused clearly;
- `follows` preserves the dispute count;
- `--repo` is a global flag on worker commands.

Its claims about the code hold at `read_dev` 8d8437a. Two choices need changing:
1. `follows` is rolled out with an `engine.min` raise instead of a G1027 capability.
2. `follows` inherits `upheld`, which lets a reviewer put new text beyond dispute.

Neither is an owner question, because each has a clear fix.

## Claims checked at read_dev 8d8437a

- **Liveness.** In `frontier.frontier` pass 1 (frontier.py:157-189), a carrier is fresh when its recorded inputs still fingerprint to `input_fp`, and `if not fresh[c] and t != c: continue` (line 182) drops the findings of a stale carrier. That is the dogfood 29/47 cause. Liveness already requires `target_fp == out_fp(target)`, so carrying on an unchanged target is sound.
  - Serialization holds. A carried finding targets an ancestor of its carrier, and while that ancestor is `ready` it is not in `cur`. So the stale review stays blocked (`subject_not_current` or a missing input) until the target has answered. No parallel wasted review run.
  - A human carrier (a `changes_requested` approve item) is carried too, which is right. `escalates` already exempts human carriers.
- **Filter join.** Today `verdicts is False → continue` (lines 174-176) runs before the freshness check. So a lens finding needs a fresh filter, and a spec edit (which also stales `filter_design` through its `spec` input) drops it. The design's lens rule ("the filter's latest done record, fresh or not") has to restructure that branch for stale carriers only. A fresh lens waiting on a stale filter must keep waiting: that is the normal round join. §3.1 says this, and test 6 covers it.
- **Op findings.** They are rebuilt with fixed ids (`records.op_findings`, records.py:154). D2 is sound.
- **Plumbing.** `frontier` has exactly two callers (frontier.py:419 and :533), and `card._carrier` exists (card.py:218).
- **Prior statuses.**
  - `process_findings` (records.py:80-95): `prior` holds only the open findings with `target != X`, so `unknown = set(status) - prior_ids` refuses a resolved id.
  - `card.previous` (card.py:295-306) lists every finding of the latest record, with status but no flag. This is dogfood 46 as described.
  - Resolved priors are copied into the new record, so the latest record holds exactly one round. The §3.2 bound claim holds.
- **Keep-open arithmetic** (records.py:91-95): `rounds + (1 if disputed and the target is an agent)`, with `upheld` copied. §3.3's `rounds` inheritance matches.
- **`--repo`.**
  - `GLOBAL` (cli.py:82) is merged into every verb's `Args`, so a trailing `--repo X` parses.
  - `Session.__init__(cwd=…)` → `Git.discover(cwd or os.getcwd())` (session.py:62-64).
  - Every worker-facing command goes through `render.command` (card.py:186-191 and render.py:72-79).
  - Cards are rendered and not stored, so the absolute primary path never enters a record or ref.

## Findings

### F1 (material, target `design`): ship `follows` as a G1027 capability, not an `engine.min` raise

§6 says that after merge "the plugin copy used by workers and `engine.min` are raised together (… as G1022 D9 does for `lens`)". G1027 (design revision 2, blob 0c556c2, approved) removes `ENGINE_VERSION` and `engine.min`, replacing them with declared capabilities: `engine/capabilities/<name>.txt` plus POLICY `settings.engine.requires`. Its §3.6 rule ("what ships with a new capability") lists "record or finding keys" explicitly. It has already rewritten G1022's rollout to capability `lenses`.

A stored `follows` is exactly such a key: an engine without it reads the goal as invalid. The `engine.min` route therefore conflicts with an approved design. It would also leave this goal with a version number that no longer exists if G1027 merges first. The §6 claim "until then nobody writes `follows`, because only the new engine accepts it in submit" is not a guard either. A worker on the new build would write it while another clone, or the root, still runs an old build.

**Fix:**
- Name a capability (for example `finding_follows`, described as "finding key `follows` on review findings (G1028)").
- Ship `engine/capabilities/<name>.txt` in this PR, and add it to G1027 test 6's pinned `SHIPPED` set if G1027 is merged.
- Change §6 and the §4 row to: the rollout pushes a `zzzops/policy/requires-<name>` branch before the first `follows` is written.
- State both merge orders, as G1027 §5 does for G1022. If this PR merges before G1027, G1027 adds the name to its `LEGACY_VERSIONS` map, or this PR carries a one-line "next minor" note.
- Remove "No goal-schema bump … the same way" only if it implies `engine.min`. Otherwise keep it.
- Update the SPEC §4.5 and §9 contract-edit list accordingly.

### F2 (material, target `design`): `follows` must not inherit `upheld`

`upheld` records that the **human** sided with the reviewer on that finding's text. After that, the target may not dispute it (`check_responses`, records.py:74-75), and it never escalates (`escalates`, frontier.py:302).

§3.3 copies `upheld` onto a new finding whose text the reviewer writes freely. Any reviewer could then attach new demands, beyond what the human upheld, by "following" an upheld finding, and the target could neither dispute them nor reach the human. That weakens the dispute safeguard. The design's own aim, that resolve-and-follow cannot dodge escalation, needs only `rounds`.

**Fix:**
- Inherit `rounds` as designed, and set `upheld: false` on every new finding. A dispute of it then escalates at rounds ≥ 2, so the human sees the new text.
- Add a test: follow an upheld finding; the new finding is disputable, and its next dispute escalates.
- Update §3.3, D5 and test 9 to match.

## Owner questions: none

Applying rule 4's reach-outside test:
- **`follows`** is a stored key. But it is additive, with a clear winner over a `partly` status (which would need its own liveness, filter and escalation rules), and its rollout path is fixed by G1027.
- **`--repo`** is a CLI name others consume. It clearly dominates the alternatives for the reasons in §3.4: shells that reset their directory, a lease that is unreachable from outside the repository, an invisible environment variable, and a parser that takes only long flags.
- **The carry rule** changes engine behaviour, but in the direction the spec asks for. It beats "waive at edit", because waiving cannot fix dogfood 29, where there was no edit.

## Notes (non-blocking)

- **The `carried_findings` preview** lists only findings that were live from a fresh carrier before the edit. A second edit made while findings are already carried, or a material lens finding that becomes carried before its filter ran, would then be live without being listed. Listing every finding that is live after the edit only because it is carried is simpler, and gives the root the complete waive list.
- **The G1026 flag in §8** (a stale input outranks `retry`, so `answer` is hidden) is a real interaction. It is right to hand it to G1026.
