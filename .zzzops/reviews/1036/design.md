# G1036 design: a general concept paper

Attempt 8, 14 November 2026. Supersedes the audit-led structure, exhaustive coverage, technical-back-half obligation and long target. Preserve design/review history; no repository files change in this phase.

## Owner decisions

WD1–WD8 were recorded from the 2026-11-01 interview, relayed by the coordinator:

| ID | Owner's words | Current application |
|---|---|---|
| WD1 | “Both, practitioner-first” | Broad accessibility; latest feedback supersedes a required technical back half. |
| WD2 | “Progressive disclosure” | The central architectural idea. |
| WD3 | “Repo page + blog post” | Repository paper, README link and blog draft. |
| WD4 | “External, you publish” | Owner publishes the blog; this goal does not. |
| WD5 | “Brief related-work section” | Brief generic positioning. |
| WD6 | “Coin "deterministic progressive disclosure"” | Introduce the term without historical-priority claims. |
| WD7 | “Your name” | David Rzepa; disclose agent drafting/review. |
| WD8 | “Ratios and trends only” | Conditional on performance evidence; none is planned. |

The owner previously clarified: “We don't need to include dogfood evidence in the paper, I just wanted to finish dogfooding first to ensure there were no major issues that would require changes to the whitepaper”. No report or evaluation gate returns.

Latest feedback, relayed by the coordinator for attempt 8 on 2026-11-14, is controlling:

> Immediately define ¨Deterministic progressive disclosure¨. This is not a concept specific to zzzops, it could be used for any agentic software. The idea is that instead of the agent driving the disclosure, deterministic software drives the disclosure based on some input. The describe how zzzops uses it to ensure that agents are given clear instruction about how to move through the defined workflow.

> The overall tone doesn't seem like a paper introducing a new concept or idea. I'm not sure how to describe it, but it's way off. Look up guidance on how to write scientific papers and adjust the tone. I'm struggling to understand it. I think it could be less technical so a wider audience can parse it. It doesn't need to describe zzzops in excruciating detail either, the most important part is the philosphies it's built on

> We need to explicitly describe the philosophy that the engine is mostly unopinionated and the actual workflow DAG is customizable. It's an interesting concept to build software with an unopinionated and an opinionated layer.

No further owner interview is needed.

## Outcome and chosen approach

Rewrite `docs/WHITEPAPER.md` as an accessible conceptual/design paper, around 1,800–2,800 words of main text. The abstract opens before source metadata or jargon:

**Deterministic progressive disclosure is an architectural pattern in which deterministic software selects the information and instructions an agent receives according to explicit inputs and rules, rather than leaving disclosure decisions to the agent's own reasoning.**

The definition applies across agentic software. Inputs can include user choices, external results, task state or other explicit values; Git and workflow state are ZzzOps choices. Define unfamiliar terms when introduced. The reader must understand the contribution without reading the appendix.

Use the supplied PLOS/Nature writing guidance editorially: one contribution, accessible opening, clear motivation and logical progression. This is a design argument with an illustration, not an experimental report. Reject the previous audit walkthrough as the central structure and a concept-only manifesto without a concrete application. Neither dense implementation detail nor unsupported benefit claims improve the explanation.

## Main argument and structure

1. **Abstract.** Define the general pattern immediately, identify the disclosure problem, introduce the separation of coordination rules from agent judgment, and identify ZzzOps as an illustration. No fabricated results or priority claims.
2. **Motivation.** Explain why choosing what an agent sees is a design decision. Describe the burden of asking an agent to infer both its task and the context needed to perform it, and continuity beyond a chat. Introduce explicit software-controlled handoffs as the proposal. Keep anticipated clarity, reproducibility or efficiency benefits framed as design aims.
3. **Concept and principles.** Explain a deterministic disclosure function in ordinary language: explicit inputs plus rules select instructions/context; changed inputs can select a different handoff. Input producers and agent reasoning need not be deterministic. Develop explicit coordination with room for agent judgment, durable work, visible human authority and critique/correction as supporting principles. Briefly position related approaches without superiority claims; retrieval can also be deterministic.
4. **ZzzOps application.** Explain the two-layer architecture centrally. A mostly unopinionated engine interprets a repository-owned workflow, policies and prompts; ZzzOps ships one opinionated default. Define a directed acyclic graph (DAG) once as tasks and prerequisite links with no dependency loops. Repositories can customize tasks, dependencies, instructions, reviews and approval choices within engine constraints. The engine retains stable invariants for valid state, eligibility, record freshness and coordinated writes; “mostly unopinionated” never means assumption-free or universally configurable. Deterministic disclosure need not impose one rigid process: the same engine applies explicit rules to different repository-defined workflows. Explain this separation as how DPD stays reusable, with maintenance responsibility on workflow authors. Source support: DESIGN §2.2 and name-independence/renamed-graph tests.
5. **Discussion.** Gather trade-offs and limitations here instead of hedging every paragraph. Rule declarations can omit relevant context or encode bad choices; customization costs effort and can reduce comparability. Deterministic selection does not establish correct reasoning, secure isolation or universal benefit. Discuss where agent-led exploration or a simpler handoff is appropriate. Separate general-pattern limitations from ZzzOps implementation limitations.
6. **Conclusion.** Restate the contribution and its design implications, without introducing evidence or mechanics.

Use one example—such as a user choice or returned analysis selecting the next instructions—before the ZzzOps illustration. Then follow one synthetic design/review/correction handoff through state → frontier → next → card → result → recomputation. Define “frontier” as the computed view of what can proceed and what must wait; explain cards as clear instructions for progressing through the configured workflow. Avoid node inventories, command examples, schemas and exhaustive transitions.

Include at most two compact Mermaid figures, each with equivalent prose: the general disclosure loop and the engine interpreting replaceable workflow/policy/prompts. The latter shows defaults as one configuration, not replaceable engine invariants. Favor connected prose over tables; use source links in the appendix.

## Supporting material and validation

Move existing binding labels, claim/source/test ledger, implementation limits and upkeep into a short appendix; link SPEC for exact behavior and DESIGN for rationale. Retain useful evidence without making auditability the paper's organizing thesis. Keep the checked c455 source/build binding. Omit the optional unmerged release-summary extension; it adds no necessary conceptual explanation.

Keep `.agents/whitepaper_check.py` unchanged: its regex accepts binding fields anywhere, and its hidden ledger can move intact. Preserve required claim families and accurate size-bound qualifications in the appendix. Rewrite the blog and README link around the general concept and customizable layers; keep byline, agent disclosure and owner-publication draft status aligned.

Validate editorially against all three owner bullets, first-sentence definition, accessible terms, architecture boundaries, conceptual scope, example coherence and evidence honesty. Run the existing manual checker locally, check links and render/print readability, then retain ordinary workflow reviews and gates. No new infrastructure. No runtime, policy, template, schema, contract or private-evidence changes; no benchmarks, deployment claims or external publication. PR #773's GitHub approval blocker remains; do not merge the old draft or weaken rules.
