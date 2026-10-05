# ZzzOps concepts

Concept references give stable operational terms precise definitions without loading a glossary into every agent workflow.

## Authoring syntax

Link the first exact occurrence of every canonical concept term or declared alias in each skill document:

```md
Keep each write a [[bounded commitment]](../../concepts/bounded-commitment.md).

The bounded commitment must be verified before dependent work fans out.
```

The balanced brackets are ordinary Markdown link text, so standard renderers show a clickable `[bounded commitment]`. Later exact, case-insensitive occurrences in that document remain plain text. Each alias establishes its own first-use binding; fuzzy matching, stemming, inferred synonyms, and cross-document bindings are forbidden.

Package validation scans every skill Markdown file. If a packaged concept's canonical term or alias appears before its matching concept link, validation fails—even when the occurrence is otherwise plain prose. This makes reusable vocabulary explicit instead of relying on an agent to infer which ordinary words have special meaning.

## Definition locations

- Packaged concepts: `plugins/zzzops/concepts/<stable-id>.md`
- Project concepts: `.zzzops/concepts/<stable-id>.md`

Targets are explicit relative paths; there is no implicit project override or shadowing. A resolved target must remain inside an allowed concept root. Missing files, absolute paths, unsafe traversal, anchors, query strings, duplicate IDs, conflicting terms or aliases, repeated bindings, and labels not declared by the target definition are invalid.

## Definition schema

Each definition is a Markdown file named for its lowercase hyphenated stable ID. It contains one `zzzops-concept` JSON metadata block with exactly:

- `schema_version`: currently `1`;
- `id`: the filename without `.md`;
- `term`: the canonical display phrase;
- `aliases`: explicit alternative phrases; and
- `authority`: always `informational-only`.

The required non-empty sections are Meaning, Decision rule, Scope and authority, Examples, Counterexamples, Parameters and invariants, Aliases and related concepts, and Compatibility. The scope section must state that the concept grants no authority and cannot weaken higher authority.

## Progressive disclosure

Agents resolve only definitions explicitly linked by the document and load each target once. Related-concept prose is not traversed automatically. Whole-catalog loading is reserved for deterministic authoring and package validation, where it is necessary to detect unlinked first uses and catalog conflicts.

Material definition changes require review of affected policy, prompts, goals, acceptance behavior, and compatibility notes. Concepts explain meaning and decision tests; user and safety authority, repository instructions, reviewed policy, and goal state remain authoritative.

## Default evidence workflow

The shipped workflow is one configurable evidence DAG. Discovery records each human-facing uncertainty as a **stable question** with its source, blocked decision, status, answer, revision, and provenance. Root owns those questions and preserves settled answers until their exact source or an admitted finding changes. Delegated investigators answer technical unknowns, and independent review members cover acceptance, maintainability, and each evidenced risk without turning risk labels into hidden orchestration.

Decomposition selects a leaf or a composition. An atomic result is a reviewed non-applicability decision for decomposition: it must prove one indivisible workspace responsibility, no independently deliverable boundary, and no useful parallel ownership. It then retains the complete leaf delivery path. A composition instead consumes immutable child delivery results in the parent integration workspace; child work never depends on the parent's integration, publication, or merge.

Migration verification and independent migration review precede publication whenever released contracts or supported prior states exist. Explicitly targeted reads of closed goals remain available, while broad portfolio discovery does not hydrate closed goals merely to manufacture evidence.
