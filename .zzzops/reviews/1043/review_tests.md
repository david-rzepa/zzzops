# G1043 independent test review, round 3

Decision: **approved**. No open prior findings and no new findings. The previously resolved portability finding remains resolved and is not re-recorded.

Read the complete new card, mapped tests checkpoint `5907d057e5a713e015635acecf85a33658106f49`, range-diff from the prior approved checkpoint `51edabe503247c4806fe55ea09164a7de1d8de9d`, exact patch, and the author's generic CLI control evidence. Approved design revision 3 remains unchanged.

The only test amendment replaces `reviewed.inputs.cost` with an explicit assertion that cost is absent from inputs and a read of `reviewed.context.cost`. This matches the existing production `card.build` contract: it routes each declared input with context:true into context instead of inputs before rendering the card. G1043's fixture explicitly declares cost as context:true, so the former access was wrong. The new absence assertion also strengthens the intended identity separation.

The complete measured cost equality assertion and optional blob decoding remain immediately after the corrected access. Measured checkpoint/command/exit/duration data, portable real red/green launcher, renamed-graph plumbing, green checks and approval summary assertions are unchanged. The previous 50 substantive cases and two launcher controls retain their earlier reviews.

Verification was limited to the exact patch against existing production routing, clean diff checks and recorded generic source-free CLI evidence: inputs_keys=[], context_keys=[cost], passed in 0.575 s. That is author-provided runtime evidence, not a repeated run by this reviewer. Repeating broad suites or restoring saved implementation would not improve this two-line contract correction. Checkpoint-vs-base paths are solely the eight approved test/fixture files; no product implementation or installed policy is frozen into tests.

## Dogfood notes

None.
