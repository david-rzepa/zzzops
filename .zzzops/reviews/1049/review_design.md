# G1049 design re-review

The owner chose protection against cooperating ZzzOps writers, with the remaining out-of-band direct-push race disclosed. The revised design records that decision, requires a changed unique gate ref in an atomic CAS transaction for all cooperating workspace claims and mutations, covers fencing across expiration and reclaim, and requires realistic competing-writer and direct-push race tests. It no longer claims a no-op push provides atomic cross-ref protection. Diagnostic and apply output expose the scope of the guarantee.

No new material finding across the applicable lenses.
