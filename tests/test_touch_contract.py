from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "actions" / "validate_touch.py"
SPEC = importlib.util.spec_from_file_location("validate_touch", VALIDATOR)
assert SPEC and SPEC.loader
validate_touch = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validate_touch
SPEC.loader.exec_module(validate_touch)


class TouchContractTests(unittest.TestCase):
    def test_catalog_report_manifest_modules_and_cache(self) -> None:
        self.assertEqual(validate_touch.validate(), [])

    def test_catalog_has_unique_stable_ids(self) -> None:
        catalog = validate_touch.document("data/catalog.json")
        ids = [test["id"] for test in catalog["tests"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(validate_touch.REQUIRED_TESTS.issubset(ids))

    def test_service_worker_cache_is_local_and_complete(self) -> None:
        self.assertEqual(validate_touch.validate_cache(), [])


if __name__ == "__main__":
    unittest.main()
