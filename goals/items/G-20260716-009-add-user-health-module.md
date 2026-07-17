---
id: G-20260716-009-add-user-health-module
title: Add a configurable user-health module
status: triaged
priority: P1
value: high
difficulty: L
confidence: low
owner: unassigned
created: 2026-07-16
updated: 2026-07-16
target_date: null
last_reviewed: 2026-07-16
review_after: null
parent: null
depends_on: [G-20260716-008-require-project-value-interview]
blocks: []
needs_human: true
tags: [health, wellbeing, breaks, hydration, sleep, weekends, preferences, timestamps]
external_refs: ["user-request:2026-07-16"]
claim: {owner: null, claimed_at: null, expires_at: null}
---

# G-20260716-009-add-user-health-module - Add a configurable user-health module

## Outcome / Why

ZzzOps can notice unhealthy work patterns from available user-message times and offer timely, respectful prompts to take breaks, drink water, wind down, sleep, and avoid weekend work. The behavior is user-controlled through finely grained, local, git-ignored preferences, adapts across long autonomous runs, and never turns wellbeing into surveillance, shame, medical advice, or an inflexible blocker.

Provisional value is high because this directly addresses the user's stated late-night/token-FOMO problem and makes autonomous agents safer to leave running without human babysitting. Confidence remains low until `goals/PROJECT.md` defines project KPIs and triage resolves timestamp availability, defaults, and intervention policy.

## Success criteria

- [ ] Define a small shared health-policy module used at workflow entry, after user messages, at bounded long-run checkpoints, and before prompting for more work; it uses actual harness-provided message timestamps/current time when available and never fabricates activity history.
- [ ] When timestamps are unavailable, ambiguous, stale, or lack a configured timezone, behavior degrades explicitly and safely—asking for missing configuration or using only supported signals without pretending to know session length, local bedtime, or weekend status.
- [ ] User-local, git-ignored preferences provide independently configurable global enablement plus break, hydration, late-night/sleep, weekend, long-session, and inactivity-reset policies.
- [ ] Preferences are finely grained and validated: IANA timezone; working days and work windows; bedtime/wake/wind-down windows; break interval/duration; hydration interval; session and message-burst thresholds; category cooldowns; snooze duration/count; escalation levels; reminder tone; acknowledgement/dismissal; temporary overrides; quiet periods; and timestamp/state-retention limits.
- [ ] The interactive ZzzOps CLI can view/edit/reset the health settings without exposing raw message content, and preserves unknown preference keys for forward compatibility.
- [ ] State needed for cooldowns/session detection is minimal, local, git ignored, bounded by retention preferences, and separable from durable project goals/usage accounting; no raw prompts or message bodies are stored.
- [ ] Nudges are observable and autonomy-preserving: they explain the triggering signal, avoid repetition, honor snooze/dismiss/disable/exception choices, and never silently stop authorized work unless the user explicitly enables a blocking policy.
- [ ] Guidance is non-diagnostic and avoids prescribing medical quantities or claiming health outcomes; urgent or medical concerns direct the user to appropriate human/professional help rather than agent inference.
- [ ] Codex and Claude Code integrations document which timing signals each harness exposes and exhibit equivalent policy where capabilities overlap.
- [ ] Synthetic-clock tests cover timezone configuration, DST transitions, midnight/session rollover, weekday/weekend boundaries, work windows spanning midnight, inactivity reset, cooldown/snooze/escalation, missing timestamps, retention, overrides, and no-repeat behavior.
- [ ] Clean install/update probes include ignored preference/state defaults without installing personal state, and prompt-budget counts plus existing workflow/installer tests pass.

## Scope

- In: Shared timing/policy logic; workflow hooks; local preference and minimal state schemas; interactive CLI editing; Codex/Claude capability handling; respectful reminder copy; deterministic time-based tests and concise docs.
- Out: Medical diagnosis/treatment, wearable/device monitoring, hidden telemetry, cloud synchronization, raw prompt retention, forced lockouts by default, OS-level shutdowns, or inferring unavailable timestamps.

## Context and decisions

- The user explicitly requested break, water, sleep, and weekend-work encouragement based on when they send messages, with finely grained preferences.
- Existing user-level configuration lives in ignored `.zzzops/PREFERENCES.json`; `.agents/templates/project-goals/PREFERENCES.json:1-12` currently covers only backlog refill and parallelization.
- The interactive CLI in `.agents/zzzops.py:55-115` already edits existing preference groups and should be extended rather than creating a second settings command.
- `G-008` initialization only advertises the preferences CLI at completion; it does not infer or edit personal settings. This health goal owns the future health preference schema/UI, and the user explicitly configures it later.
- Existing `.zzzops/.gitignore` and installed ignore templates must cover any minimal health-state file so personal timing data cannot be committed accidentally.
- Harnesses may expose current time, message times, or neither. Triage must inspect real Codex and Claude Code capabilities and define an honest capability matrix before implementation.
- Preference groups to design and validate:

