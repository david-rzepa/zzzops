# G1024 test review, Windows portability correction

Approved. No new findings; the previous Python 3.10 cleanup finding remains resolved.

I reviewed the frozen checkpoint `7b18dbe704b32fe310a2421df2dd641f66c46036`, its interdiff from the previously approved tests, and the documented CLI PowerShell invocation rule.

- The checkpoint's product diff against integration contains only `.agents/test_engine_defaults.py` and `.agents/test_template_history.py`. It includes no engine implementation, history-store files or documentation changes. The previously restored source-free tree is therefore preserved in the frozen tests checkpoint.
- The correction changes only printed-command launching and fixture paths, and adds two small launcher probes. Original default-comparison, provenance, tombstone, preview and advisory assertions remain intact, as do the history checks and Python-3.10-compatible ExitStack cleanup.
- On Windows, the helper explicitly invokes `pwsh` or `powershell` with `shell=False`, `-NoProfile`, `-NonInteractive` and `-Command`; it prefixes the printed command with the documented `&` call operator while preserving a pre-existing operator. It does not pass PowerShell single-quoted commands to cmd.exe.
- Fixture paths now include spaces and apostrophes. The launcher preserves printed quoting, including doubled apostrophes in PowerShell single-quoted strings. POSIX retains the appropriate native shell path.
- I ran only the two independent launcher checks under Python 3.10: `python3.10 -m unittest discover -s .agents -p test_engine_defaults.py -k PrintedCommandTests`. Both passed in 0.005 seconds. The actual PowerShell probe supplied with the correction also passed. No full suite was repeated.

This addresses the platform harness issue without relaxing any feature assertion or changing implementation authority.
