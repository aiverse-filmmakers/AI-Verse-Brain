import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas"


class SchemaContractTests(unittest.TestCase):
    def load_schema(self, name):
        return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))

    def test_every_schema_is_valid_json(self):
        files = sorted(SCHEMAS.glob("*.schema.json"))
        self.assertTrue(files)
        for path in files:
            with self.subTest(path=path.name):
                data = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(data.get("type"), "object")

    def test_slice2_schema_fields_match_engine_contract(self):
        opportunity = self.load_schema("opportunity.schema.json")["properties"]
        self.assertTrue({"cooldown_fingerprint", "score_components", "rank_result"}.issubset(opportunity))

        initiative = self.load_schema("initiative.schema.json")["properties"]
        self.assertTrue({"source_opportunity_ref", "source_fingerprint", "evaluation_refs"}.issubset(initiative))

        objective = self.load_schema("objective.schema.json")["properties"]
        self.assertTrue({"verification_level", "progress_ledger", "stall_threshold", "evaluation_refs"}.issubset(objective))
        self.assertEqual(objective["verification_level"]["enum"], ["V0", "V1", "V2", "V3"])

        evaluation = self.load_schema("evaluation.schema.json")
        self.assertTrue({"target_ref", "verification_level", "independence", "verdicts", "overall", "evaluator_id"}.issubset(evaluation["required"]))

        belief = self.load_schema("model-belief.schema.json")["properties"]
        self.assertTrue({"observed_at", "expires_at", "max_age_seconds", "contradiction_refs"}.issubset(belief))

        learning = self.load_schema("learning.schema.json")["properties"]
        self.assertTrue({"independent_observations", "controlled_evaluations", "contradiction_count", "evaluation_refs", "strategy_ref"}.issubset(learning))

        strategy = self.load_schema("strategy-rule.schema.json")["properties"]
        self.assertTrue({"regression_passed", "source_learning_ref", "evaluation_refs"}.issubset(strategy))

    def test_documented_verification_and_evolution_boundaries_exist(self):
        action = (ROOT / "protocol" / "ACTION-VERIFICATION.md").read_text(encoding="utf-8")
        self.assertIn("V3", action)
        self.assertIn("independent_model", action)
        learning = (ROOT / "protocol" / "LEARNING-EVOLUTION.md").read_text(encoding="utf-8")
        self.assertIn("E3 and E4 cannot be activated through runtime Brain state", learning)
        direction = (ROOT / "protocol" / "DIRECTION-ATTENTION.md").read_text(encoding="utf-8")
        self.assertIn("notification cooldown", direction)
        self.assertIn("Proactivity levels", direction)


class VersionParityTests(unittest.TestCase):
    def test_manifest_package_and_module_versions_are_in_sync(self):
        brain = (ROOT / "BRAIN.yaml").read_text(encoding="utf-8")
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        module = (ROOT / "engine" / "aiverse_brain" / "__init__.py").read_text(encoding="utf-8")
        self.assertRegex(brain, r'version: "0\.1\.0-alpha\.2"')
        self.assertRegex(pyproject, r'version = "0\.1\.0a2"')
        self.assertRegex(module, r'__version__ = "0\.1\.0a2"')

    def test_readme_does_not_claim_native_installation(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("have not been modified by Phase 4", readme)
        self.assertIn("Installer/registration work remains a later Phase 4 slice", readme)


if __name__ == "__main__":
    unittest.main()
