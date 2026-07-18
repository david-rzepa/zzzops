# Skill discovery and modes

ZzzOps uses the portable skill contract shared by Codex and Claude Code: the `name` and `description` frontmatter in each `SKILL.md`. Put likely user verbs, nouns, boundaries, and exact mode phrases in `description`; do not invent alias or keyword metadata. Codex's optional `agents/openai.yaml` supplies UI text, while Claude Code may support additional metadata, but neither replaces the common description.

| Skill | Discovery terms | Default | Explicit modes |
| --- | --- | --- | --- |
| `add-zzzops-goal` | add, create, capture, record; goal, TODO, backlog item | Write one canonical goal | None |
| `execute-zzzops` | execute, work all goals, continue, triage, prioritize, reprioritize, unblock | Execute authorized work | `dry run`, `preview`, `plan`: read-only |
| `install-zzzops` | install, set up, copy, refresh, update | Preview, confirm, then install mechanics | `preview`, `dry run`: read-only; `apply`, `install`, `setup`, `update`: full workflow |
| `migrate-zzzops-todos` | discover, plan, migrate, import; TODOs, backlog | Build review artifacts; apply only after approval | `dry run`, `preview`, `plan`: report only; `apply`, `migrate`, `import`: approved write |
| `suggest-zzzops-work` | suggest, discover, audit, refill | Dry run | `dry run`, `preview`, `plan`: read-only; `apply`: approved write; `refill`: preference-authorized write |
| `analyze-zzzops-usage` | tokens, usage, cost, overhead, value, efficiency | Analyze and record a local review | None |

Generic mode words are contextual: combine them with the task noun, such as “dry run TODO migration” or “preview ZzzOps install.” Keep descriptions concise and update contract tests when names, modes, or defaults change.

References: [Codex skills](https://developers.openai.com/codex/skills), [Claude Code skills](https://code.claude.com/docs/en/slash-commands).