| Group | Required controls |
| --- | --- |
| General | enabled, timezone, policy mode, tone, global cooldown, temporary pause/override |
| Work schedule | working days, per-day windows, holidays/exceptions, weekend behavior |
| Breaks | interval, minimum break, inactivity reset, snooze duration/count, escalation |
| Hydration | interval, active window, cooldown, acknowledgement/snooze |
| Sleep | bedtime, wake time, wind-down lead, late-night thresholds, escalation/blocking opt-in |
| Sessions | continuous-session threshold, message-burst threshold/window, reset gap |
| Privacy/state | timestamp source policy, retained derived fields, retention duration, reset/delete |

## Approach and next action

**Next action:** Finish `G-008`, resolve `B-001`, then execute `G-013` through `G-015` sequentially.

### Fast feedback

- Baseline/current observable behavior: ZzzOps has no health policy, timing state, reminder preferences, or workflow hook; current preferences only cover backlog refill and parallelization.
- Hypothesis: Deterministic policy evaluation over explicit preferences and minimal timestamp-derived state can produce useful nudges without noisy repetition or privacy-invasive storage.
- Observation surface (test/harness/API/UI/log/MCP/etc.): Pure policy function with injected clock/timestamp fixtures, CLI round-trip output, ignored-file checks, workflow transcript fixtures, and harness capability probes.
- Smallest chunk: Define preference/state schemas and a pure `evaluate_health_policy(now, recent_activity, preferences)` contract using synthetic times only.
- Probe/action and expected signal: Feed bedtime, weekend, break-due, hydration-due, snoozed, inactive-reset, and missing-signal fixtures; receive one deterministic, explainable action or no-op with no file/network side effect.
- Actual result/evidence: Not run; goal captured from user request and repository baseline.
- Wider checks after local proof: CLI persistence/reset, workflow hooks, Codex/Claude capability parity, install/update state isolation, DST/timezone regressions, prompt budget, and end-to-end no-repeat transcripts.

### Execution constraints

- Mode: `sequential`
- Parallel exception: Read-only harness capability research and independent preference/test-case proposals may run in parallel during decomposition.
- Resources/shared state: User-local preferences and health state, workflow entry points, CLI, installed templates, clock/timestamp sources, and prompt budget.

## Relationships

- Parent: none
- Children (required/optional + purpose/status): [G-013](G-20260716-013-health-policy-schema.md) required/triaged—pure policy/schema; [G-014](G-20260716-014-health-preferences-cli.md) required/triaged—ignored state and CLI; [G-015](G-20260716-015-health-workflow-integration.md) required/triaged—workflow hooks, install/docs, and regressions.
- Dependencies (status/reason): [G-20260716-008](G-20260716-008-require-project-value-interview.md) must initialize project value/KPIs, backend, and workflow preflight before health-policy defaults are selected.
- Blocks (impact): none recorded.

## Blockers

### Open

### B-001 - Confirm health privacy and behavior defaults
- Status/category/raised/owner: open / `decision` / 2026-07-16 / user
- Blocks: health policy implementation and all health children.
- Question or required action: Confirm or correct opt-in, nonblocking, per-repository reminders; derived timestamps only; exact message times when exposed; approximate workflow-receipt time only by explicit opt-in; clear unsupported-timezone warning instead of a dependency.
- Why/options/recommendation: These defaults minimize surveillance, false claims, dependencies, and unwanted interruption while retaining configurable nudges.
- Evidence gathered: Neither Codex nor Claude Code portably exposes send timestamps; Windows may lack IANA timezone data; current preferences are per-repository and ignored.
- Continuation: `stop-affected-work`
- Safe work remaining/recheck trigger: Complete `G-008`; recheck on user reply.
- Resolution/resolved/resolved by: pending

### Resolved

None.

## Progress and evidence

Captured as a new root goal. Repository search found no existing health/wellbeing goal or preference group. Current configuration and CLI provide reusable extension points, while message-timestamp support remains an explicit capability question for triage.

## History

| Date | Actor/run | Change | Reason/evidence |
| --- | --- | --- | --- |
| 2026-07-16 | user/Codex | Created `new` | User requested configurable health prompts based on message times for breaks, hydration, sleep, and weekend boundaries. |
| 2026-07-16 | Codex | Corrected dependency metadata and initialization wording | `G-008` now owns deterministic project initialization rather than ad hoc per-workflow interviewing. |
| 2026-07-16 | Codex alignment audit | Clarified preference ownership | Initialization advertises preferences; `G-009` defines and edits health-specific personal settings. |
| 2026-07-16 | Codex/R-20260716-execute-root | Triaged and decomposed | Three required children isolate pure policy, local preference/state CLI, and workflow/install integration. |
| 2026-07-16 | Codex/R-20260716-execute-root | Raised `B-001` | Privacy, timestamp, enablement, and timezone defaults require user confirmation before health implementation. |
