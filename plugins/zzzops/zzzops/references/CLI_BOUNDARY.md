# Compact responses and minimal inputs

Workflow stdout is compact by default. `--response full` preserves the complete
programmatic JSON shape; the Python API also returns complete structured data.
Small responses remain inline when reference wrapping would increase their size.
Actionable, unknown and error fields are retained; explicit evidence reads return
the requested content. Required policy reads and independent reviews still apply.

A returned `context` binds the exact saved response, repository, goal and intent.
For the next action, supply this reference, its `operation`, a new request ID and
new decisions/evidence in the input JSON. The CLI restores unchanged fields from
the exact `start`, `bind` or `submission` contract. If several actions match,
supply the exact qualified `node`. Placeholders still require actual values.
Conflicting supplied fields are rejected. Preview context can initiate execution;
other intent mismatches require the matching context or a fresh checkpoint.

References reduce copying; they grant no authority. Existing current policy,
input, lease, actor, independence and retry checks run on every action. For an
uncertain submission, replay its identical request ID and payload rather than
creating a new attempt. A stale, missing or corrupt context requires the reported
repair; do not fabricate fields or approval to bypass it.

To read a saved `full_response` without calling the provider, run the package CLI
with `workflow --repo <repository> --read-response <returned-path>
--response-hash <returned-sha256>`. Add `--goal <goal>` to constrain the goal and
repeat `--select <JSON-Pointer>` for needed sections. Omitting selectors returns
the full response. Keep the returned hash and file together for resumption;
missing, corrupt and wrong-repository references are rejected.
