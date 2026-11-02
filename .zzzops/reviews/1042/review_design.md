# G1042 design review

Approved. The design addresses the reported README drift and stays within documentation and the specifically requested GitHub metadata proposal. No findings.

I read the full goal spec and design and checked the integration baseline `de5640d1c5909ea924450aeea6450497a78946f6` against README.md, docs/EXECUTION.md, docs/MAINTAINING.md, the capture skill, capability validation, release-line finishing code, and the existing documentation/disclosure/positioning checks.

- The README on dev already identifies Git goal branches. The design correctly separates that working tree from the still-published main README and live GitHub metadata; it does not pretend a dev merge updates the published front page.
- The bounded opening preserves branding and the tested positioning phrases. Describing stop/resume and project-owned configuration corrects claims without inventing a product direction.
- `engine.min` remains supported and deprecated in schemas.py; the compatibility wording accurately distinguishes it from required capabilities.
- Release-line finish uses the approved recorded tip, merges into the configured production branch and back-merges. It does not publish a release. Maintaining independently reserves main for intentional owner releases and explains the semantic-release/latest pipeline. The design's conditional account of the actual release route is appropriate.
- Future sync/review/budget claims are explicitly gated on dependency code reaching the implementation base and the required capability. The implementation audit must retain this condition rather than describe approved plans as shipped.
- The narrow supporting-doc edits and deferral to G1031 avoid competing work. A short claim ledger in the PR body is an explicit acceptance requirement in the goal spec; no extra persisted evidence system is needed.
- Existing doc/disclosure tests and direct link inspection are proportionate. The design does not add recursive tests for prose or a new checking framework.
- Exact GitHub description/topic changes are concrete and match the existing canonical vocabulary. The spec explicitly places their external application under owner approval at merge, so this approval step is justified by the requested contract. The proposal preserves unrelated current values and reports pending application separately from the Git merge.

No owner choice is needed during design. Routine wording corrections remain implementation decisions; only a consequential branding or direction change would need a new owner question. Final wording and the exact metadata change are reviewed at approve_merge as required by the spec.
