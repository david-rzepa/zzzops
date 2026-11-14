# G1036 design review, attempt 8

Approved, with no findings. The design responds to the owner's latest feedback as a single conceptual argument: deterministic software controls disclosure, while a stable engine can interpret different repository-owned workflows. ZzzOps illustrates the general idea. The main paper no longer has an implementation-audit or exhaustive-behavior obligation.

## Subject and scope

Reviewed design blob `7aa4db7dc9cac42eaaa2b947bb4097cf8152e896`, its change from `9c056c03d9f2e0238eadcef88eef497970e66e6a`, and revised specification blob `1d29fefe77710b23077697d23f3c6d2b3aea38ab`. Applied every lens on the card independently, in order. There are no prior findings requiring status updates. No other subject reviews were read.

The latest verbatim owner feedback in the specification and design supersedes the earlier structure, length and exhaustive inventory. This review does not restore them as acceptance conditions. Settled WD choices and the newer feedback are quoted in Owner decisions; no new owner choice is introduced.

## Intent

The proposed first substantive sentence defines deterministic progressive disclosure generally, without making Git, workflow state or ZzzOps part of the definition. User choices and external results are explicitly valid inputs. The abstract, motivation, principles, illustration and discussion all support the same contribution. The mostly unopinionated engine and customizable opinionated layer are central to the application and explicitly connected to reusable disclosure. Plain language, term definitions, a small general example and a synthetic handoff address the wider audience requested by the owner. README and blog alignment, authorship/disclosure, external-publication limits and lack of a dogfood report requirement are preserved. The revised scope remains consistent with project intent: the engine is small and project-owned workflow/policy supplies the opinions.

## Simplicity

The design removes the node inventories, command/schema detail, optional unmerged extension, long technical back half and excessive diagram plan from the main argument. Supporting evidence moves into an appendix and normative details are linked. The existing manual checker remains unchanged; there is no new CI, simulator, infrastructure or runtime work. The conceptual structure is sufficient to explain the proposed pattern without requiring an exhaustive audit document. The general example and ZzzOps handoff have complementary purposes: establish the abstraction, then make its use concrete. No material simplification is missing.

## Truth

The definition concerns the disclosure-selection function; input producers and agent reasoning need not themselves be deterministic. This avoids implying deterministic end-to-end agent behavior or experimentally established benefit. The engine/configuration distinction is bounded by retained validity, eligibility, freshness and coordinated-write invariants. Repository customization is expressly within those constraints, rather than a claim that arbitrary engine assumptions can be configured away.

Pinned c455 DESIGN §2.2 records removal of hard-coded default node identities in favor of selectors/attributes, and the implementation/tests support the narrower name-independence claim. Existing checker commit `6417262fa2d0d06afb514ef0e493eca8e2faed51` was inspected directly: `field` searches the full document with multiline matching; `ledger` searches its hidden comment independently of placement. Moving intact labels and ledger into an appendix is therefore compatible with keeping it unchanged. Accurate size-bound qualifications and known implementation limits are retained in supporting material, without becoming the main thesis or a new runtime-repair gate.

The supplied editorial guidance was also checked against [Mensh and Kording's PLOS article](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1005619) and [Nature's summary guidance](https://www.nature.com/documents/nature-summary-paragraph.pdf): one central message, clear terms, accessible framing and logical progression are appropriate adaptations. The design deliberately does not invent experimental results to mimic an experimental-paper template.

## Adversary

The discussion addresses declarations that omit relevant context or encode poor choices, and distinguishes selection from correct reasoning, isolation or universal benefit. It does not promote a configurable graph into an unrestricted authority or security guarantee. Generic positioning avoids unsupported superiority or historical-priority claims. Private run evidence, external publication and deployment claims stay out of scope. There is no new authority-bearing action in this documentation design.

## Concurrency

No execution, lease, storage or scheduling behavior changes. The retained invariants and explicit-input framing avoid treating concurrent external observations or agent results as deterministic just because disclosure selection is deterministic. The single synthetic correction/recomputation handoff is appropriate for explaining the concept; exhaustive retry, lease and sync walkthroughs need not return to the main paper. Implementation-specific limits remain in the existing appendix/reference arrangement.

## Rollout

The change continues the existing paper/blog/README work and preserves its source/build binding, useful ledger, limits and upkeep. Metadata can move without checker changes. The source pin remains explicit rather than silently rebinding the document to an installed package or unmerged extension. Existing workflow gates and PR #773's approval blocker are expressly retained; no merge-rule relaxation or external publication is authorized by this design.

## Experience

The reader encounters the general definition before metadata or internal terminology. Unfamiliar terms are introduced in ordinary language, and the DAG and frontier definitions are short and concrete. The two-layer illustration shows defaults as one replaceable configuration while preserving engine invariants, which makes the owner's architectural philosophy understandable. Connected prose, bounded examples and equivalent prose for diagrams support broad and print audiences. The reader can understand the contribution without opening the appendix. Precise final wording, layout and example clarity remain implementation/editorial review work; they are not reasons to block this sound design.

## Local verification and limits

Four focused tests passed from an immutable archive of `c455b09914b49fd65e169f91a4f79110e3e2540b`: `test_engine_names.NameIndependenceTests` and `test_engine_review_lenses.RenamedReviewJourneyTests`. The exact command and output are in the adjacent `verification.json`. These support the engine's separation from shipped names and the tested renamed workflow; they do not prove arbitrary graphs valid or establish empirical performance benefits.

The revised prose is not yet implemented. The planned unchanged manual checker, links, rendering/print review and owner-bullet editorial pass remain necessary during implementation. No runtime source, checker, policy, template or contract was edited in this review.
