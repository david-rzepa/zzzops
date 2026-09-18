import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parent.parent / "plugins" / "zzzops" / "zzzops" / "zzzops.py"
SPEC = importlib.util.spec_from_file_location("zzzops_migration_acceptance", MODULE_PATH)
zzzops = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(zzzops)


def policy(status: str | None = "never_released") -> dict:
    settings = {} if status is None else {"legacy_migration": {"release_status": status}}
    return {"sections": [{"id": "git_review_release", "configuration": settings}]}


class MigrationAcceptanceTests(unittest.TestCase):
    def test_release_evidence_and_reset_boundaries(self):
        released = {"status": "released"}
        never = {"status": "never_released"}
        unknown = {"status": "unknown"}
        self.assertEqual("preserve", zzzops.migration_boundary(policy("released"), released)["action"])
        self.assertEqual("all_state", zzzops.migration_boundary(policy("released"), released)["scope"])
        self.assertEqual("replace_reset", zzzops.migration_boundary(policy("never_released"), never)["action"])
        self.assertEqual("affected_project_owned", zzzops.migration_boundary(policy("never_released"), never)["scope"])
        for candidate in (
            zzzops.migration_boundary(policy("never_released"), released),
            zzzops.migration_boundary(policy("never_released"), unknown),
            zzzops.migration_boundary(policy(None), never),
        ):
            self.assertEqual("block", candidate["action"])
            self.assertEqual("none", candidate["scope"])

    def test_conflicting_release_evidence_never_authorizes_reset(self):
        conflicting = zzzops._policy.classify_release_evidence(
            visibility="PUBLIC", github_releases=[{"draft": False, "published_at": "2026-09-01T00:00:00Z"}],
            owner_declaration="never_released",
        )
        self.assertEqual("released", conflicting["status"])
        self.assertEqual("block", zzzops.migration_boundary(policy("never_released"), conflicting)["action"])


if __name__ == "__main__":
    unittest.main()
