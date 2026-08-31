# OpenAI marketplace compliance review

This document is the human review checkpoint for publishing ZzzOps through OpenAI's plugin marketplace. It is evidence and a checklist, not legal certification. Automated validation can prove that required repository disclosures exist and agree; only the owner can accept terms, make legal attestations, verify identity, submit, or publish.

**Last reviewed:** August 9, 2026

**Support, privacy, and security contact:** [zzzops.support@gmail.com](mailto:zzzops.support@gmail.com)

## Authoritative sources

- [OpenAI App Developer Terms](https://openai.com/policies/developer-apps-terms/) — page updated July 9, 2026 when reviewed.
- [OpenAI Plugin Guidelines](https://developers.openai.com/plugins/app-guidelines) — reviewed August 9, 2026.
- [OpenAI Usage Policies](https://openai.com/policies/usage-policies/) — incorporated by the App Developer Terms.
- [OpenAI plugin submission requirements](https://developers.openai.com/plugins/deploy/submission).

Re-read the live sources before each marketplace submission and after a material policy, data-flow, permission, capability, or monetization change. Update the review date and dispositions in the same reviewed release change. A repository check cannot establish that unchanged links still contain unchanged requirements.

## Current applicability and evidence

| Requirement | ZzzOps disposition and evidence |
| --- | --- |
| Clear, original, reliable purpose | ZzzOps provides reviewed durable project-goal workflows. The README describes the complete user-facing surface; plugin and prompt validation run in required CI. |
| Accurate name, description, capabilities, and side effects | The Codex manifest declares `Write`; its long description and the README disclose GitHub Issue writes, existing GitHub authentication, and policy-governed Git/PR operations. |
| MCP tool annotations and server security | Not applicable: ZzzOps is skills-only and ships no MCP server, tools, API, hosted backend, or UI. Reassess before adding any such surface. |
| Authentication and minimum permissions | ZzzOps requests no separate credential. It uses the user's existing Codex, Git, and GitHub environment, and deterministic checkpoints fail when required access is unavailable. |
| Privacy notice and minimization | [The privacy policy](../PRIVACY.md) lists processed data, purposes, recipients, retention, controls, restricted-data exclusions, and the optional exactly confirmed public feedback flow, including one explicitly selected fixed-schema timing aggregate. |
| Surveillance, profiling, advertising, and commerce | Not applicable: ZzzOps has no automatic telemetry, behavioral profiling, advertising, checkout, sale, subscription, or payment path. Local timing capture is opt-in and cannot leave the machine outside an exact user-confirmed feedback payload. |
| External writes and user intent | GitHub and Git side effects are disclosed. Goal capture is bounded; public feedback shows the exact payload and requires fresh confirmation; reviewed project policy and higher authority govern implementation writes. |
| Restricted and sensitive data | Shipped goal and feedback instructions reject credentials, payment data, health data, government identifiers, and other restricted/raw sensitive data. The privacy policy provides accidental-disclosure guidance. |
| Safety and general audience | User and safety authority outrank goals. ZzzOps is not directed to children under 13 and must not receive children's personal data. OpenAI Usage Policy compliance remains required for every use. |
| Intellectual property and independent branding | The repository is Apache-2.0 licensed; the ZzzOps name and cat images are submitted as project assets. The owner must confirm the necessary rights. The README states that ZzzOps is independently developed and not endorsed by or affiliated with OpenAI. |
| Support and developer verification | `zzzops.support@gmail.com` is the published support/privacy/security contact. The owner must complete and maintain OpenAI developer verification in the portal. |
| Incident response | Security reports go to the published contact. The owner must assess, contain, and report a relevant App/API vulnerability or breach to OpenAI promptly when the terms require it. |
| Accurate submission and ongoing compliance | Portal information must match the reviewed release exactly. The owner reviews live requirements, attestations, test cases, availability, and release notes before submission and publication. |

## Owner checklist before submission or publication

- [ ] Re-read every authoritative source above and record the current review date and any changed requirement.
- [ ] Confirm the public privacy-policy URL resolves and still describes observed behavior, recipients, retention, controls, and the feedback payload.
- [ ] Confirm `zzzops.support@gmail.com` is monitored and can receive support, privacy, and security requests.
- [ ] Confirm the listing and manifest accurately describe GitHub authentication, external writes, capabilities, limitations, and independent-developer status.
- [ ] Confirm the necessary rights to every submitted name, logo, icon, description, and other asset.
- [ ] Confirm the plugin contains no MCP server, hosted service, UI, automatic telemetry, advertising, or commerce, and that any confirmed feedback data flow still matches the privacy notice and exact-preview contract; otherwise stop and reassess every affected disposition.
- [ ] Inspect the release archive and submission materials for secrets, personal data, repository-only tooling, stale versions, and unintended files.
- [ ] Run the required plugin, cross-platform, prompt-budget, and release validation at the exact submitted commit.
- [ ] Supply reviewer-runnable positive and negative tests, starter prompts, availability, release notes, and attestations from the portal-ready sources tracked by [#256](https://github.com/david-rzepa/zzzops/issues/256).
- [ ] Complete developer verification and personally review and make every legal or policy attestation; automation must not accept terms or publish.
- [ ] Record the submitted version, exact commit, bundle digest, portal result, and any reviewer conditions in the release evidence.

## Owner-only legal considerations

The owner—not CI or ZzzOps—must decide whether to accept the App Developer Terms and obtain legal advice where appropriate. The current terms include developer warranties, indemnification obligations, OpenAI's liability limitation, arbitration and class-action provisions, trade-control duties, changing terms, and OpenAI's discretion to reject or remove an app. Repository validation does not resolve those legal choices.
