# G1036 design 11: introduction, Prior Work and no blog

Focused amendment, 14 November 2026. Design 9's conceptual structure, parallel-action/model-guidance distinctions, Future Work, evidence simplification and checker retirement remain settled. This amendment replaces all operative blog requirements in earlier designs and adds the requested selective Prior Work section.

## Owner decisions


WD1–WD8, from the 2026-11-01 interview relayed by the coordinator, remain historical decisions, subject to the supersession below:

| ID | Owner's words | Application |
|---|---|---|
| WD1 | “Both, practitioner-first” | Accessible to a broad audience; no required technical back half. |
| WD2 | “Progressive disclosure” | The general architectural idea remains central. |
| WD3 | “Repo page + blog post” | Paper and README remain; blog deliverable superseded below. |
| WD4 | “External, you publish” | Historical blog publication choice; no blog deliverable remains. |
| WD5 | “Brief related-work section” | Concise substantive Prior Work with primary citations; no superiority claims. |
| WD6 | “Coin "deterministic progressive disclosure"” | Historical quote; exact prior term use is acknowledged, with no coinage or priority claim. |
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

Additional owner requirement, relayed by the coordinator for attempt 11 on 2026-11-14:

> A Prior Work section about progressive disclosure and any other similar concepts (including if there's existing work like determinstic progressive disclosure)

The requested primary-source research is complete in the coordinator's verified research notes. Existing use of the exact phrase was found; WD6 is historical wording, not permission for a coinage or historical-priority claim.

## Focused change

At the beginning of “ZzzOps as an illustration,” before the architecture discussion, introduce it in one short paragraph: repository-based goal and release management for coding agents, serving repository owners and developers who coordinate durable goals, workers, reviews, checks and human decisions across sessions. Explain release support as branching and merge coordination, with deployment handled separately. Then continue the existing illustration. Preserve the immediate general DPD definition and the rest of the approved concise paper.

Delete `docs/blog/release-1.md`. Remove operative blog-draft references from the design, README where present, and PR description. The paper and README link are the deliverables. Keeping the blog as an unused draft would contradict the latest instruction; a broader rewrite is unnecessary.

## Prior Work plan

Add a selective 250–350-word Prior Work section after “The pattern,” replacing the generic related-approaches paragraph. Keep the central argument concise. Use direct primary links and explain who selects each disclosure step; avoid an exhaustive survey or bibliography detached from the argument.

Begin with established HCI usage. The original [Star interface article](https://guidebookgallery.org/articles/designingthestaruserinterface/) (1982) describes relevant object properties as progressive disclosure; use it as an early example, not proof of origin. [Nielsen's discussion](https://www.nngroup.com/articles/progressive-disclosure/) (2006) distinguishes optional complexity from staged task sequences. Explain the overlap in showing material as interaction state changes, while recognizing that agent instructions are a different application. Do not import usability benefits as measured evidence for ZzzOps.

Then compare agent context loading. [Agent Skills](https://www.anthropic.com/research/equipping-agents-for-the-real-world-with-agent-skills) automatically supplies metadata before the model chooses relevant skills and further resources: a hybrid, not wholly agent-led system. Official [Claude Code scoped-memory documentation](https://code.claude.com/docs/en/memory#how-claudemd-files-load) describes software-triggered instruction loading on file access. An agent may choose the operation, while the loader chooses the accompanying material. That already overlaps the paper's general definition; context guidance is not behavioral enforcement.

Explicitly acknowledge [dotagents](https://dotagents.io/), which already uses the exact phrase “deterministic progressive disclosure” and proposes harness-driven scoped instruction loading. Cite this undated project self-description for terminology and overlap only, not vendor comparisons, validation or earliest priority. The checked page was observed on 14 November 2026.

Finally, [Building effective agents](https://www.anthropic.com/research/building-effective-agents) documents predefined workflows, routing and parallelization. Recognize existing explicit coordination and tailored handoffs; a workflow branch can itself use a model. Close by locating this paper's contribution in articulating the selection boundary and illustrating frontier/cards in ZzzOps, without claiming to originate the term or underlying mechanism. The research is selective and cannot establish historical first or absence of other work.

Review the new section for accurate attribution, accessible overlap/distinction and bounded claims; review the introduction for a reader unfamiliar with ZzzOps, truthful release scope, absence of broken references, and the focused diff. Reuse existing whitespace/local verification and ordinary independent review/approval gates; no new tests or infrastructure. Preserve SPEC/DESIGN, runtime, policy, templates and schemas. Update PR #773 while respecting its existing GitHub blocker and rules; no external publication.
