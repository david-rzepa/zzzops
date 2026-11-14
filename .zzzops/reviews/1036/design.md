# G1036 design 10: introduce ZzzOps and remove the blog

Focused amendment, 14 November 2026. Design 9's conceptual structure, parallel-action/model-guidance distinctions, Future Work, evidence simplification and checker retirement remain settled. This amendment replaces all operative blog requirements in earlier designs.

## Owner decisions


WD1–WD8, from the 2026-11-01 interview relayed by the coordinator, remain historical decisions, subject to the supersession below:

| ID | Owner's words | Application |
|---|---|---|
| WD1 | “Both, practitioner-first” | Accessible to a broad audience; no required technical back half. |
| WD2 | “Progressive disclosure” | The general architectural idea remains central. |
| WD3 | “Repo page + blog post” | Paper and README remain; blog deliverable superseded below. |
| WD4 | “External, you publish” | Historical blog publication choice; no blog deliverable remains. |
| WD5 | “Brief related-work section” | Generic positioning without superiority claims. |
| WD6 | “Coin "deterministic progressive disclosure"” | Introduce the term without priority claims. |
| WD7 | “Your name” | David Rzepa with agent drafting/review disclosure. |
| WD8 | “Ratios and trends only” | Conditional; no performance evidence planned. |

The owner previously clarified: “We don't need to include dogfood evidence in the paper, I just wanted to finish dogfooding first to ensure there were no major issues that would require changes to the whitepaper”. No report/evaluation gate returns.

Prior feedback, relayed on 2026-11-14:

> Immediately define ¨Deterministic progressive disclosure¨. This is not a concept specific to zzzops, it could be used for any agentic software. The idea is that instead of the agent driving the disclosure, deterministic software drives the disclosure based on some input. The describe how zzzops uses it to ensure that agents are given clear instruction about how to move through the defined workflow.

> The overall tone doesn't seem like a paper introducing a new concept or idea. I'm not sure how to describe it, but it's way off. Look up guidance on how to write scientific papers and adjust the tone. I'm struggling to understand it. I think it could be less technical so a wider audience can parse it. It doesn't need to describe zzzops in excruciating detail either, the most important part is the philosphies it's built on

> We need to explicitly describe the philosophy that the engine is mostly unopinionated and the actual workflow DAG is customizable. It's an interesting concept to build software with an unopinionated and an opinionated layer.

Latest owner feedback, relayed by the coordinator for attempt 9 on 2026-11-14:

> Ok much better. One thing that isn't explained is that the frontier provides multiple target actions, so it supports parallelisation and model selection for specific tasks (I don't remember if we actually implemented that after the design reset, but we can suggest its useful for that) I think we can simplify even further, I'm honestly not sure how useful the evidence is. And we could add a Future Work section with more ideas for uses for the concept.

This supersedes mandatory public evidence ledgers, size reproductions and checker preservation.

Latest owner steering, relayed by the coordinator for attempt 10 on 2026-11-14:

> I think the whitepaper needs more of an introduction to ZzzOps - what it is. It just jumps right into it at the moment, assuming the reader knows. Also, we don't need the blog post .md.

This explicitly supersedes WD3/WD4's blog deliverable and publication plan; their quotations remain historical only. No new owner choice is required.

## Focused change

At the beginning of “ZzzOps as an illustration,” before the architecture discussion, introduce it in one short paragraph: repository-based goal and release management for coding agents, serving repository owners and developers who coordinate durable goals, workers, reviews, checks and human decisions across sessions. Explain release support as branching and merge coordination, with deployment handled separately. Then continue the existing illustration. Preserve the immediate general DPD definition and the rest of the approved concise paper.

Delete `docs/blog/release-1.md`. Remove operative blog-draft references from the design, README where present, and PR description. The paper and README link are the deliverables. Keeping the blog as an unused draft would contradict the latest instruction; a broader rewrite is unnecessary.

Review the introduction for a reader unfamiliar with ZzzOps, truthful release scope, absence of broken references, and the focused diff. Reuse existing whitespace/local verification and ordinary independent review/approval gates; no new tests or infrastructure. Preserve SPEC/DESIGN, runtime, policy, templates and schemas. Update PR #773 while respecting its existing GitHub blocker and rules; no external publication.
