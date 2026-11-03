"""Keep scoped checkpoint cards readable when normal shrink steps are exhausted."""
import copy
import hashlib
import unittest

import engine_fixtures  # installs the engine import path
from engine import card
from engine.canon import canonical


class PreviewFallbackTests(unittest.TestCase):
    def test_last_preview_clip_preserves_checkpoint_and_full_blob_access(self):
        full = "Independent review guidance and measured verification details. " * 100
        data = full.encode()
        oid = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
        blobs = {oid: full}
        view = {"blob": oid, "read": f"git cat-file -p {oid}", "summary": full[:120]}
        checkpoint = {"commit": "a" * 40, "base": "b" * 40, "change": "c" * 40,
                      "diff": "git diff " + "b" * 40 + " " + "a" * 40 +
                              " -- ':/' ':(exclude,top,literal)tests/test_code.py'"}
        original = {"inputs": {"code": checkpoint}, "context": {"checks": view}, "padding": ""}
        original["padding"] = "x" * (card.CARD_LIMIT + 37 - len(canonical(original)))
        before = copy.deepcopy(original)
        result = card.shrink(original, None)
        self.assertLessEqual(len(canonical(result)), card.CARD_LIMIT)
        self.assertEqual(before, original)
        self.assertEqual(checkpoint, result["inputs"]["code"])
        clipped = result["context"]["checks"]
        self.assertEqual(view["blob"], clipped["blob"])
        self.assertEqual(view["read"], clipped["read"])
        self.assertEqual(full, blobs[clipped["read"].split()[-1]])
        self.assertEqual(80, len(clipped["summary"]))
        under_budget = {"context": {"checks": view}}
        self.assertEqual(under_budget, card.shrink(under_budget, None))


if __name__ == "__main__":
    unittest.main()
