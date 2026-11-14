# Who decides what an agent sees next?

**David Rzepa**

Draft for owner publication · 14 November 2026

Drafted and reviewed with AI agents.

An agent needs more than a request. It needs instructions, relevant information and some way to know what to do when a result arrives. Who makes those choices?

One answer is to let the agent decide what to retrieve and what to do next. Another is to have software make some of those decisions using explicit inputs and rules. I call the latter pattern **deterministic progressive disclosure**: deterministic software selects the information and instructions an agent receives from the inputs and rules it has been given, rather than relying on the agent's own reasoning to decide what to disclose.

The idea applies to agentic software generally. A user choice might select one set of instructions; a tool result might select another. The agent still uses judgment to do the task. The software determines the handoff, and can change that handoff as inputs and results change. The inputs themselves may come from people, tools or earlier agent work.

For a simple example, imagine an assistant that can produce either a brief explanation or a detailed comparison. The user chooses a format, and a rule provides the corresponding instructions alongside the source material. The assistant interprets the sources and writes the answer. The rule does not write it; it makes the choice of task explicit.

This distinction becomes useful to consider when work spans several steps. A design can be written, reviewed, corrected and approved by different participants. Each participant needs to understand the current task and the decisions that led to it. A long conversation can preserve history, but it does not necessarily identify the next task or the information needed for it. Explicit handoffs aim to make that progression easier to inspect and resume.

The new [working paper](../WHITEPAPER.md) introduces the pattern and illustrates it with ZzzOps. It is a design argument, not a benchmark or a claim that the approach is always better. Its source appendix binds the illustration to a checked development snapshot; this draft is not an official release announcement.

## A reusable engine and an opinionated process

ZzzOps separates a mostly unopinionated coordination engine from a repository-owned process. The engine interprets a workflow, policy and prompts. The repository can customize the tasks, their prerequisites, instructions, reviews and approval choices supported by the engine. ZzzOps also ships one opinionated default as a starting point.

The workflow is a graph: tasks are connected by prerequisite links without dependency loops. The engine applies common rules for valid state, eligibility, result freshness and coordinated writes. Those are real constraints; “mostly unopinionated” does not mean the engine has no assumptions. The point is that different repositories can make different process choices while using the same coordination model.

This separation shows why deterministic disclosure need not mean a single rigid way of working. Each repository states its process. The engine uses the declared state and rules to select the next eligible work and the initial instructions and context for the worker. The process is opinionated; the mechanism interpreting it is reusable.

Suppose a workflow calls for a design, review and approval. At first, the design can be ready while review waits. A worker receives a task card with the instructions and inputs selected for the design. After the design is submitted, the engine recomputes what can proceed and a reviewer receives the relevant subject and review instructions. If the review identifies a missing constraint, the configured process can return that finding to the design worker as a correction. A revised design can then be reviewed, followed by the configured human decision.

That sequence is synthetic. It shows the intended relationship between coordination and judgment: the software selects and records the handoffs; the workers contribute the design, critique and correction. The card is an initial disclosure, not a security boundary, and a participant may need to inspect more material.

## A design choice, with responsibilities

Explicit rules make coordination choices visible, but they can also encode the wrong choices. A workflow may omit context, use an unsuitable instruction or put a decision at the wrong point. Deterministic selection does not make a result true or a review complete. A record that matches its declared inputs does not prove that every relevant input was declared.

There are situations where agent-led exploration is the right starting point, especially when the path and sources are unknown. A small task may need no formal workflow at all. A system can also combine approaches: give an agent a defined exploration task, let it find material, and use the result to select a later handoff.

For ZzzOps, customization brings responsibility. Repository owners need to review the process they declare and keep it current. Engine checks coordinate work under that process; they do not replace human authority, guarantee secure isolation or prove that a Git merge deployed an application. The paper describes those boundaries and links to the specification and tests for readers who want the implementation details.

The intended contribution is a way to think about the boundary between software coordination and agent judgment. Deterministic progressive disclosure makes some decisions about what an agent sees explicit and repeatable. It leaves the process designer responsible for choosing those decisions, and leaves the agent and reviewers responsible for the quality of the work performed with them.
