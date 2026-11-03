# Engine design and specification

The ZzzOps engine's contract and its rationale. Revision 6.3 was approved on 2026-10-31 and implemented in #740. Later changes are amendments, listed in [HISTORY.md](HISTORY.md#4-amendments-after-approval).

| Document | Normative for | Use it to |
|---|---|---|
| [SPEC.md](SPEC.md) | **The contract**: exact names, formats, algorithms, the CLI, outputs and exit codes, and the default data files. | Implement or check behaviour. |
| [DESIGN.md](DESIGN.md) | **The rationale**: what was decided and why. It wins on *what* was decided; SPEC wins on exact names, formats and algorithms that DESIGN does not state. A disagreement between the two is a bug to report. | Understand or change a decision. |
| [HISTORY.md](HISTORY.md) | A record, not contract: the revisions, the review sources, the amendment-id index and the amendments since approval. | Look up `REV6 H23` or what changed since 6.3. |
| [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) | A record, not contract: the completed plan that built the reset. Its §3 deviation log lists where the engine knowingly differs from SPEC. | Trace a `Step N` citation or a known deviation. |

## How to cite

Engine code, tests, prompts and goals cite these documents by section: `DESIGN §3.15`, `SPEC §4.14`, `DESIGN §10 item 2`, `REV6 H23` (an amendment id, resolved in HISTORY §3), and `Step 7` (a plan step). Section numbers are stable: amendments add text inside existing sections and never renumber them.

## How to amend

A goal that changes the contract (a CLI verb, flag or exit code; `next`, `validate`, card or approval-item content; a schema; the template graph or prompt set; an engine algorithm; an operation; a bootstrap or policy step) edits SPEC.md and, where the rationale changes, DESIGN.md in its own PR, and adds one row to [HISTORY.md §4](HISTORY.md#4-amendments-after-approval). Reviewers check the edit against the code in the same PR.

## Pending amendments

Goals that will change the contract and have not landed yet. Every goal listed here depends on G1017, so its PR is built on these documents. Its PR applies its amendments, adds its HISTORY §4 row, and deletes its row here. The **Landed when** marker is a repository path, `contains` or `lacks`, and a quoted string. The path may be a file or a directory; a directory matches when any tracked file under it does (`contains`), or none does (`lacks`).

| Goal | Sections | Landed when |
|---|---|---|
| G1024 default-policy update notices | SPEC §2.3, §3.2, §3.15, §3.16, §8.3, §9; DESIGN §3.10 | `plugins/zzzops/zzzops/engine contains "policy_update"` |

Other goals that depend on G1017 need no row: G1026 (its approved design applies its amendment in its own PR without a row), G1029, G1032 and G1034 (skill, prompt or documentation changes only), and G1033 (a package check and hint; its design changes no contract).

**The guard.** `.agents/test_design_docs.py::test_no_landed_goal_is_pending` fails while a row's marker matches the tree: the goal's code has landed but its amendment has not. Because every listed goal depends on G1017, the first tree that holds both a goal's code and its row is that goal's own PR, so the guard trips there and nowhere else.

**Repair.** If `test_no_landed_goal_is_pending` fails on the integration branch (for example after a hand merge, or after an `edit` removed a dependency), open one PR that applies the named goal's amendments to these documents, adds its HISTORY §4 row and deletes its pending row. Do not delete the row alone: the documents would then describe an engine that no longer exists.
