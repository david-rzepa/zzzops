---
name: analyze-zzzops-usage
description: Analyze ZzzOps tokens, usage, cost, management overhead, delivered value, and value-per-token efficiency. Use for usage/cost reviews, efficiency comparisons, or evidence-based reprioritization; records a local review, not goal execution.
---

# Analyze ZzzOps Usage

Run `../../../.zzzops/rules/INITIALIZATION.md`, then `../../../.zzzops/rules/BACKENDS.md`. Read the charter, usage ledger, canonical goals, and `../../../.zzzops/rules/USAGE_ACCOUNTING.md`.
Run applicable `../../../.zzzops/rules/HEALTH.md` hooks from reviewed PROJECT policy; do not count health state as project value.

1. Validate comparability: separate exact/estimated/unavailable usage and token classes; exclude or label incompatible rows. Allocate shared management overhead consistently and show the method.
2. Determine realized value from verified goal evidence against project KPIs and acceptance criteria—not priority labels alone. Prefer native measures such as KPI delta, acceptance criteria completed, risk removed, or a dependency unlocked.
3. Report native efficiency where possible: realized KPI change or verified outcome per 1,000 compatible tokens. Never combine unrelated KPI units.
4. For cross-goal comparison, use the reviewed PROJECT heuristic weights: value weight × realized fraction × evidence confidence ÷ compatible tokens in thousands. Show every input; do not present this as money, truth, or a KPI.
5. Report management ratio, work/management tokens, samples, uncertainty, fastest verified wins, expensive low-value work, recurring overhead, and Pareto-dominated goals. Apply PROJECT sample thresholds and decline recommendations when evidence is insufficient.
6. Recommend specific changes: reprioritize, split, simplify management, improve feedback loops, revise difficulty, batch blockers, or gather missing measurements. Cost never overrides safety, binding deadlines, project acceptance, or explicit user priority.
7. Run `python .agents/zzzops.py --repo . usage ensure`, then append a concise dated review to ignored local `.zzzops/USAGE_LEDGER.md`. Update goal estimates/priorities only when evidence supports it, with history and rationale. Ask the user before changing a strategic premise.

When usage or value evidence is insufficient, say so and prescribe the minimum measurements needed. Never invent token counts or value merely to produce a ratio.
