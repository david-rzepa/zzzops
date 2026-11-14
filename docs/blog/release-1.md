# A workflow that reveals the next piece of work

**David Rzepa**

Draft for owner publication · 14 November 2026

Drafted and reviewed with AI agents.

Long-running agent work has a handoff problem. A session ends, a review finds a missing requirement, a dependency changes, or a human needs to make a decision. The next participant needs enough context to act, but a transcript of everything that happened is a poor substitute for knowing what matters now.

ZzzOps explores an approach I call **deterministic progressive disclosure**. A declared workflow and durable state select the next eligible work and the initial context for the worker doing it. The worker records a result. Reviews and decisions become state too. Then the workflow recomputes what can happen next and what context belongs in the next handoff.

The idea is simple to draw: state → frontier → next → task card → result or review → recomputed context. The interesting part is the meaning of each arrow. The [working paper](../WHITEPAPER.md) follows the loop through its identity rules, review, recovery and delivery, and gives source and test references so readers can inspect the claims. It describes a checked development snapshot, not an official release announcement.

A **frontier** is the current classification of workflow nodes. One may be ready to run; another may be blocked on an input, waiting for a dependency, running under a lease, or waiting for a human approval. A result is current when it is done, acceptable under the workflow and still matches its declared inputs. This lets a dependent goal start discovery from a reviewed design while later delivery waits for integration. A held dependency that can still produce its output is a named wait, giving a reader a reason to wait instead of presenting it as an unexplained dead end.

“Deterministic” has a precise and limited meaning here. The frontier is a pure computation of its complete preloaded arguments, including the supplied time. Identical arguments yield identical frontier results. That does not make a language model's prose deterministic. Nor do Git refs alone fix every rendered card: lease state, the actor, attempt, local paths and other rendering context also matter. Human decisions, external services and CI observations remain outside that claim.

When an agent claims work, it receives a task card. The card brings together the selected prompt and instructions, declared inputs, useful context such as previous output or corrections, a workspace and exact lease commands. Large material can be represented by a summary and a pointer to the immutable full content. The worker can read further; this is selective initial context, not an access-control boundary.

Consider a design review that finds a missing constraint. The finding is bound to the output it concerns. A filter joins the reviews and keeps the material finding; the design is reopened with that correction. After the worker responds and submits a changed design, the subject has changed and review runs again. The workflow can then present a human approval when its prerequisites are current. The handoff is not just “continue the conversation”: it records why this work is ready and what needs an answer.

The identity rules deserve particular scrutiny. An artifact is identified by its blob; a whole checkpoint uses a normalized change identity. A code tree can be checked separately. Context edges can gate readiness without invalidating existing records, and prompts and instructions do not normally enter the fingerprint simply because they appear on a card. If a prompt change should force a rerun, the workflow author must use the configured revision mechanism. A matching fingerprint says the declared identity did not change. It does not prove the output is right, or that the workflow declared every relevant input.

This distinction matters after an upstream sync. Under the documented carry conditions, a change-bound judgment may remain useful while the actual tree changes and tree checks run again. The configured implementation-review edge can also require a sync-focused review. Conflict resolutions that fail the conservative carry predicate do not get that carry. Leases provide a different boundary: once an expired lease is reclaimed, the old attempt's engine submission is fenced. That fence does not kill the old process or isolate its filesystem.

The paper also records discrepancies instead of hiding them. The implementation targets a 4,096-byte card, but one large previous-result fixture remains at 8,122 canonical bytes after shrinking. A held goal with 150 dependents yields an 11,270-byte `next` result even after actions and human items are exhausted. Those cases qualify stronger size wording in the specification; they are not an evaluation of cost or speed.

The intended benefit is a workflow that can stop, resume and expose its assumptions to inspection. This is an aim, not a measured reliability or savings claim. The mechanism can be too much for a small change and cannot replace sound permissions, independent judgment, deployment controls or complete declarations. A consistently computed answer can still be the wrong answer if the workflow encodes the wrong dependencies.

These distinctions also shape adoption. A repository owns its policy and workflow; installing a newer engine does not silently adopt its shipped defaults. Capability requirements can prevent an older engine from proceeding with a workflow it cannot interpret. A human still needs to examine the declared choices and decide whether the resulting handoffs suit the work.

The paper is a working document: its source binding, evidence ledger, known limits and upkeep procedure are there so we can find flaws and revise it as the implementation changes. Read it alongside the normative specification and inspect the cases that matter to your own workflow.
