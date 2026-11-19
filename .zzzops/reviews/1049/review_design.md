# G1049 gate lifecycle re-review

The revision makes the gate lifetime, holder visibility, CAS renew/release/reclaim, automatic crash recovery and stale-holder refusal observable. It identifies workspace claims, artifacts and op updates and requires a shared fail-closed transaction guard for future work-ref update routes. Public local-remote tests exercise the entry points and expiry/reclaim path, while documenting the direct-push limitation. No new material findings across the applied lenses.
