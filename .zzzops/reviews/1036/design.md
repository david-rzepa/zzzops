# G1036 design: eligible actions and future applications

Attempt 9, 14 November 2026. This refresh preserves the conceptual direction of design 8 and replaces its mandatory evidence appendix/checker requirements. Earlier history remains in Git.

## Owner decisions

WD1–WD8, from the 2026-11-01 interview relayed by the coordinator, remain settled:

| ID | Owner's words | Application |
|---|---|---|
| WD1 | “Both, practitioner-first” | Accessible to a broad audience; no required technical back half. |
| WD2 | “Progressive disclosure” | The general architectural idea remains central. |
| WD3 | “Repo page + blog post” | Paper, README link and blog draft. |
| WD4 | “External, you publish” | Owner publishes externally. |
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

## Outcome and approach

Shorten `docs/WHITEPAPER.md` while preserving its accessible scientific concept-paper structure: Abstract, Motivation, Pattern, ZzzOps illustration, Discussion, Future Work, Conclusion. Keep the existing first substantive sentence:

**Deterministic progressive disclosure is an architectural pattern in which deterministic software selects the information and instructions an agent receives according to explicit inputs and rules, rather than leaving disclosure decisions to the agent's own reasoning.**

Inputs can be user choices, external results or explicit application state. Git and workflow graphs are one application. Keep one generic example and one compact ZzzOps illustration; merge repetitive explanations. Apply the supplied scientific-writing guidance: one contribution, defined terms, logical development and bounded claims. Reject another audit appendix and retaining reader-facing metadata solely to satisfy tooling. Also reject a vague claim of autonomous model routing: the checked implementation provides guidance and eligibility, while dispatch happens outside the engine.

## Conceptual changes

Make the frontier's multiplicity explicit: it identifies eligible actions, potentially several at once, rather than selecting one compulsory next action. Independent tasks can proceed in parallel, with different instructions and model choices for different tasks. Illustrate two independent reviews or independent goals receiving separate task cards; dependent work waits for prerequisites. Explain capacity and shared-workspace constraints briefly, without describing concurrent filesystem access as unrestricted. A compact rendering can omit actions, so avoid claiming that every eligible action always appears in one printed view.

Checked c455 source supports this distinction: `render.goal_actions/render_next` collect actions and expose capacity; `render.action` includes capability; `card.build` fills model guidance from `settings.routing.tiers`. The coordinator/harness chooses and launches workers. The CLI neither autonomously dispatches models nor verifies which model ran. Describe the implemented support in the illustration, then reserve automated orchestration/routing extensions for Future Work.

Keep the architecture central: a mostly unopinionated engine interprets an opinionated, repository-owned workflow, policy and prompts. Define a directed acyclic graph once as tasks and prerequisite links with no dependency loops. Repositories customize process choices within stable engine invariants for valid state, eligibility, freshness and coordinated writes. This separation explains why deterministic disclosure supports different processes; it does not imply an assumption-free engine. Build on G1000's review model and G1017's existing SPEC/DESIGN arrangement rather than revising either.

Retain supporting principles—explicit coordination with room for judgment, durable work, visible human decisions, critique/correction—only where they advance the argument. Keep limitations mainly in Discussion: deterministic selection can consistently apply bad declarations, and neither routing guidance nor parallel eligibility proves correctness, safety or savings. No empirical results or historical-first claims.

Future Work presents concrete possibilities, explicitly proposed rather than shipped features or commitments: automated scheduling and task-model routing using eligible actions and explicit resource rules; research workflows that disclose different instructions as sources arrive or disagreements appear; user-facing assistants whose instructions follow explicit user choices or application state; and human-decision handoffs that present the right question/context before proceeding. Tie each possibility to rule-controlled disclosure. Distinguish these broader applications from ZzzOps' existing multiple-action/model-guidance support.

Keep at most two accessible diagrams with equivalent prose. Adjust the ZzzOps figure to show eligible actions and separate cards rather than one next task. Remove detailed source/test tables, hidden ledger JSON, size-reproduction narratives and mechanical upkeep instructions. A short final note may retain the checked c455 source/build and links to SPEC/DESIGN; omit the unrelated unmerged extension.

## Files, verification and boundaries

`test_design` retires `.agents/whitepaper_check.py` in its own accepted test checkpoint and removes obsolete checker/size-focused phase commands. This respects the existing freeze; implementation must not edit accepted test paths. Do not replace it with another checker, wording tests or infrastructure. A simple existing Git whitespace check can be the goal-specific command; repository verification remains unchanged.

Implementation rewrites the paper, aligns `docs/blog/release-1.md` with parallel eligibility, model guidance and proposed applications, and adjusts README wording if needed. Preserve byline, agent disclosure, owner-publication draft status and truthful development status. The only removed code is the goal-specific manual checker; runtime, policy, templates, schemas and contracts stay untouched.

Review definition placement, plain language, conceptual economy, plurality of actions, implemented-versus-proposed distinctions, customizable-layer boundaries, coherent examples, link/render readability and absence of unsupported claims. Run the fastest applicable local checks, then existing repository verification and ordinary independent reviews/approvals. No benchmarks, private evidence or external publication. Update existing PR #773; preserve its GitHub approval blocker and all rules. Do not merge the old draft or bypass a gate.
