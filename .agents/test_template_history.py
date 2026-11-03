"""G1024: published template bases remain available and correctly addressed.

The pinned seed is all 26 distinct template blobs published through c3791a0.
These tests inspect bytes, independent of Git history availability in a bundle.
Run `.agents/template_history.py --write` when changing a shipped default.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "plugins/zzzops/zzzops/templates/default"
HISTORY = TEMPLATE.parent / "history"
UPDATE = ".agents/template_history.py --write"
SEED = frozenset("""
016e8c0e465e73dd968e2d2badd720ea1bfbfbec
243c93eb589dfe1d3c3312ba69954887bb23d639
26b98429432907bc24a682eb186aaf7bf33039ce
2a22e817a86c35672f444cce8aeea72a07de86fe
2acc59e0fbbc5fc705a5150935b75e5e2a2ddd3a
39e1f12605627a3534aa37c4b201ed2f3c9baad8
4376779eb80606bbf98657c7c0cad969f2cc20a5
440dcbecceabb0d20fb9ae6169a80adc055f0347
448c0c48454f24f3e421fe4a3411787c746d944d
531ca51c4c4d5a3798813131e342476bbb905603
56e14121fb1986de2bb7641320f3451332e326a2
673d834dc6c8916916428da37e19bf4728d1a73e
6c00edb1cfc92f3f708a4afd9d5212674431338b
709c9925e1eee92ee05a70575e860df2cc7155c3
7cc76ad016a00b90ae675395099c8832d99c325d
84e4c3a1bf442728e2267fd4c43dbc4a5864ce48
8fc21c64839dd577617d9c8b89e131163bce4e95
915f555c952aaa18656d2776a02993ac23942404
91f3668f239b2b575d5a765cf072243d03dffa86
9b4f755befc154a65f3ad9f1b50709886876deb7
a6626809162d4989f39df8c0823bc0ae776d1bdc
b8ea24d2e9431dd4b4aa138d016cc3d70bfff55c
bb0768a46886afc4f55290f8d680241fd38f5eb0
c2c895badc0ed7c52bae18592240411eec7fbdb7
caf539abfa66f2b5daa2e3ae9edce2e3e5228008
efc61d15a3a0b5737521e28ad2ff092b4c49963a
""".split())


def blob(data):
    data = data.replace(b"\r\n", b"\n")
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


class TemplateHistoryTests(unittest.TestCase):
    def test_every_current_template_has_identical_history_bytes(self):
        missing = []
        for p in TEMPLATE.rglob("*"):
            if not p.is_file():
                continue
            data = p.read_bytes().replace(b"\r\n", b"\n")
            historical = HISTORY / (blob(data) + p.suffix)
            if not historical.is_file():
                missing.append(str(p.relative_to(TEMPLATE)))
            else:
                self.assertEqual(data, historical.read_bytes().replace(b"\r\n", b"\n"), str(p))
        self.assertFalse(missing, f"Missing template bases: {missing}; run {UPDATE}")

    def test_history_names_are_the_content_ids_and_seed_is_never_pruned(self):
        self.assertTrue(HISTORY.is_dir(), f"Missing template history; run {UPDATE}")
        ids = set()
        for p in HISTORY.iterdir():
            if not p.is_file():
                continue
            self.assertIn(p.suffix, {".md", ".json"}, str(p))
            self.assertEqual(blob(p.read_bytes()), p.stem, str(p))
            ids.add(p.stem)
        self.assertTrue(SEED <= ids, f"Published bases must never disappear: {sorted(SEED - ids)}")


if __name__ == "__main__":
    unittest.main()
