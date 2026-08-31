# Skill discovery and modes

ZzzOps uses the Agent Plugins skill contract: the `name` and `description` frontmatter in each `SKILL.md`. Put likely user verbs, nouns, boundaries, and exact mode phrases in `description`; do not invent alias or keyword metadata. Codex's optional `agents/openai.yaml` supplies UI text but does not replace the common description.

The table below is the exact ten-skill Agent Plugin package. `run-zzzops-acceptance` is deliberately absent: that skill, `docs/ACCEPTANCE_TEST_PLAN.md`, and `.agents/manual_acceptance.py` are base-repository maintenance and release infrastructure used to validate the shipped workflows, not plugin features.

| Skill | Discovery terms | Default | Explicit modes |
| --- | --- | --- | --- |
| `add-zzzops-goal` | add, create, capture, record; goal, TODO, backlog item | Write one canonical goal | None |
| `bootstrap-zzzops-repository` | bootstrap, create project; repository, agent-ready, specification | Analyze, plan, and execute verified harness goals; stop before product implementation | Greenfield, early scaffold, and brownfield are evidence-derived rather than user-selected |
| `execute-zzzops` | execute, work all goals, continue, triage, prioritize, reprioritize, unblock | Execute authorized work; exclude feedback issues | `dry run`, `preview`, `plan`: read-only; session approval includes all `zzzops-feedback` issues |
| `migrate-to-zzzops` | discover, plan, migrate, import; TODOs, backlog | Build review artifacts; apply only after approval | `dry run`, `preview`, `plan`: report only; `apply`, `migrate`, `import`: approved write |
| `review-zzzops-policy` | review, initialize, summarize, reconcile, adjust; policy | Summarize current policy and invite adjustments | Explicit approval confirms the current reviewed policy |
| `review-agentic-engineering` | review; completed software-agent work, agentic engineering, practice | Read-only evidence attribution and at most two improvements | Explicit invocation only; insufficient evidence produces no advice |
| `review-zzzops-entropy` | review; entropy, repository decay; recent, full | Read-only preview | `recent`: exact pending batch; `full`: repository-wide; `apply`: approved goal capture; `complete`: exact reviewed coverage |
| `send-zzzops-feedback` | send, submit, feedback; execution reports | Preview human-readable cause accounts plus the exact inline report appendix | Exact digest confirmation: create one public ZzzOps issue and delete only submitted reports |
| `suggest-zzzops-work` | suggest, discover, audit, refill | Dry run | `dry run`, `preview`, `plan`: read-only; `apply`: approved write; `refill`: PROJECT-policy-authorized write |
| `validate-zzzops-installation` | validate, check; installation, upgrade, legacy ZzzOps | Audit once per repository and installed package | Explicit invocation revalidates; removal always requires confirmation |

Generic mode words are contextual: combine them with the task noun, such as “dry run TODO migration.” Host installation and updates remain Codex marketplace operations; the validation skill reconciles their repository-local aftermath. Keep descriptions concise and update contract tests when names, modes, or defaults change.

References: [Agent Plugins specification](https://agent-plugins.org/specification), [Codex skills](https://developers.openai.com/codex/skills).
