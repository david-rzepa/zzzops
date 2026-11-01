# G1037 review_design (attempt 1)

**Verdict: changes requested, on one finding.** The public design is generic and faithful to the root's private run plan. It carries my three G1035 points:
- **F1 (redact every public write):** handled by §6 and the widened A15.
- **F2 (keep the public design generic):** done.
- **F3 (later-release goals):** handled by §4.4, which creates them held, and A6.

The remaining problem is that A15 and the pre-write gate, as specified, cannot pass. The scope reaches history that is not this run's, and the deny list matches ordinary text in this repository. Separately, I have sent deny-list gaps to the root privately.

## What I checked

- **The public design and this goal's refs.** The design (blob dc8a15a), the commits on this goal's work branch that are not on dev, and this goal's state branch all give no deny-pattern hit. Nothing in the design identifies the app.
- **Faithfulness to the private plan.** The plan's essentials appear in generic form:
  - the root-held `implement`;
  - the one-time housekeeping step that stops if any file would change;
  - held later-release goals;
  - staging outside the engine, on the exact release tip, with its own approval, and `approve_finish` bound to the same tip;
  - the redaction scope and quotes with `[redacted]` replacements;
  - A1–A17.

  Small inconsistencies inside the private plan, for the root to tidy up:
  - its §7.3 still describes the old, narrower diff-only scan, while its A15 and §7.4 have the wide one;
  - its header still says it lands in a public repository;
  - its start-snapshot line cites A15 where A16 is meant.
- **F3.** Held goals do not block the Release 1 cut, because G1025's cut condition looks only at goals of release N. `new` accepts `state`, so goals can be created held. A6 checks both.
- **OD wording.** OD1–OD7 are quoted with only identifying words replaced, and §2 says so.

## Finding

### F1 (material, target `design`): A15's scope and the deny list together fail on text that is not the run's

A15 scans "the full history of every zzzops ref the run touched (goal, work, PR and lease branches)". Work and PR branches descend from the integration branch, so their full history is dev's whole history.

Today, the private deny list matches about 700 lines of dev's history and about 160 lines at dev's tip. I reviewed every match at the tip. All of them are false positives:
- short digit fragments of ids that match inside SHA-256 values;
- common English and programming words that this engine's own code and tests use;
- one phrase in `PRIVACY.md`.

One already-public defect goal this run depends on (G1032) also matches one pattern in its spec. That match is again generic, not identifying.

As specified, then:
- A15 fails on its first run.
- §6's gate would block legitimate writes that quote engine code or describe hosting limits generically, such as a defect goal about card clipping or a G1032 follow-up.
- A gate that cries wolf gets bypassed.

**Fix:**
- **Scope.** A15 scans only the run's own content: `git log -p <I>..<ref>` for work, PR and lease branches, the full history of the goal state branches (they hold only goal content), PR text, defect goal documents, and the report and data.
- **Tuning.** Tune the deny list against this repository. Anchor numeric ids as whole digit runs, and replace generic words with app-specific phrases or names.
- **Precondition check.** Before the run, `git grep -i -E -f <patterns> <I>` and a scan of the defect goal documents must print nothing. Rerun this whenever the list changes.
- **G1032.** Decide whether its matching phrase is rewritten or the pattern is narrowed.
