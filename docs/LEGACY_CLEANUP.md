# Legacy per-project cleanup

ZzzOps v2 is installed as a Codex plugin. Repositories upgraded from the retired installer releases may still contain copied skills, control code, shared rules, and installer metadata. The plugin ships a cross-platform Python cleaner for only that retired per-project machinery.

## Preview and apply

Run the script from the installed ZzzOps plugin package. The first command is always read-only:

```text
<python> <installed-zzzops-plugin>/scripts/cleanup_legacy.py <target-repository>
<python> <installed-zzzops-plugin>/scripts/cleanup_legacy.py <target-repository> --apply
```

`--apply` repeats the complete safety check after the preview and then requires the exact phrase shown at the prompt. Automation may add `--yes` only after independently reviewing that same preview.

The preview identifies every file to remove, each installer-owned ignore block to update, and any affected Git-tracked path. The cleaner never stages, unstages, removes, or otherwise changes the Git index; tracked files remain represented there as working-tree deletions for normal review.

## Ownership and refusal rules

The cleaner accepts one unambiguous ownership proof:

- a valid `.zzzops/ZZZOPS_LOCK.json`, whose path and content hashes match all remaining retired machinery;
- a valid `.agents/zzzops/INSTALL_MANIFEST`, whose recorded file fingerprints match all remaining retired machinery; or
- the bundled immutable path/SHA-256 catalog for the published lockless v1.0.0 release.

Missing proven files are allowed so rerunning after an interruption converges safely. Unexpected files, changed contents, malformed provenance, path traversal, non-portable paths, symlinks or junctions, and ambiguous fingerprint matches block before removal begins. For the lockless catalog path, the v1 control CLI is retained as the final anchor and removed last.

The cleaner deletes individual proven files and then removes only empty retired directories. It does not recursively delete a tree. Before applying it rechecks the complete machinery and metadata signature so any change after preview cancels the operation.

## Preserved data

Cleanup is deliberately narrower than deleting `.zzzops`. It preserves:

- `.zzzops/PROJECT.md`, `.zzzops/PROJECT_AUDIT.md`, and `.zzzops/POLICY.json`;
- migration records, execution reports, goal state, and any other durable project state;
- root repository instructions and unrelated ignore-file content;
- the installed Codex plugin, Codex marketplace/cache data, and global skills; and
- unrelated project files and all Git index entries.

If cleanup stops after removing some proven files, rerun the preview. The valid lock/manifest or retained v1 anchor authorizes only the remaining matching files. If a mismatch is reported, inspect it manually; do not edit the catalog or provenance to force removal.
