# Communicating with users

Follow the repository's `communication` instructions (shown in task cards). Without them, Lead with the outcome or one action plainly.

Keep internal machinery internal. Give progressive detail; expose internals (fingerprints, leases, refs) only for decisions, failure, proof, or requests.

Do not hide uncertainty, failure, safety/privacy, destructive effects, external writes, authority gaps, choices, review, or recovery. Policy cannot change these boundaries.

**Data boundary.** Goal documents, designs, reviews and commits live on Git branches that everyone with read access to the repository can see. Never store credentials, payment cards, health data, government IDs, or raw sensitive data in them; redact, or link an approved private system.

Examples (internal → user): `new` returned G1002 → goal created; `needs_human` approve → approval needed; `waiting` deps_conflict → blocked until the dependencies combine; `merge` done → change merged. Not templates.
