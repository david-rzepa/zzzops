# G1048 design review

Approved with no findings. The focused illustration change answers the owner’s request without expanding the paper or changing product behavior.

Reviewed the assigned design and spec independently, then checked the relevant default graph and CLI/card functions at the card’s integration tip, `ffb3e43f3be01ebd7733a3751d57f79c5dc7f33b`. No other review was read and no tests were rerun.

- **Intent:** The design adds the missing shipped-process explanation and identifies the CLI as the disclosure mechanism. It preserves the general definition, Prior Work, Future Work, byline, published implementation pin and dev-only boundary.
- **Simplicity:** One illustration edit, short equivalent prose and existing verification are proportionate. No new reference catalogue, checker, test or infrastructure is proposed.
- **Truth:** `next` exposes frontier/status/start commands; agent `start` builds the selected card, while operation `start` runs the operation. Card content may use pointers. The coordinator dispatches work and recomputes `next`; the design does not claim an automatic scheduler or enforced model routing.
- **Adversary:** Explicit human decisions and separate result submission remain visible. The design grants no new authority, publication action or bypass of checks.
- **Concurrency:** The checked default has fifteen nodes. Design review and adversarial critique share the design input; integration and merge approval have distinct prerequisites. The proposed prose avoids a false single serial chain and qualifies the visible frontier by capacity/display rules.
- **Rollout:** Only the whitepaper illustration changes. The unchanged-test checkpoint, whitespace check, configured local full validation and ordinary exact-head gates preserve the requested verification without changing runtime or stored formats. Main, release/tag and publication remain excluded.
- **Experience:** Short diagram labels, an agent/operation branch and equivalent prose make the two-stage disclosure understandable without requiring a CLI manual. The existing capability/model-guidance distinction remains intact.

There are no unresolved owner choices or material findings.
