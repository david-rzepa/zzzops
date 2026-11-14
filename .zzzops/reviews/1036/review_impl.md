# G1036 implementation review, attempt 2

Approved. No material findings.

Reviewed subject `93889189b5b58cb99d73d9e700a8e2e11dfe5b7e`, starting with the interdiff from the prior subject `580987251909105fb202d84648828e8271abf08c`. The controlling design is blob `7aa4db7dc9cac42eaaa2b947bb4097cf8152e896` (attempt 8). Source claims remain bound to `c455b09914b49fd65e169f91a4f79110e3e2540b`. There were no prior findings requiring statuses. I did not read other reviews of this subject, mutate source, run remote workflows or inspect private evidence.

## Compliance pass

The rewrite addresses all three controlling owner requests. Its abstract's first sentence defines deterministic progressive disclosure as software selecting an agent's information and instructions from explicit inputs/rules rather than the agent making that disclosure decision through its own reasoning. The motivation and generic research-assistant example establish that this is a pattern for agentic software generally; Git and a DAG are subsequently introduced as ZzzOps choices.

The main argument is accessible without the appendix: motivation → pattern → ZzzOps illustration → discussion → conclusion. DAG and frontier are explained at first use. The source binding, implementation ledger, size discrepancies and upkeep have moved to supporting material. The old exhaustive mechanics, third diagram and long target are correctly superseded rather than requirements to restore. The two retained figures are compact and have equivalent prose.

The engine/process philosophy is central to the illustration, not an incidental qualification. The text distinguishes a mostly unopinionated engine's invariant coordination rules from repository-owned, opinionated workflow/policy/prompts and a shipped default. It explicitly explains that determinism does not require the same rigid process in every repository. The blog and README description follow the same framing; byline, agent disclosure and owner-publication draft status remain appropriate.

The supplied PLOS/Nature guidance was applied editorially through a clear contribution, accessible opening and logical progression. No experimental results, superiority claim or historical-first claim were introduced. The paper remains a design argument, with anticipated benefits labelled as aims.

## Correctness pass

The general claim is precisely bounded: identical complete inputs under the same disclosure rule select the same disclosure; time, configuration and tool results count as inputs when relevant. Nondeterministic input producers and agent reasoning are explicitly allowed. Initial selection does not prevent later exploration or imply access control.

For ZzzOps, the prose preserves the distinction between engine invariants and supported repository choices. It does not claim an assumption-free engine or unlimited configurability. I checked the pinned architecture description, generic workflow schema/engine boundary and renamed graph journey. The renamed review journey changes node and lens identifiers, drives to the approval/integrate states and inspects the resulting PR summary, supporting actual interpretation of configured graph data rather than merely finding a reference with a suitable name.

The synthetic design/review/correction example matches the existing frontier/card/review behavior reviewed in attempt 1: recorded state selects eligible work, a claimed task receives selected instructions/inputs, a configured review finding can reopen its target, and changed output is reviewed again before configured approval. Its deliberately conceptual wording does not promise every graph has this sequence. The main text also accurately qualifies currentness under declared inputs, context gating without identity contribution, stale-submit fencing, Git history and deployment boundaries.

## Missing pass

I searched the immutable subject's public README/docs for the paper and disclosure references. The main paper, shorter blog and navigation now describe the general pattern and customizable layers consistently. The appendix still supplies the checked source/build/date/status, normative references, source/test families, two known size exceptions and upkeep. The unchanged manual checker remains compatible with moving those fields and its hidden ledger. No sibling runtime, policy, schema, publication or infrastructure change is required by this rewrite.

## Tests pass

No test files changed. The checker remains an integrity/reproduction audit and explicitly does not claim to establish semantic support or editorial quality. Those aspects were reviewed directly. Existing assertions support the retained implementation illustration and appendix boundaries; the new configurable-process citation is supported by the actual renamed journey assertions described above. The broad claims about the proposed pattern are a design argument, not disguised test or empirical claims.

The card records a passing local manual audit (356 ms), 12 focused checks (1,597 ms) and all 1,121 local policy checks with zero failures/errors (360,044 ms). There is no changed-test contribution. The unavailable baseline is explained as changed commands/allocation; no timing comparison is inferred. These checks need not be repeated for this prose review, and no unresolved substantive claim required an additional runtime probe. The known 8,122-byte card and 11,270-byte `next` exceptions remain documented boundaries, not fixes for this goal.

## Craft and unfamiliar-reader pass

Reading the main text alone, I can explain the general idea: explicit software rules choose what an agent initially sees and does next, while the agent retains judgment in doing the task. I can explain the illustration: ZzzOps computes eligible work from recorded state and a repository-defined process, then discloses that task through a card and recomputes after results or review. I can explain why deterministic does not mean rigid: repositories can choose different supported processes while the engine consistently applies its coordination invariants to each configuration.

The prose develops this argument without requiring schemas, command knowledge or appendix-first reading. The example and discussion expose the costs of explicit rules and customization without inventing evidence. Source-level inspection found no blocking readability or print-fallback problem; the prose preserves both figures' meaning without Mermaid. I did not independently produce a browser/PDF render. The parent coordinator reports all 19 links/anchors resolve. No concrete material craft issue was found.

## Findings

None.
