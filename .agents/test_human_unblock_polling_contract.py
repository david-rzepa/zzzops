import re
import unittest
from pathlib import Path


UNBLOCK = Path(__file__).parent / "skills" / "execute-zzzops" / "references" / "UNBLOCK.md"


class HumanUnblockPollingContractTests(unittest.TestCase):
    def test_polling_window_is_bounded(self):
        text = UNBLOCK.read_text(encoding="utf-8")
        match = re.search(r"poll cadence: (\d+) seconds; maximum window: (\d+) seconds", text)
        self.assertIsNotNone(match)
        cadence, window = map(int, match.groups())
        self.assertGreaterEqual(cadence, 15)
        self.assertGreaterEqual(window, cadence)
        self.assertLessEqual(window, 300)
        self.assertLessEqual(window // cadence, 10)


if __name__ == "__main__":
    unittest.main()
