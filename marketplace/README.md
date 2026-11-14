# Marketplace submission sources

This directory is the reviewed, version-controlled source for the OpenAI skills-only submission form. `listing.json`, `test-cases.json`, and `ATTESTATIONS.md` retain listing copy, tests, availability, and human review gates; generated release artifacts are not committed.

Build a fixed-version local probe with:

```text
python .github/scripts/build_marketplace_bundle.py --version 2.0.0 --output <directory>
```

The command emits and validates the portal-upload plugin archive. The semantic-release prepare step runs the same builder for the calculated release version and attaches that ZIP to the release. Form materials stay readable and reviewable here instead of being duplicated into a packet the portal does not consume.

CI never uploads to the OpenAI portal, completes attestations, submits for review, approves, or publishes. Use these canonical sources to fill a portal draft, compare every field and test, check attestations personally, submit for review, and publish only after OpenAI approval.

| Classification | Material | Supported consumer |
| --- | --- | --- |
| Release asset | Versioned OpenAI skills bundle | OpenAI portal upload |
| Repository-only evidence | Listing, test cases, assets, attestations, and semantic release notes | Human portal completion and review |
| Repository-only validation | Claude manifests, generated marketplace probe, strict validation, and installed-cache acceptance | Git marketplace installation and Anthropic review |
| Removed | OpenAI submission-packet and Claude plugin release archives | None; current vendor workflows do not consume them |
