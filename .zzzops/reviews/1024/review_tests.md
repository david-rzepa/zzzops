# G1024 test review

Changes requested for one test portability defect. The behavior assertions otherwise exercise the approved design in useful detail, rather than only checking that a new module exists.

## Finding

`DefaultsCase.setUp` uses `self.enterContext` at lines 50, 66 and 67 of `.agents/test_engine_defaults.py`. `unittest.TestCase.enterContext` is unavailable in Python 3.10, which `.github/workflows/validate.yml` explicitly runs. I reproduced this with `python3.10 -m unittest discover -s .agents -p test_engine_defaults.py`: 16 tests in 0.003 seconds, including 14 setup errors with `AttributeError: ... has no attribute 'enterContext'`. Those errors will remain after implementing the feature and prevent the comparison tests from reaching their assertions.

Use Python-3.10-compatible cleanup management, for example a `contextlib.ExitStack` registered with `addCleanup` and its `enter_context` method, or explicit patch start/stop and temporary-directory cleanup. Re-run the new tests under 3.10 to ensure their red result reaches the intended missing implementation rather than failing on the test harness.

## Coverage assessment

The frozen diff was reviewed against approved design revision 4. Assertions check the observable directory-validation output, execute generated diff/merge commands under paths with spaces, check local-edit preservation and conflict markers, decline quieting, inferred provenance, added/removed/deleted files, malformed/newer records, CRLF normalization, unknown-base downgrade protection and removal tombstones across alternating plugin states. A single repository fixture checks committed-policy reads, previews, compact bounds and successful writes despite advisory notices. History checks validate bytes and pinned published bases. These checks would catch wrong classifications, unsafe downgrade/apply offers, lost tombstones, stale preview reads, blocked work and malformed merge commands even once imports exist.

The design explicitly calls for the existing skill/documentation acceptance checks; they add no Git journeys. The large majority of comparisons are in process, which is appropriate for this feature. No additional broad suite or timing threshold is requested.

No prior findings or owner decisions apply.
