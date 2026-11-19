# Adversarial design re-review

Approved. The revised design defines the child baseline, takes the full union of changed paths (including retry and blocked-attempt history), records exact accepted entries including absence, and fails closed on missing provenance. It also requires a real submodule regression that alters only an accepted helper. This resolves the prior finding.

The newly specified route-change checks retain unresolved findings and require independent review of retained code or a separately reviewed removal before a true-to-false transition may unlock tests. The route decision is fingerprinted into the challenge, filter, and approval chain, closing the obvious stale-approval bypass.
