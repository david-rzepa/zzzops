# Who decides what an agent sees next?

**David Rzepa**

Draft for owner publication · 14 November 2026

Drafted and reviewed with AI agents.

**Deterministic progressive disclosure** is an architectural pattern in which software selects the information and instructions an agent receives from explicit inputs and rules, rather than relying on the agent's reasoning to decide what to disclose.

An agent needs a task, context and instructions. Sometimes it should discover these through exploration. In a known process, software can make some of those choices directly. A user's selection can choose one prompt; a tool result can select another; a review can provide the correction needed for the next handoff. The agent still does the reasoning within the task.

For example, an assistant might offer a brief explanation or a detailed comparison. The user chooses, a rule supplies the corresponding instructions and sources, and the agent writes the response. The disclosure decision is explicit without prescribing the answer. The same idea can extend across sessions when requests, results and outstanding decisions are recorded durably.

The [working paper](../WHITEPAPER.md) introduces this general pattern and uses ZzzOps as an illustration. It presents a design argument and proposed applications, without claiming measured superiority. This owner-publication draft describes a development snapshot, not an official release.

## A reusable engine and a customizable process

ZzzOps separates a mostly unopinionated coordination engine from an opinionated, repository-owned workflow, policy and prompts. It ships one default process, which repositories can adapt. The workflow is a graph of tasks and prerequisite links without dependency loops.

The engine keeps common rules for valid state, eligibility, result freshness and coordinated writes. The repository chooses process details within those constraints: tasks, instructions, inputs, reviews and approval arrangements. This is how deterministic disclosure can support different ways of working without requiring a different engine for each one.

The engine computes a **frontier** of what can proceed and what must wait. That frontier can expose several eligible actions, not just one next task. Two independent reviews, for example, can receive separate cards and run in parallel while later work waits for them. Capacity and shared-workspace constraints still apply.

Each eligible agent action carries a capability requirement, and task cards list configured model suggestions. A coordinator can use this guidance to choose different models for different tasks. The coordinator or harness launches the workers; the engine does not autonomously dispatch models or verify which one ran.

When a review finds a missing constraint, the configured process can return it to the design task as a correction. A revised design can be reviewed again, then presented for the configured human decision. Results change the state, and the system recomputes eligible work and the context to disclose. Workers supply judgment; software coordinates the handoffs.

## Where the idea could go

The paper's Future Work section proposes uses across agentic software. Automated coordinators could build on eligible tasks and explicit resource rules to schedule parallel work and route tasks to models. Research applications could change instructions as sources arrive or analyses disagree. User-facing assistants could adapt their handoffs to explicit choices or application state. Human decision handoffs could gather the relevant alternatives and context before work proceeds.

These are proposed directions, distinct from ZzzOps' existing multiple-action and model-guidance support. Each asks the same question: which disclosure decisions should software make explicitly, and which should remain with people or agents?

Explicit rules can encode bad choices or omit important information. They need review and maintenance. Deterministic selection does not establish correct reasoning, complete reviews, secure isolation or successful external actions. A simple task may need no formal workflow, and an unfamiliar problem may call for agent-led exploration.

The aim is to make a useful boundary visible: software can select tasks and context through rules, people can retain authority over decisions, and agents can exercise judgment in the work they are given.
