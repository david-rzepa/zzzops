---
name: install-zzzops
description: Install, set up, copy, refresh, or update ZzzOps mechanics in another repository. "preview" or "dry run" guarantees no writes; "apply", "install", "setup", or "update" writes mechanics only after preview. Not backlog migration/import.
---

# Install ZzzOps

Mode: `preview` or `dry run` stops after step 1 with no writes. `apply`, `install`, `setup`, or `update` follows the full preview-confirm-apply workflow; this is the default when no mode is stated.

1. Inspect target instructions and preview with `scripts/install_zzzops.py TARGET`.
2. Review mechanical conflicts. Apply the identical plan with `--apply --confirm-plan FINGERPRINT`; use `--overwrite-mechanical` only after explicit conflict review.
3. Inspect the target diff. Verify project state, goals, local preferences, and project instruction files were untouched. Skills are installed for Codex under `.agents/skills/` and Claude Code under `.claude/skills/`; installation never edits target `AGENTS.md` or `CLAUDE.md`.
4. Stop. Tell the user to invoke any non-install workflow so its agent initializes the project, then `$migrate-zzzops-todos` to discover/import existing TODOs. Never initialize state, discover/import work, or delete TODOs during installation.

The main agent runs the installer because it writes files. Never install this installer into the target, create/copy project state, overwrite target state, or replace unmarked target instructions.
