# Marketplace submission sources

This directory is the reviewed, version-controlled source for the OpenAI skills-only submission packet. `listing.json`, `test-cases.json`, and `ATTESTATIONS.md` map to the official submission form. CI generates presentation Markdown and exact-version manifests from these sources; generated release artifacts are not committed.

Build a fixed-version local probe with:

```text
python .github/scripts/build_marketplace_bundle.py --version 2.0.0 --release-notes-file <notes.md> --output <directory>
```

The command emits a portal-upload plugin archive and a separate submission packet. It validates both before making them available. The semantic-release prepare step runs the same builder for the calculated release version; the GitHub plugin attaches both ZIP files to the release.

CI never uploads to the OpenAI portal, completes attestations, submits for review, approves, or publishes. Use the generated packet to fill a portal draft, compare every field and test, check attestations personally, submit for review, and publish only after OpenAI approval.
