# Skill discovery and modes

ZzzOps uses the portable skill contract shared by Codex and Claude Code: the `name` and `description` frontmatter in each `SKILL.md`. Put likely user verbs, nouns, boundaries, and exact mode phrases in `description`; do not invent alias or keyword metadata. Codex's optional `agents/openai.yaml` supplies UI text, while Claude Code may support additional metadata, but neither replaces the common description.

| Skill | Discovery terms | Default | Explicit modes |
| --- | --- | --- | --- |
| `add-zzzops-goal` | add, create, capture, record; goal, TODO, backlog item | Write one canonical goal | None |
| `execute-zzzops` | execute, work all goals, continue, triage, prioritize, reprioritize, unblock | Execute authorized work | `dry run`, `preview`, `plan`: read-only |
| `migrate-to-zzzops` | discover, plan, migrate, import; TODOs, backlog | Build review artifacts; apply only after approval | `dry run`, `preview`, `plan`: report only; `apply`, `migrate`, `import`: approved write |
| `review-zzzops-policy` | review, initialize, summarize, reconcile, adjust; policy | Summarize current policy and invite adjustments | Explicit approval confirms the current reviewed policy |
| `suggest-zzzops-work` | suggest, discover, audit, refill | Dry run | `dry run`, `preview`, `plan`: read-only; `apply`: approved write; `refill`: PROJECT-policy-authorized write |

Generic mode words are contextual: combine them with the task noun, such as “dry run TODO migration.” Installation uses the native root `install.ps1` and `install.sh` scripts rather than an agent skill. Keep descriptions concise and update contract tests when names, modes, or defaults change.

References: [Codex skills](https://developers.openai.com/codex/skills), [Claude Code skills](https://code.claude.com/docs/en/slash-commands).
