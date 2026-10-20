# Release planning

Release planning is repository scoped and disabled until the reviewed
`git_review_release.release_planning` policy enables it. Positive integer release
IDs are planning identities; published semantic versions and tags are separate
provider observations.

Use `zzzops release status` to read the control record. `configure`, `assign`,
`checkpoint`, `approve`, and `publication` accept `--input` JSON. Every write carries a unique
`request_id`; configuration and assignment also carry `expected_revision`.
Retry an uncertain operation with the identical request. A changed payload or
stale revision is rejected rather than overwriting concurrent work.

`assign` accepts an `assignments` array of `{goal, release}` objects and validates
the complete batch before its first effect. Its result reports each item as
`applied` or `pending`. Public goal capture may include `target_release`; goal
creation remains recoverable when the subsequent assignment is uncertain.

The release checkpoint proceeds through proposal, frozen intent, and confirmed
branch creation. Proposal and freeze use current provider evidence for members,
active owners, integration commits, source ancestry, policy, repository, and
authority. Cut rechecks those facts under the repository lock immediately before
the create-only remote branch operation. Same-ref/same-SHA retries reconcile;
different SHAs conflict. Only confirmation advances `next_release`.

After branch confirmation, `approve` records explicit human approval bound to
the exact frozen release and target. `publication` accepts that authenticated
approval reference and records version and tag only from the provider. Release
planning does not authorize merging main or publishing.
