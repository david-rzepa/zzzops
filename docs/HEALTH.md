# User health architecture

Health support is opt-in per user and never blocks authorized work. `.agents/zzzops_health.py` is a pure injected-clock policy; `.agents/zzzops.py` owns explicit user/machine paths, atomic JSON, the interactive editor, and `health status|check|record|reset`. `.zzzops/rules/HEALTH.md` supplies concise workflow hooks.

## Capability matrix

| Surface | Exact send time | Approximate receipt | Current clock | Storage |
| --- | --- | --- | --- | --- |
| Codex | Only when explicitly exposed by the active harness | Opt-in; agent records observed workflow receipt | Yes | Subject to task sandbox |
| Claude Code | Only when explicitly exposed by the active harness | Opt-in; agent records observed workflow receipt | Yes | Subject to process permissions |
| Tests/other harnesses | Explicit ISO input | Explicit ISO input | Injected/system UTC | Override directories supported |

Never scrape transcript/session files or relabel receipt time as send time. Without qualified activity, session-duration rules do not run; schedule rules may use the current clock. Missing IANA data and denied storage return explicit no-op capability results.

## Storage

| Platform | User preferences | Machine-local state |
| --- | --- | --- |
| Windows | `%APPDATA%\ZzzOps\health_preferences.json` | `%LOCALAPPDATA%\ZzzOps\health_state.json` |
| Linux | `$XDG_CONFIG_HOME/zzzops/health_preferences.json` or `~/.config/...` | `$XDG_STATE_HOME/zzzops/health_state.json` or `~/.local/state/...` |
| macOS | `~/Library/Application Support/ZzzOps/health_preferences.json` | `~/Library/Application Support/ZzzOps/health_state.json` |

`ZZZOPS_USER_CONFIG_DIR` and `ZZZOPS_MACHINE_STATE_DIR` override directories without changing the schema. State is created lazily and contains only session/last-activity instants, precision, cooldown/snooze instants, and per-reason counters. It never stores prompts, messages, or timestamp history. Reset deletes files; installers never create or overwrite them.

## Verification

- `test_zzzops_health.py`: policy, precedence, schedule/overnight windows, DST, retention, privacy, and missing capabilities.
- `test_zzzops_cli.py`: Windows/Linux/macOS paths, opt-in defaults, unknown-key preservation, denial, reset/cancel, and subprocess behavior.
- `test_zzzops_appdata.py`: atomic write-read-reset in isolated temporary directories inside real platform app-data roots.
- CI runs the live storage probe on Windows, Linux, and macOS.
