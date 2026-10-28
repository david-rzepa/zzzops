# Finding resolution batches

Generated and structurally recognized registry TaskSet correction routes, including
ordinary and late reviews, offer one resolution task per exact output scope and current corrected subject. A task can contain any number of
admitted findings. Unrelated standalone static singular resolver contracts remain
unchanged. If a ready registry batch overlaps such a custom resolver at the same
exact scope, the host reports an unsupported overlap rather than bypassing its
additional requirements. Supported registry executors have worker role, empty
resources and self/value authority, with the historical `bounded` or `reasoning`
capability. Static bounded/reasoning lanes preserve those requirements: the host
selects only one lane, at the maximum capability required by the original contracts
covering the exact findings. Unrelated late-event routes do not raise a bounded
finding’s floor; an admitted late finding retains its reasoning requirement.
Other executor contracts require a reviewed policy mapping and fail closed.
Supported registry node fields, finding Ref schemas and resolution output schemas
are recognized exactly; extra required output fields, narrowed finding filters or
applicability conditions receive a specific unsupported-contract diagnostic. The host deduplicates exact finding
identities and revisions across routes; it does not infer equivalence from similar text.

Follow the returned task, acquire and bind its lease, and read its `batch` input.
The manifest contains an exact `target`, corrected `subject`, required review
Result refs, and a `findings` map. Preserve every map key. Submit `value.entries`
with exactly one entry for each manifest finding:

```json
{
  "finding": {"hash": "sha256:...", "uri": "..."},
  "subjects": [{"hash": "sha256:...", "uri": "..."}],
  "reviewer_result": {"hash": "sha256:...", "uri": "..."},
  "decision": "resolved",
  "rationale": "Explain why this exact finding is resolved or remains unresolved."
}
```

`decision` is `resolved` or `unresolved`. Copy the exact finding and corrected
subject refs; choose a qualifying review Result from that finding's manifest
entry. The host verifies all required review routes, including actual executor
independence and inspection of the full corrected subject. Selecting one convenient
reviewer cannot bypass another required review. An approved review alone never
resolves a finding.

Validation is atomic. Missing, extra, duplicated, conflicting, foreign or stale
entries reject the entire submission before provider writes. Public workflow
`--input` rejects duplicate JSON object keys. Python dictionary APIs cannot express
raw duplicate keys; they still reject duplicate finding identities under distinct
entry keys. Working-input freeze and dispatch preserve exact submitted bytes.

An unresolved entry keeps its obligation open. An identical opportunity is not
offered forever: another attempt requires a changed exact finding, corrected
subject, qualifying reviewer, required decision/authority context binding, or
policy contract. Context fingerprints use each input's identity/content mode.
Opportunity identity includes each entry’s applicable original contracts and
required capability, not its peers or selected lane. Resolving reasoning entries
does not reoffer unchanged bounded debt. Operational lease renewals and model
availability refreshes do not by themselves create another opportunity. Closed finding revisions stay closed when later
subjects or reviews change. A newly admitted superseding revision is a new debt.

## Historical acceptance and recovery

Accepted resolution entries are immutable lifecycle decisions, distinct from a
Result being current enough to grant new task authority. The host folds both old
singular resolutions and new batches. It authenticates their actual submit on the
current receipt lineage, source evidence prefix, consumed lease/acquisition and
worker, exact appended Result, lease removal, captured policy contract, and prior
independent review Results. Renewal may advance the source revision: the Result's
expected revision remains tied to its acquisition. Receipt lookup binds the exact
request ID, request hash and response Ref: different recover transactions may
legitimately share one identical response artifact. Historical model pairs need
not be available today. Historical closure authenticates the exact recorded policy
against approved first-parent snapshots and their PROJECT/AUDIT bindings, without
requiring compatibility with today’s policy. This demand-driven lookup has no
policy-commit horizon. Current Result reuse keeps its separate compatibility checks
and existing bounded historical lookup. This trusts the host/provider journal; it is not a
cryptographic defense against an adversary rewriting that trust boundary.

The fold does not reexecute historical DAGs or mark old reviews current. A prepared
orphan comment, disconnected response, changed source lease, forged reviewer or
self-asserted Result cannot grant closure. The immediate submit continuation uses
only its already validated private candidate entries until the receipt commits.
A fresh process reconstructs the same closure from committed history.

Lazy adoption preserves historical graph and comment bytes. Old singular TaskSet
rows remain inert at their original declaration positions, preserving captured
selector locations. New policy-time batch families provide the work. An owned
legacy resolver delays adoption until its owner finishes or is observed stopped.
An owned batch's captured member remains addressable for custody and recovery;
changed inputs still reject its submit. Expiry does not authorize takeover.

A closed late event is dismissed only through an exact authenticated
event → admission → finding revision → accepted resolution chain. A new comment
or merely similar diagnostic still requires its own review. Unsupported custom
resolution contracts and symbolic/literal scope aliases fail closed with a
specific diagnostic, requiring a reviewed policy correction.

Retry the identical request ID and payload after an uncertain response. The common
submit receipt/CAS path handles replay, lost response recovery and stopped owners.
All entries remain readable as immutable evidence. There is no arbitrary finding
or correction count cap; existing artifact byte limits and chunking still apply.
Large batches can require additional evidence comments.

## Reproducible acceptance evidence

`.agents/test_resolution_batch.py` exercises public CLI lifecycle and provider I/O
boundaries. Its four-unique-findings/three-overlapping-routes fixture produces seven
singular resolver leases and submissions at generator commit `d5c9943`, measured at
21 body writes and 21 comment writes. The batch implementation produces one lease,
one submission, three body writes and three comment writes, preserving all four
finding entries. Counts include acquisition, binding and submit, not the preceding
finding/correction work. Comment byte-size limits are checked separately.

`.agents/fixtures/resolution_batch_legacy.json` is a synthetic one-finding public
CLI journal generated by the unmodified `d5c9943` product. Reproduce by running the
public fixture with that revision: produce; reject ordinary review; interpret and
admit one finding; correct producer; approve review; retain finding; acquire, bind
and submit the old singular resolver. The fixture records its generator commit,
policy, issue envelope, original immutable comments and exact finding/Result refs.
No private repository or real goal history is included. Tests assert lazy reads
leave the captured issue/comment history unchanged and reject altered lineage.
