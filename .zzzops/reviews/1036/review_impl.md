# G1036 implementation review

Approved. No material findings.

Subject: `580987251909105fb202d84648828e8271abf08c`, compared with `c455b09914b49fd65e169f91a4f79110e3e2540b`; manual checker reviewed at `6417262fa2d0d06afb514ef0e493eca8e2faed51`. Primary behavior claims were checked against the pinned c455 source, not the installed extension. I read only this card's supplied design and context, not other reviews of this subject. No source, workflow or runtime changes were made.

## Compliance pass

The three-file implementation is within the approved documentation scope: reference paper, owner-publication blog draft and neutral README navigation. The paper is organized around state → frontier → next → card → result/review → recomputation. The source/build/date/integration binding, David Rzepa byline, agent disclosure and development-status wording are present. It makes no empirical reliability, savings, completed-dogfood, official-release, deployment or external-publication claim. Omitting the separately bound, unmerged release-summary extension is permitted by the design.

The paper covers the eight states and precedence; snapshot/CAS and bounded creation recovery; semantic versus context selectors; instruction/policy selection; selected artifact/checkpoint/tree identities; prompt/instruction omissions and `rev`; findings, filter joins, held output and disputes; capability-dependent material-round budgets; leases and holder labels; carry, tree checks and sync review; delivery and optional lines; adoption and external authority limits. The synthetic A/B trace explicitly places initial correction before dependency readiness, distinguishes discovery from delivery and states the assumptions. It is labelled a composite, not production evidence. The failure/recovery pairing distinguishes reclaim fencing from process/filesystem isolation, and qualifying carry from refused resolutions.

The main text is shorter than the approximate design target but contains useful coverage and the intended audit boundaries; this is not a reason to block it. The blog meets its role as an accessible shorter introduction. All three small Mermaid diagrams have adjacent equivalent prose and avoid color-dependent meaning. The contents, headings, tables and code examples remain understandable from the Markdown text when Mermaid is unavailable.

## Correctness pass

I traced the principal claims against the actual pinned implementations of `frontier.py`, `fingerprint.py`, `card.py`, `carry.py` and the shipped `workflow.json`. The state precedence agrees with the implementation: skip and live leases precede missing-input classification; missing inputs precede expiry/reclaim; stale inputs, blocked records, corrections, non-ok outputs and human approval then distinguish work. Named dependency waits are distinct from the `waiting` node state and from stuck goals in the paper's walkthrough.

The selector examples match the shipped definitions: `implement` uses design, test change and base semantically, commands and test-review summary as context; `run_tests` selects the actual code tree and commands, plus its declared verification policy. The artifact/blob versus checkpoint/change distinction, selected subfields, semantic definition allowlist, omitted prose/provenance, subject normalization and full target-output fence agree with the fingerprint functions. The explanation does not confuse identity equality with correctness or initial disclosure with access control.

The review, held-output, material-round and carry claims preserve their limits. Carry is per eligible checkpoint, uses scoped deltas and conservative edited-resolution checks, and does not establish semantic safety. The shipped implementation-review base selector explains why review reruns after sync even when change-bound work carries. The paper correctly separates tree checks, approval/expected-head Git operations and deployment.

## Missing pass

I searched the immutable subject for the new paper and disclosure terminology and checked the existing normative/rationale references and default definitions. README navigation and the blog's paper link are consistent. The implementation does not silently modify SPEC to fit the documented size discrepancies or imply that historical fixtures are today's shipped graph. No required sibling runtime, schema, policy or publication change is missing from this documentation-only goal.

## Tests pass

I checked assertions, rather than treating named-reference existence as proof: creation-response recovery observes one durable goal; fingerprint tests assert blob/change identities, context/prose omission and `rev` sensitivity; dependency tests assert premerge discovery and named integration/held waits; review journeys assert the independent fan-in and reopened design; held-output tests keep findings while consumers remain blocked; lifecycle tests reject superseded submission without moving the goal ref; round-budget tests distinguish new material rounds, follow-ups, stage caps and base-only/no-checkpoint exemptions; clean-sync tests retain eligible change identity, rerun tree checks/review and refuse interleaved/dropped resolutions; branching tests inspect target selection and resulting merge refs.

The manual checker intentionally verifies binding integrity and bounded reproductions, not semantic entailment, and says so. Its hidden ledger covers the required families and exact symbols; visible references and prose provide the human audit. I found no defect requiring a change to the frozen checker. The two size exceptions are intentionally documented limitations, not defects to repair in this goal.

I used the card's observed checks evidence: all four commands passed, including 12 focused checks and 1,121 local product checks with zero failures/errors. The new manual audit took 397 ms; its source-only audit took 285 ms; focused checks took 1,639 ms. The existing broader verification took 414,756 ms. Baseline timing is explicitly unavailable because commands/allocation changed, so no speedup or regression is inferred. I did not repeat the full suite or run remote CI; no unresolved claim required a new probe.

## Craft pass

The prose keeps the central mechanism visible while the technical half exposes identity, authority and recovery boundaries. It uses a compact worked sequence and small diagrams instead of reproducing the complete graph or CLI manual. Status, provenance, evidence classification and upkeep remain explicit. Source-level layout inspection found no blocking readability problem; I did not independently produce a browser/PDF rendering. The parent coordinator reports all 43 links and anchors resolve. No material craft issue was found.

## Findings

None.
