---
name: install-zzzops
description: Install, set up, copy, refresh, or update ZzzOps mechanics in another repository. "preview" or "dry run" guarantees no writes; "apply", "install", "setup", or "update" writes mechanics only after preview. Not backlog migration/import.
---

# Install ZzzOps

Mode: `preview` or `dry run` stops after step 1 with no writes. `apply`, `install`, `setup`, or `update` follows the full preview-confirm-apply workflow; this is the default when no mode is stated.

1. Inspect target instructions and preview with `scripts/install_zzzops.py TARGET`. For dry run, explain the capabilities and major surfaces that would be installed plus any conflict requiring action; the approval code only binds apply to that exact preview.
2. For apply, use the identical plan with `--apply --confirm-plan APPROVAL_CODE`; use `--overwrite-mechanical` only after explicit conflict review. Do not replay preview detail.
3. Inspect the target diff. Verify project state, goals, local preferences, and project instructions were untouched.
4. Stop. Report installation success and the next useful action: invoke a non-install workflow to initialize, then `$migrate-to-zzzops` for existing TODOs. Never initialize, migrate, or delete TODOs during installation.

The main agent runs the installer because it writes files. Never install this installer into the target, create/copy project state, overwrite target state, or replace unmarked target instructions.
