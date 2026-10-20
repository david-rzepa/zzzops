"""Keep reviewed integration-to-contract coverage mappings executable."""
import json
from pathlib import Path
import unittest


class ContractCoverageMappingTests(unittest.TestCase):
    def test_every_mapped_contract_and_retained_integration_is_loadable(self):
        mapping = json.loads(Path(__file__).with_name("contract_test_coverage.json").read_text())
        self.assertEqual(1, mapping["schema_version"])
        self.assertTrue(mapping["replacements"])
        targets = set()
        for replacement in mapping["replacements"]:
            self.assertTrue(replacement["previous_tests"])
            self.assertTrue(replacement["guarantees"])
            self.assertTrue(replacement["contract_tests"])
            self.assertTrue(replacement["integration_tests"])
            targets.update(replacement["contract_tests"])
            targets.update(replacement["integration_tests"])
        loader = unittest.TestLoader()
        suite = loader.loadTestsFromNames(sorted(targets))
        self.assertEqual([], loader.errors)

        def identities(group):
            for test in group:
                if isinstance(test, unittest.TestSuite):
                    yield from identities(test)
                else:
                    yield test.id()

        actual = list(identities(suite))
        self.assertEqual(targets, set(actual))
        self.assertEqual(len(targets), len(actual))


if __name__ == "__main__":
    unittest.main()
