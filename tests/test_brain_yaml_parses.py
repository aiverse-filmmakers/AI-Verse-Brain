"""BRAIN.yaml must be real, parseable YAML (FL-27).

The old checks only searched the file's text, so a mis-indented line made the
whole file invalid YAML while every test still passed. This test parses it.
Brain itself has no dependencies; CI installs PyYAML for tests only. Locally the
test is skipped without PyYAML, but in CI (CI env var set) a missing parser fails.
"""
import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

try:
    import yaml
except ImportError:  # pragma: no cover - depends on the environment
    yaml = None


class BrainYamlParses(unittest.TestCase):
    def setUp(self):
        if yaml is None:
            if os.environ.get("CI"):
                self.fail("PyYAML is required in CI to check BRAIN.yaml")
            self.skipTest("PyYAML not installed")

    def test_manifest_is_valid_yaml_with_expected_shape(self):
        data = yaml.safe_load((ROOT / "BRAIN.yaml").read_text(encoding="utf-8"))
        self.assertIsInstance(data, dict)
        self.assertEqual(data["version"], "0.1.0-beta.3.dev0")
        self.assertEqual(data["status"], "development")
        self.assertEqual(data["state_schema_version"], "1.0")
        self.assertEqual(data["package"], {"name": "AI-Verse Brain", "python": ">=3.9"})
        self.assertIsInstance(data["principles"], dict)
        self.assertIn("ai-verse-os-v2", data["modes"])


if __name__ == "__main__":
    unittest.main()
