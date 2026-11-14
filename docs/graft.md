# Graft repository navigation

Graft provides a local structural graph for code navigation. The setup was
verified with `@nanonets/graft` 0.17.0. Install that version if `graft` is absent:

```sh
npm install --global @nanonets/graft@0.17.0
```

Build the graph separately in each worktree. Generated files under `graft/`
are ignored by Git; no API key or model-based enrichment is required.

```sh
DO_NOT_TRACK=1 graft build
DO_NOT_TRACK=1 graft check
DO_NOT_TRACK=1 graft map
DO_NOT_TRACK=1 graft ask "symbol or question" --source
DO_NOT_TRACK=1 graft skeleton path/to/file.py
DO_NOT_TRACK=1 graft callers symbol
DO_NOT_TRACK=1 graft callers symbol --direction out --depth 2
DO_NOT_TRACK=1 graft grep "literal"
```

Rebuild after source changes, and check structural freshness before relying on
the graph. A missing deep/meaning layer is expected for this structural setup.
Ranked answers are not exhaustive; inspect source spans to verify findings.

Version 0.17.0 excludes dot-directories, including `.agents` tests and `.github`
tooling. Use `rg` and direct source inspection for these paths, dynamic behavior,
and unresolved relationships. Missing edges do not establish that dependencies
or callers are absent. The graph does not authorize skipping tests; goal #557
tracks dependency-based test selection and its required correctness checks.

The root `.ignore` makes graph cards searchable while excluding internal graph
and cache data. No global agent instructions, hooks, or MCP configuration are
needed for this repository setup.
