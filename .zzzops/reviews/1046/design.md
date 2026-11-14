# G1046: pin the published implementation

Change only the Implementation note in `docs/WHITEPAPER.md`: replace development-only wording with the actual published semantic version, tag, immutable commit, matching package build and authoritative release/source/reference links. Preserve all conceptual prose, Prior Work, exact-term acknowledgement, byline and no-blog decision inherited from G1036/G1045.

The coordinator must not claim/start implement or write a pin until root supplies a real published tag/commit/asset receipt. Previews and predicted versions are rejected. Preparation through test review may proceed now.

At implement, verify public release/tag/commit and package facts dynamically from that receipt; record URLs, identifiers and verification in phase output. Missing or inconsistent evidence means no pin is written.

Review the bounded diff and links; reuse the existing Git whitespace command, configured verification and exact-head gates. No new tests, infrastructure, runtime/policy changes or release actions. Root retains merge authority.
