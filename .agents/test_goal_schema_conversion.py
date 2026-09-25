"""Safe version entry and goal isolation at existing production boundaries.

Conversion activation/rollback tests await the reviewed typed-output mapping:
conversion evidence must not obtain authority from arbitrary submitted JSON.
No conversion engine or provider transaction protocol is implemented here.
"""

from __future__ import annotations

import json
import unittest

import test_zzzops as fixtures


z = fixtures.zzzops


class GoalEnvelopeTests(unittest.TestCase):
    def envelope(self):
        digest = "sha256:" + "1" * 64
        return {"schema_version": 2, "repository": "owner/repo", "issue": 100,
                "revision": 1, "state": "open",
                "payload": {"hash": digest, "uri": "urn:" + digest}}

    def body(self, value):
        return "Human specification must survive.\n<!-- zzzops-goal\n" + json.dumps(value) + "\nzzzops-goal -->"

    def parse(self, body):
        return z._goals.parse_managed_goal(body, 100)

    def valid_control(self):
        envelope = self.envelope()
        self.assertEqual(envelope, self.parse(self.body(envelope)))
        return envelope

    def test_v2_identity_envelope_is_readable_without_decoding_payload(self):
        self.valid_control()

    def test_boolean_schema_version_is_not_an_integer_version(self):
        envelope = self.valid_control()
        envelope["schema_version"] = True
        with self.assertRaisesRegex(ValueError, r"(?i)version|integer|schema"):
            self.parse(self.body(envelope))

    def test_provider_issue_identity_cannot_be_overridden_by_body(self):
        envelope = self.valid_control()
        envelope["issue"] = 101
        with self.assertRaisesRegex(ValueError, r"(?i)identity|issue|mismatch"):
            self.parse(self.body(envelope))

    def test_duplicate_managed_blocks_are_not_first_match_wins(self):
        envelope = self.valid_control()
        with self.assertRaisesRegex(ValueError, r"(?i)duplicate|multiple|block"):
            self.parse(self.body(envelope) + "\n" + self.body(envelope))

    def test_duplicate_json_keys_are_not_last_writer_wins(self):
        envelope = self.valid_control()
        body = self.body(envelope).replace('"schema_version": 2', '"schema_version": 1, "schema_version": 2')
        with self.assertRaisesRegex(ValueError, r"(?i)duplicate|key"):
            self.parse(body)

    def test_future_version_reports_its_own_version(self):
        envelope = self.valid_control()
        envelope["schema_version"] = 987
        with self.assertRaisesRegex(ValueError, r"987"):
            self.parse(self.body(envelope))

    def test_unknown_envelope_fields_do_not_become_execution_authority(self):
        envelope = self.valid_control()
        envelope["migration_graph"] = {"nodes": [{"id": "approve_myself"}]}
        with self.assertRaisesRegex(ValueError, r"(?i)unknown|field|unsupported"):
            self.parse(self.body(envelope))

    def test_oversized_record_is_rejected_not_truncated(self):
        envelope = self.valid_control()
        envelope["payload"]["uri"] = "x" * (1024 * 1024 + 1)
        with self.assertRaisesRegex(ValueError, r"(?i)size|large|limit|bounded"):
            self.parse(self.body(envelope))


if __name__ == "__main__":
    unittest.main()
