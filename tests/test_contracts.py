import json
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
        evaluation = self.load_schema("evaluation.schema.json")
        self.assertTrue({"target_ref", "verification_level", "independence", "verdicts", "overall", "evaluator_id"}.issubset(evaluation["required"]))

    def test_cognition_action_schemas_exist(self):
        cognition = self.load_schema("cognition-request.schema.json")
        proposal = self.load_schema("cognition-proposal.schema.json")
        action = self.load_schema("action-request.schema.json")
        self.assertIn("output_contract", cognition["required"])
        self.assertIn("proposal_kind", proposal["required"])
        self.assertIn("idempotency_key", action["required"])

    def test_shipment_schemas_exist(self):
        installation = self.load_schema("installation.schema.json")
        onboarding = self.load_schema("onboarding-answers.schema.json")
        adapter = self.load_schema("adapter-config.schema.json")
        self.assertTrue({"state_schema_version", "package_version", "installation_id"}.issubset(installation["required"]))
        self.assertFalse(installation["additionalProperties"])
        self.assertFalse(onboarding["additionalProperties"])
        self.assertIn("desired_state", onboarding["properties"])
        self.assertIn("success_definition", onboarding["properties"])
        self.assertFalse(adapter["additionalProperties"])
        self.assertEqual(adapter["properties"]["transport"]["const"], "json-subprocess")
        self.assertEqual(adapter["properties"]["command"]["type"], "array")
        self.assertTrue(adapter["properties"]["env_names"]["uniqueItems"])

    def test_protocol_boundaries_exist(self):
        integration = (ROOT / "protocol" / "INTEGRATION-CADENCE.md").read_text(encoding="utf-8")
        self.assertIn("refuses standalone fallback", integration)
        boundary = (ROOT / "protocol" / "COGNITION-ACTION-BOUNDARY.md").read_text(encoding="utf-8")
        self.assertIn("model response is never itself canonical Brain state", boundary)
        self.assertIn("automatic retries remain forbidden", boundary)
        runtime = (ROOT / "protocol" / "RUNTIME-PIPELINE.md").read_text(encoding="utf-8")
        self.assertIn("does not call `host.notify_user` automatically", runtime)
        self.assertIn("Every criterion starts `unverified`", runtime)
        self.assertIn("Cognition proposals cannot become `ActionRequest` objects implicitly", runtime)
        shipment = (ROOT / "protocol" / "INSTALLATION-ONBOARDING.md").read_text(encoding="utf-8")
        self.assertIn("The installer MUST NOT", shipment)
        self.assertIn("There is no destructive implicit migration path", shipment)
        self.assertIn("Only answers supplied through an explicit onboarding apply operation", shipment)
        adapter = (ROOT / "protocol" / "ADAPTER-BRIDGE.md").read_text(encoding="utf-8")
        self.assertIn("shell=False", adapter)
        self.assertIn("stores environment variable **names**, never credential values", adapter)
        self.assertIn("cannot bypass Brain action permissions", adapter)
        self.assertIn("fails closed", adapter)


class VersionParityTests(unittest.TestCase):
    def test_manifest_package_and_python_version_source_are_in_sync(self):
        brain = (ROOT / "BRAIN.yaml").read_text(encoding="utf-8")
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        version = (ROOT / "engine" / "aiverse_brain" / "_version.py").read_text(encoding="utf-8")
        module = (ROOT / "engine" / "aiverse_brain" / "__init__.py").read_text(encoding="utf-8")
        installer = (ROOT / "engine" / "aiverse_brain" / "installation.py").read_text(encoding="utf-8")
        self.assertIn('version: "0.1.0-alpha.7"', brain)
        self.assertIn('state_schema_version: "1.0"', brain)
        self.assertIn('__version__ = "0.1.0a7"', version)
        self.assertIn('DISPLAY_VERSION = "0.1.0-alpha.7"', version)
        self.assertIn('STATE_SCHEMA_VERSION = "1.0"', version)
        self.assertIn('dynamic = ["version"]', pyproject)
        self.assertIn('version = {attr = "aiverse_brain._version.__version__"}', pyproject)
        self.assertIn('from ._version import __version__', module)
        self.assertIn('PACKAGE_VERSION = __version__', installer)

    def test_readme_preserves_repository_separation_and_install_safety(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        runtime = (ROOT / "protocol" / "RUNTIME-PIPELINE.md").read_text(encoding="utf-8")
        self.assertIn("Nothing in this work has been installed into or merged with AI-Verse OS or AI-Verse Memory", readme)
        self.assertIn("reports a blocker rather than editing `AI-VERSE.yaml` implicitly", readme)
        self.assertIn("does not call `host.notify_user` automatically", runtime)
        self.assertIn("No state is written by that command", readme)
        self.assertIn("advertising an operation never grants authority", readme)


if __name__ == "__main__":
    unittest.main()
