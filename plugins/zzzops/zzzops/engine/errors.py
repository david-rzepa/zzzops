"""Error envelope and exit codes (SPEC §3.17)."""

from __future__ import annotations

EXIT = {}
for _code in ("usage validation not_found not_ready independence workspace_busy capacity budget_exceeded crash_loop "
              "mass_expiry goal_held goal_closed lease_held dirty_worktree sync_refused test_freeze checkpoint_required "
              "goal_changed fp_mismatch goal_rewritten goal_deleted too_large wrong_integration_branch engine_too_old "
              "engine_too_new engine_bug op_error environment").split():
    EXIT[_code] = 1
for _code in ("remote", "push_refused"):
    EXIT[_code] = 2
for _code in ("claim_lost", "superseded", "contention"):
    EXIT[_code] = 3
for _code in ("policy_branch", "policy_invalid", "not_bootstrapped"):
    EXIT[_code] = 4


class Refused(Exception):
    """A refusal with a code from SPEC §3.17; `exit` follows the code."""

    def __init__(self, code: str, message: str = "", hint: str | None = None, details: dict | None = None):
        if code not in EXIT:
            raise ValueError(f"unknown error code {code!r}")
        super().__init__(message or code)
        self.code = code
        self.message = message or code
        self.hint = hint
        self.details = details or {}

    @property
    def exit(self) -> int:
        return EXIT[self.code]

    def envelope(self, coordinator: dict | None = None) -> dict:
        error = {"code": self.code, "message": self.message, "details": self.details}
        if self.hint:
            error["hint"] = self.hint
        return {"ok": False, "error": error, "coordinator": coordinator or {}}


class EngineError(Exception):
    """An internal failure that must never be mistaken for an empty result (for example a failing git diff)."""
