# CI coverage

Linux remains the complete product-validation platform. Both Linux matrix jobs run the full `.agents` unittest discovery, migration-skill tests, manual coverage audit, plugin and release tests, prompt statistics, and Python compilation in their established order.

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

The five hosted legs remain two complete Linux matrix jobs plus one Windows, one macOS, and one Claude installed-cache job. `dev-required-tests` continues to aggregate the four job results, including the Linux matrix result, through `require_validation.py`.
