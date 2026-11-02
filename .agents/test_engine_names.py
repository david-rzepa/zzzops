"""No default node id appears in engine source (DESIGN §10 item 3)."""

from __future__ import annotations

import re
import unittest

import engine_fixtures as fx


class NameIndependenceTests(unittest.TestCase):
    def test_engine_source_names_no_default_node(self):
        # `base` and `merge` are also SPEC-mandated words (the `base` input of checkpoint nodes, the checkpoint key,
        # settings.merge); the renamed-graph journeys cover them.
        names = [n for n in fx.DEFAULT_NODES if n not in ("base", "merge")]
        pattern = re.compile(r"[\"'](%s)[\"']" % "|".join(names))
        hits = []
        for path in sorted((fx.PLUGIN_CODE / "engine").rglob("*.py")):
            for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if pattern.search(line):
                    hits.append(f"{path.relative_to(fx.ROOT)}:{i}: {line.strip()}")
        self.assertEqual([], hits)

    def test_engine_source_names_no_shipped_node_and_no_lens(self):
        """G1022 test 12: the engine names neither a shipped (15-node) node id nor a lens: both come from the graph.
        `intent` (settings.intent) and `missing` (frontier) are engine vocabulary, like `base` and `merge`."""
        from test_engine_review_lenses import DESIGN_LENSES, IMPL_LENSES, SHIPPED_NODES
        names = [n for n in SHIPPED_NODES if n not in ("base", "merge")]
        names += [l for l in DESIGN_LENSES + IMPL_LENSES if l not in ("intent", "missing")]
        pattern = re.compile(r"[\"'](%s)[\"']" % "|".join(sorted(set(names))))
        hits = []
        for path in sorted((fx.PLUGIN_CODE / "engine").rglob("*.py")):
            for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if pattern.search(line):
                    hits.append(f"{path.relative_to(fx.ROOT)}:{i}: {line.strip()}")
        self.assertEqual([], hits)


if __name__ == "__main__":
    unittest.main()
