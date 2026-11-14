"""G1038 regression: squash release semantics come from declarations, not summary text."""
from __future__ import annotations

import merge_sync_fixtures as msf


class BreakingDeclarationTests(msf.OpFixture):
    def squash(self, message):
        self.publish({"src/declaration.py": "value = 1\n"}, message)
        result = self.integrate()
        head = self.pr_commits(result)[-1]
        return self.git.out("show", "-s", "--format=%B", head)

    def test_literal_bang_delimiter_in_summary_does_not_make_a_major_release(self):
        message = self.squash("fix: preserve literal !: delimiter")
        self.assertTrue(message.startswith("fix: "), message)
        self.assertIn("fix: preserve literal !: delimiter", message)

    def test_scoped_declaration_bang_makes_a_major_release(self):
        message = self.squash("fix(parser)!: change the accepted delimiter")
        self.assertTrue(message.startswith("fix!: "), message)

    def test_genuine_breaking_change_footer_is_retained(self):
        message = self.squash("fix: change delimiter\n\nBREAKING CHANGE: migrate saved inputs")
        self.assertTrue(message.startswith("fix!: "), message)
        self.assertIn("BREAKING CHANGE: migrate saved inputs", message)

    def test_genuine_hyphenated_breaking_change_footer_is_retained(self):
        message = self.squash("fix: change delimiter\n\nBREAKING-CHANGE: migrate saved inputs")
        self.assertTrue(message.startswith("fix!: "), message)
        self.assertIn("BREAKING-CHANGE: migrate saved inputs", message)
