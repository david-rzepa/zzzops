# Release summary

Expand the existing `next.releases` section with a read-only summary of each Git-flow release/hotfix line. Preserve existing fields and workflow behavior. Summaries show the branch and observed head, configured production target, member completion counts, unfinished member references, line workflow progress, existing next actions and blockers, and recorded production/back-merge evidence. Repository-specific deployment remains outside this view.

Derive all information from the current portfolio, fetched branch tips and immutable goal records. Load closed line goals for publication evidence, while ordinary closed members remain ledger-only. Treat absent or invalid evidence as unknown; closing or cancelling a goal alone does not prove publication. Honor paused/offline execution: offer no actions then. The existing coordinator freshness applies to the summary.

Use the existing `next` interface instead of another command or persistent report. Keep optional summary details within the normal output budget, with `next --all` providing complete detail. No new scheduler, release state, approval or deployment gate is introduced.
