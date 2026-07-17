---
name: install-zzzops
description: Preview, install, or update ZzzOps mechanics in another repository while preserving goal state. Use when copying or refreshing ZzzOps. Backlog discovery/import belongs to migrate-zzzops-todos after installation.
---

# Install ZzzOps

1. Inspect target instructions and preview with `scripts/install_zzzops.py TARGET`.
2. Review conflicts and any content-addressed template diff. Apply the identical plan with `--apply --confirm-plan FINGERPRINT`; use `--overwrite-mechanical` only after explicit conflict review.
3. Inspect the target diff. Verify existing goals, charter, index, ledger, migration state, and project instruction files were untouched. Skills are installed for Codex under `.agents/skills/` and Claude Code under `.claude/skills/`; installation never edits target `AGENTS.md` or `CLAUDE.md`. The installer may append `.zzzops/migration/template-diffs/<old-hash>--<new-hash>.md`; it never edits state from that diff.
4. Stop. Tell the user to invoke `$migrate-zzzops-todos` from the target repository; never discover, import, or delete TODOs during installation. If the preview reports legacy first-release skill directories, retain them by default and tell the user they may remove them after verifying the renamed skills.

The main agent runs the installer because it writes files. Never install this installer into the target, copy base state, overwrite target state, or replace unmarked target instructions.
