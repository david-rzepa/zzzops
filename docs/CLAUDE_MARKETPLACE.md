# Claude marketplace handoff

This is the maintainer handoff for distributing ZzzOps through Claude Code and submitting it to Anthropic's plugin directory. It records repository-owned facts and verification evidence; it is not a legal attestation, an external approval, or proof of publication.

## Repository contract

ZzzOps keeps one plugin implementation in `plugins/zzzops`. Claude-specific repository metadata is limited to:

- `.claude-plugin/marketplace.json`, which points to `./plugins/zzzops`;
- `plugins/zzzops/.claude-plugin/plugin.json`, which describes that canonical plugin directory.

Skills, rules, scripts, and the ZzzOps runtime are not copied into a second Claude tree or release archive. Anthropic review and normal marketplace installation consume repository state. CI still generates a disposable marketplace, applies the strict validator with the documented SHA-version warning isolated, then performs installed-cache runtime acceptance from a disposable Git-backed repository marketplace.

Claude's cache version comes from the plugin source Git commit. The Claude plugin manifest and marketplace entry intentionally omit `version`; Anthropic documents that `plugin.json` otherwise wins and an unchanged explicit value suppresses updates. Users follow the release-only `latest` branch, so semantic-release remains the product release authority while each published commit naturally has a distinct Claude cache identity. CI does not write or commit a second semantic version.

## Direct Claude Code installation

After the release containing Claude support reaches the repository's default branch, users can install directly from this repository:

```powershell
claude plugin marketplace add david-rzepa/zzzops@latest
claude plugin install zzzops@zzzops
```

Refresh the repository marketplace without uninstalling the plugin:

```powershell
claude plugin marketplace update zzzops
claude plugin update zzzops@zzzops --scope user
```

These commands use ZzzOps's own marketplace and do not imply Anthropic review or directory placement.

## Anthropic submission path

Checked 2026-08-24 against Anthropic's [plugin creation guide](https://code.claude.com/docs/en/plugins), [marketplace documentation](https://code.claude.com/docs/en/plugin-marketplaces), and [community catalog repository](https://github.com/anthropics/claude-plugins-community):

- Anthropic directs plugin authors to its authenticated [Console submission form](https://platform.claude.com/plugins/submit) or the Claude.ai form linked from the official guide.
- The public `anthropics/claude-plugins-community` repository is a read-only mirror populated by Anthropic's review pipeline; direct pull requests are closed.
- Anthropic's documentation and repository currently use both “official marketplace” and “community” terminology. Do not promise a destination catalog or install identifier before the review result names it.
- Submission, identity or legal attestations, review, approval, and publication remain human actions. ZzzOps must not automate the form or use undocumented endpoints.

If Anthropic ultimately lists ZzzOps in `claude-community`, users would follow the catalog's documented pattern:

```powershell
claude plugin marketplace add anthropics/claude-plugins-community
claude plugin install zzzops@claude-community
```

Do not present those commands as live ZzzOps installation instructions until the catalog actually contains ZzzOps.

## Candidate repository facts

Use these repository-derived values when the live form requests them:

| Item | Candidate value |
| --- | --- |
| Plugin name | `zzzops` |
| Repository | `https://github.com/david-rzepa/zzzops` |
| Marketplace manifest | `.claude-plugin/marketplace.json` |
| Plugin source | `./plugins/zzzops` |
| Plugin manifest | `plugins/zzzops/.claude-plugin/plugin.json` |
| Claude cache version | Git source commit (Claude displays its 12-character abbreviation) |
| Canonical Agent Plugin version | `0.0.0-dev` (`latest` and immutable tags define published repository revisions) |
| Description | Agentic engineering with durable goals for autonomous coding agents |
| License | Apache-2.0 |
| Homepage | `https://github.com/david-rzepa/zzzops` |
| Privacy | `https://github.com/david-rzepa/zzzops/blob/main/PRIVACY.md` |
| Support | `zzzops.support@gmail.com` |

The final submission commit is intentionally not hard-coded here. Record the immutable reviewed commit only after parent goal #300 has integrated every required child and its combined checks pass.

## Verification evidence

The reviewed repository contract is exercised by:

```powershell
claude plugin validate . --strict
python .agents/claude_plugin_acceptance.py --claude-version 2.1.241
python .agents/test_marketplace_bundle.py
```

The installed-cache acceptance creates a disposable Git-backed marketplace in an isolated Claude configuration, installs revision A, advances the repository to revision B, refreshes and updates the plugin, and proves Claude uses a new cache path and the second revision's contents. It also verifies exactly ten skills and runs ZzzOps initialization from Claude's cache.

Claude's strict validator currently warns when `version` is omitted even though Anthropic documents omission as the commit-SHA mode. The acceptance harness allows exactly that one warning, requires the same artifact to pass native non-strict validation, and rejects every additional strict-validation warning or error. Required CI repeats the complete contract with a pinned Claude CLI before review.

## Owner checklist

Before submitting:

- [ ] Re-open Anthropic's live documentation and authenticated form; record any changed requirements.
- [ ] Confirm parent goal #300 is integrated and all required checks pass at the exact candidate commit.
- [ ] Confirm the public repository and candidate commit contain both Claude manifests and the complete canonical plugin tree.
- [ ] Run the verification commands above and retain links to the exact-head CI evidence.
- [ ] Verify the repository, homepage, privacy, support, license, description, and Git-derived cache version behavior against the live files.
- [ ] Read every identity, ownership, security, licensing, privacy, and legal attestation in the live form and personally confirm only statements the owner can support.
- [ ] Map every required form field to reviewed repository evidence; preserve unknown fields rather than inventing answers.
- [ ] Review the exact payload and attestations before pressing submit.

After approval or rejection:

- [ ] Record the actual catalog, install identifier, review result, and any requested changes.
- [ ] Test the published installation path in a clean Claude configuration before advertising it.
- [ ] Update this handoff and user onboarding from observed behavior rather than assumed marketplace naming.
