# ZzzOps Privacy Policy

**Effective date:** August 9, 2026

**Contact:** [zzzops.support@gmail.com](mailto:zzzops.support@gmail.com)

ZzzOps is an open-source, skills-only Agent Plugin. It has no ZzzOps-operated server, account system, analytics, advertising, or payment service. The plugin runs through Codex in the user's environment and uses tools and accounts that the user has configured there.

## Data ZzzOps processes

ZzzOps may process the following data to perform a user-requested workflow:

- Repository content and metadata available to Codex, including source files, documentation, configuration, Git history, branches, pull requests, checks, and repository instructions.
- Project policy and local ZzzOps state stored under `.zzzops/` in the user's repository.
- Goal content and metadata stored in GitHub Issues, including titles, descriptions, relationships, blockers, evidence, labels, comments, and GitHub-generated account or repository identifiers.
- For optional public feedback, user-authored feedback, explicitly selected execution reports, and at most one explicitly selected local timing diagnostic. Reports contain a content-derived identifier, creation timestamp, bounded workflow and cause codes, an agent category, numeric impact, and the installed ZzzOps version and revision. A timing payload contains only a content-derived identifier, fixed phase aggregates, measurement provenance, bounded agent/platform/Python categories, and validated ZzzOps feedback-build provenance. These structured payloads are designed not to contain project names, paths, code, goals, domain facts, user content, raw output, or secrets.

ZzzOps does not need and must not be given authentication secrets, passwords, API keys, MFA or one-time codes, payment-card data, protected health information, government identifiers, or other restricted or regulated data.

## Why data is processed

ZzzOps processes repository and goal data only to initialize reviewed project policy; capture, migrate, prioritize, and execute project goals; coordinate Git and GitHub work; verify results; and prepare user-requested feedback. It does not use this data for advertising, behavioral profiling, model training, sale, or unrelated purposes.

## Who receives data

- OpenAI processes conversations, repository context, and tool activity provided to Codex under the terms and privacy choices for the user's account or workspace. ZzzOps does not control OpenAI's retention or use of that data.
- Local repository data is handled in the user's Codex environment and by tools the user authorizes. The ZzzOps developer does not receive it through a ZzzOps-operated service.
- GitHub receives data that ZzzOps reads or writes through the user's existing GitHub authentication. Goal and implementation records are visible to the selected repository's permitted audience; in a public repository, they are public. GitHub attributes writes to the authenticated GitHub account, so its username and public profile may be visible with an issue, comment, commit, or pull request. GitHub processes that data under its own terms and privacy statement.
- Optional feedback is submitted only after ZzzOps shows the exact payload and the user explicitly confirms it. The payload is posted to the public `david-rzepa/zzzops` GitHub repository and becomes visible to the public and GitHub.

ZzzOps does not sell personal data or disclose it to advertisers or data brokers.

## Retention

- Local `.zzzops/` state, execution reports, and Git-local timing diagnostics remain in the user's environment until the user removes them or the documented workflow removes them.
- An execution report or timing diagnostic selected for feedback is deleted locally only after successful submission. Cancellation, validation failure, or submission failure retains it for review or retry; unselected diagnostics are never removed by feedback submission.
- Data written to GitHub remains according to the user's repository settings, actions, and [GitHub's privacy practices](https://docs.github.com/site-policy/privacy-policies/github-general-privacy-statement). ZzzOps does not control GitHub backups, forks, caches, or copies made by repository viewers.
- Public feedback issues are retained as project records. Requests for correction or deletion can be sent to the contact below and will be handled where technically and legally possible; removal cannot guarantee deletion of third-party copies.

## Your choices and controls

Users can:

- choose whether to install or use ZzzOps and which repository it may access;
- use a private GitHub repository and restrict repository collaborators;
- redact sensitive context or link to an approved private system instead of placing it in a goal;
- review, edit, or remove local ZzzOps state and manage GitHub records using their normal repository controls;
- disable local execution-report recording in reviewed ZzzOps policy;
- leave timing profiling off, inspect or purge local timing diagnostics, and decline or omit diagnostic sharing;
- inspect the exact public feedback payload, cancel submission, or remove content before confirming it; and
- request privacy, support, or security assistance at [zzzops.support@gmail.com](mailto:zzzops.support@gmail.com).

If restricted data is entered accidentally, do not submit it as feedback. Remove or redact it from local and GitHub records where possible, and rotate any exposed credential through its provider.

## Security and children

ZzzOps uses the permissions of the user's existing Codex, Git, and GitHub environment and does not request a separate credential. Users remain responsible for repository access controls and for reviewing proposed external or destructive actions. Security concerns can be reported to [zzzops.support@gmail.com](mailto:zzzops.support@gmail.com); do not include active credentials in a report.

ZzzOps is a developer tool for a general audience and is not directed to children under 13. Do not use it to submit personal data about children under 13 or below the applicable age of digital consent.

## Changes

This policy will be updated when ZzzOps data practices materially change. Marketplace releases review the current [OpenAI App Developer Terms](https://openai.com/policies/developer-apps-terms/) and [OpenAI Plugin Guidelines](https://developers.openai.com/plugins/app-guidelines); the repository history records policy changes.

## Contact

For support, privacy requests, or security reports, email [zzzops.support@gmail.com](mailto:zzzops.support@gmail.com).
