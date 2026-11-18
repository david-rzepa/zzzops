# G1051 design re-review

Changes requested: the maintenance provenance correction resolves `review_design:3:1`, but the new multi-ref race contract still gives a guarantee that a destination-only CAS cannot enforce.

A finished maintenance line now records the approved immutable tip and source lineage without fabricating `production_merge`; the design covers a nested maintenance patch and refuses unapproved or missing provenance.

However, after a verified snapshot, an external actor may move production or revoke a source goal while leaving the destination patch line unchanged. A CAS on that unchanged line compares only the line, so it can succeed even though the separate production/source ref no longer matches the pre-read. This must either be handled with a real atomic cross-ref mechanism or described and tested as an allowed isolated-line advance that cannot lead to production or forward-port without refreshed authority and destination guarding. Do not state that the patch-line CAS itself rejects the separate-ref change.

The other lenses, including the owner’s maintenance decision, identified no additional material issue. Compared the interdiff with integration commit `cb33c2d65b0affbdc60b4492cdc4a032c1014241` and current Git ref/CAS semantics.
