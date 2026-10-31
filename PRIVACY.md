# ZzzOps Privacy Policy

**Effective date:** August 9, 2026

**Contact:** [zzzops.support@gmail.com](mailto:zzzops.support@gmail.com)

ZzzOps is an open-source, skills-only Agent Plugin. It has no ZzzOps-operated server, account system, analytics, advertising, or payment service. The plugin runs through Codex in the user's environment and uses tools and accounts that the user has configured there.

## Data ZzzOps processes

ZzzOps may process the following data to perform a user-requested workflow:

- Repository content and metadata available to Codex, including source files, documentation, configuration, Git history, branches, pull requests, checks, and repository instructions.
- Project policy and local ZzzOps state stored under `.zzzops/` in the user's repository.
- Goal content and metadata stored on Git branches of the user's repository (`zzzops/goal/*`, `zzzops/work/*` and related branches), including titles, specifications, designs, reviews, decisions with the deciding person's name and words, findings, and phase records with agent labels and times.
- Pull requests, required-check results and, when a goal links one, a GitHub issue that ZzzOps closes when the goal is delivered.

ZzzOps does not need and must not be given authentication secrets, passwords, API keys, MFA or one-time codes, payment-card data, protected health information, government identifiers, or other restricted or regulated data.

## Why data is processed

ZzzOps processes repository and goal data only to initialize reviewed project policy; capture, migrate, prioritize, and execute project goals; coordinate Git and GitHub work; and verify results. It does not use this data for advertising, behavioral profiling, model training, sale, or unrelated purposes.

## Who receives data

- OpenAI processes conversations, repository context, and tool activity provided to Codex under the terms and privacy choices for the user's account or workspace. ZzzOps does not control OpenAI's retention or use of that data.
- Local repository data is handled in the user's Codex environment and by tools the user authorizes. The ZzzOps developer does not receive it through a ZzzOps-operated service.
- GitHub receives data that ZzzOps reads or writes through the user's existing GitHub authentication. Goal and implementation records are visible to the selected repository's permitted audience; in a public repository, they are public. GitHub attributes writes to the authenticated GitHub account, so its username and public profile may be visible with a branch, commit, pull request or issue update. GitHub processes that data under its own terms and privacy statement.

ZzzOps does not sell personal data or disclose it to advertisers or data brokers.

## Retention

- Local `.zzzops/` state and goal worktrees remain in the user's environment until the user removes them or the documented workflow removes them.
- Goal branches are kept as the goals' history; ZzzOps never deletes them. Work branches are kept until the user deletes them.
- Data written to GitHub remains according to the user's repository settings, actions, and [GitHub's privacy practices](https://docs.github.com/site-policy/privacy-policies/github-general-privacy-statement). ZzzOps does not control GitHub backups, forks, caches, or copies made by repository viewers.
- Requests for correction or deletion can be sent to the contact below and will be handled where technically and legally possible; removal cannot guarantee deletion of third-party copies.

## Your choices and controls

Users can:

- choose whether to install or use ZzzOps and which repository it may access;
- use a private GitHub repository and restrict repository collaborators;
- redact sensitive context or link to an approved private system instead of placing it in a goal;
- review, edit, or remove local ZzzOps state and manage GitHub records using their normal repository controls;
- review or rewrite goal documents with `zzzops edit`, and delete branches with their normal Git controls; and
- request privacy, support, or security assistance at [zzzops.support@gmail.com](mailto:zzzops.support@gmail.com).

If restricted data is entered accidentally, remove or redact it from local and GitHub records where possible, and rotate any exposed credential through its provider.

## Security and children

ZzzOps uses the permissions of the user's existing Codex, Git, and GitHub environment and does not request a separate credential. Users remain responsible for repository access controls and for reviewing proposed external or destructive actions. Security concerns can be reported to [zzzops.support@gmail.com](mailto:zzzops.support@gmail.com); do not include active credentials in a report.

ZzzOps is a developer tool for a general audience and is not directed to children under 13. Do not use it to submit personal data about children under 13 or below the applicable age of digital consent.

## Changes

This policy will be updated when ZzzOps data practices materially change. Marketplace releases review the current [OpenAI App Developer Terms](https://openai.com/policies/developer-apps-terms/) and [OpenAI Plugin Guidelines](https://developers.openai.com/plugins/app-guidelines); the repository history records policy changes.

## Contact

For support, privacy requests, or security reports, email [zzzops.support@gmail.com](mailto:zzzops.support@gmail.com).
