# CI coverage

Linux remains the complete product-validation platform. Each Python version (3.10 and 3.14) runs eight deterministic shards whose disjoint union is the complete current `.agents` unittest inventory. Discovery rejects loader errors and duplicate canonical IDs before partitioning. Every shard validates its exact selected, started and completed IDs; missing, duplicate, unexpected or partial execution fails the job. A new test is automatically included even when no timing hint exists.

`.github/scripts/linux_test_timings.json` contains performance hints, never an allowlist. The runner assigns the longest estimated tests first, breaking ties by canonical ID and shard index. It reserves 20 estimated seconds on shard 0 for the non-core commands. Shard 0 alone runs migration-skill tests, the manual coverage audit, plugin and release tests, prompt statistics, and Python compilation, once on each Python version. Only shard 0 installs Node and npm dependencies. Windows, macOS and Claude installed-cache legs retain their coverage.

The unsharded command `python .github/scripts/run_product_validation.py --platform linux` retains full discovery followed by all non-core commands in their original order. CI invokes `--shard-index 0 --shard-count 8 --workers 2` (with indices 0 through 7). Add `--discover-linux` to inspect a partition without executing tests. Every shard uploads a report named `linux-python-<version>-shard-<index>` with the full inventory count/digest, selected and executed IDs, completion counts, individual durations and total wall time; the job summary exposes counts and estimated/observed duration. Timing hints use measured hosted durations where available; projections still need verification against the full job, including setup and runner contention. Linux checkouts include full history and tags so published-version contracts execute instead of skipping.

Each Linux shard uses at most two fresh Python child interpreters, supervised by a thread pool. The same timing hints deterministically balance disjoint child selections, without reserving auxiliary overhead again. Per-child observations are retained and checked before combining counts and exact started/completed IDs; a failing child cannot be overwritten by a successful sibling. `--workers` defaults to 1 and accepts only 1 or 2. No additional hosted jobs are created.

The explicit `LINUX_EXCLUSIVE_TESTS` list contains only `test_evidence_dag_journeys.EvidenceDagPublicTests.test_pure_frontier_has_no_io_and_fixed_expanded_equal_work_budget`. Its existing one-second wall-clock assertion runs unchanged in a fresh child after both concurrent children have exited, avoiding contention with sibling tests. Discovery fails if that listed identity disappears. It remains part of the exact shard inventory and execution count; this is scheduling isolation, with no skip or relaxed threshold. Reports include configured/actual concurrent worker counts, serial IDs, and every child's selected IDs and full observation. Auxiliary checks still run once, after all tests succeed.

The former Windows and macOS command groups have these dispositions. The discovery commands shown identify the same complete inventory now partitioned across Linux shards; a native-retained ID is the narrower cross-platform assurance that runs on Windows and macOS.

| Former native command group | Complete Linux disposition | Exact native-retained test IDs |
| --- | --- | --- |
| `.agents/test_workflow_*.py` | Covered by `python -m unittest discover -s .agents -p test_*.py`. | `test_workflow_heartbeat.HeartbeatProcessTests.test_one_coordinator_renews_multiple_leases_and_stops_tracking_workers`<br>`test_evidence_dag_journeys.WorkspaceAuthorityPublicTests.test_mixed_clean_checkout_rejects_raw_consumed_drift_and_restores_exact_acquisition`<br>`test_evidence_dag_journeys.WorkspaceAuthorityPublicTests.test_crlf_design_correction_retains_frozen_raw_checkout_overrides`<br>`test_evidence_dag_journeys.WorkspaceAuthorityPublicTests.test_clean_crlf_checkout_pins_raw_consumed_bytes_and_allows_owned_red_edit`<br>`test_evidence_dag_journeys.WorkspaceAuthorityPublicTests.test_acquired_owned_path_cannot_be_replaced_by_escaping_symlink`<br>`test_workflow_publication_contract.GenericDeliveryPublicTests.test_reviewed_red_green_proofs_commit_and_exact_publication_form_one_delivery_graph` |
| `.agents/test_phase_*.py` | Covered by `python -m unittest discover -s .agents -p test_*.py`. | None. Its unique assurance remains Linux-only. |
| `.agents/test_zzzops.py` | Covered by `python -m unittest discover -s .agents -p test_*.py`. | `test_zzzops.InitializationTests.test_cli_without_command_shows_help_without_writing_local_state` |
| `.agents/test_legacy_cleanup.py` | Covered by `python -m unittest discover -s .agents -p test_*.py`. | `test_legacy_cleanup.LegacyCleanupTests.test_default_cli_is_dry_run_and_interrupted_cleanup_converges` |
| `.agents/test_installation_validation.py` | Covered by `python -m unittest discover -s .agents -p test_*.py`. | `test_installation_validation.InstallationValidationTests.test_cli_clean_first_use_and_idempotent_status` |
| `.agents/test_marketplace_bundle.py` | Covered by `python -m unittest discover -s .agents -p test_*.py`. | `test_marketplace_bundle.MarketplaceBundleTests.test_fixed_version_build_is_deterministic_and_complete`<br>`test_agent_plugin.AgentPluginTests.test_marketplace_points_to_the_self_contained_package` |
| `plugins/zzzops/skills/migrate-to-zzzops/scripts/test_*.py` | Covered by `python -m unittest discover -s plugins/zzzops/skills/migrate-to-zzzops/scripts -p test_*.py`. | None. Its unique assurance remains Linux-only. |

Windows and macOS run a bounded native-sensitive selection in fresh Python interpreters. The explicit mapping in `run_product_validation.py` retains these former native groups:

| Coverage obligation | Retained target behaviour |
| --- | --- |
| `installation_cleanup` | First-use cleanup, idempotent status, dry-run defaults, and interrupted-cleanup convergence |
| `marketplace_package` | Deterministic complete bundles and self-contained marketplace package references |
| `package_cli` | Help-only CLI invocation without local-state writes |
| `heartbeat_process` | Coordinator lease renewal and worker-process cleanup |
| `git_crlf_drift` | Clean and mixed checkout authority, CRLF preservation, and raw-byte checkout overrides |
| `path_confinement` | Rejection of owned-path replacement through escaping symlinks |
| `public_delivery` | Reviewed proof, exact commit, and publication delivery graph |

The runner discovers real unittest identities before selection and rejects missing, duplicate, partial, or unexpected execution. Each native report records selected and executed counts, per-test and grouped timing, failures, errors, and evidenced coverage limits. None of the current 11 targets has an authentic skip-based native-facility probe, so the real worker rejects every unittest skip. Native facility failures, including unavailable symlink support, fail the leg and retain their traceback. The report validator accepts a coverage limit only when an injected observation identifies a selected test and supplies an explicit `unavailable_native_facility` reason and probe evidence.

The hosted legs are sixteen Linux shards plus one Windows, one macOS, and one Claude installed-cache job (nineteen runnable jobs before aggregation). The Linux matrix uses `fail-fast: false`. `dev-required-tests` continues to aggregate the four job results, including the entire Linux matrix result, through `require_validation.py`; any failed, cancelled, skipped or missing matrix execution prevents a successful required check.
