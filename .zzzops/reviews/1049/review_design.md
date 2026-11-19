# G1049 design re-review

The prior finding is resolved. The design records lease-fenced start/end commit provenance for every blocked producer attempt atomically with its work-ref update, derives pending candidates from those segments on success, and explicitly tests a test commit before a block followed by a no-op retry. Rebase or sync attribution must be verified or submission refused, and independent review sees candidate exclusions.

The revision also addresses blocked-consumer submission, requires a capability for new persisted provenance, and refuses unsafe operation before capability adoption. No further material findings across intent, simplicity, truth, adversary, concurrency, rollout and experience.
