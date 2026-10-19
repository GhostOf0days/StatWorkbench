"""Vendored notice bytes must survive checkout on every build platform."""
import hashlib
import json
from pathlib import Path
import unittest


class BackendLicenseTests(unittest.TestCase):
    def test_upstream_notices_match_recorded_distribution_hashes(self):
        root = Path(__file__).resolve().parents[1] / "licenses" / "backend-upstream"
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        for package in manifest["packages"]:
            for notice in package["files"]:
                with self.subTest(package=package["name"], path=notice["path"]):
                    actual = hashlib.sha256((root / notice["path"]).read_bytes()).hexdigest()
                    self.assertEqual(actual, notice["sha256"], "Dependency notices must retain their original bytes, including line endings.")


if __name__ == "__main__":
    unittest.main()
