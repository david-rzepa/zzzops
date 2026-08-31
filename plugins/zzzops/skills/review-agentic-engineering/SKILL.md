---
name: review-agentic-engineering
description: ZzzOps v0.0.0-dev — development plugin. Review completed software-agent work on explicit request and suggest one or two evidence-based improvements to the user's overall agentic-engineering practice. Read-only; not a scorecard, automatic coaching, repository mutation, or ZzzOps feedback submission.
---

# Review Agentic Engineering

Read `../../rules/COMMUNICATION.md` for user-facing messages.

Run only when explicitly invoked. Help the user improve how they use software agents across projects without assuming that friction was their prompting fault.

1. Read [evidence and attribution](references/ATTRIBUTION.md). Inspect several substantial completed work items when available, using evidence already visible in the current environment. Do not create a prompt archive or copy raw project content into attribution input or output.
2. Attribute the evidence through the bounded read-only `coaching attribute` interface. Evaluate expectations relative to effective rigor, task stakes, repository context, specialist context, and facts an agent should have discovered itself.
3. If evidence is insufficient or ambiguous, say so plainly and stop. Do not manufacture advice to fill a report.
4. Select at most two high-value observations. Coach user practice only for genuine specification gaps. For context, skill, tooling, guardrail, verification, implementation, or external causes, name the owning system surface and avoid blaming the user.
5. Make each observation concise: the pattern, why it matters, and one practical improvement or durable destination. Optimize information efficiency, verification, task boundaries, and autonomy—not prompt length.

Remain read-only: do not edit policy, `AGENTS.md`, documentation, skills, tests, CI, goals, or repository files, and do not write to GitHub. Recommend a destination without changing it. `$send-zzzops-feedback` separately submits feedback about ZzzOps itself; never invoke or imitate it here.

Before stopping, apply the privacy boundary in `../../rules/FEEDBACK.md` without recording a new execution report solely because this review ran.
