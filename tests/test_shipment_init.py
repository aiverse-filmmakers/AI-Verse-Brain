import json
import tempfile
import unittest
from pathlib import Path

from aiverse_brain.controller import BrainController
from aiverse_brain.doctor import run_doctor
from aiverse_brain.errors import ValidationError
from aiverse_brain.installation import initialize, plan_init, read_installation_marker
from aiverse_brain.onboarding import OnboardingService


class ShipmentInitializationTests(unittest.TestCase):
    def test_standalone_init_is_dry_run_by_default_plan(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            plan = plan_init(str(root))
            self.assertTrue(plan.safe_to_apply)
            self.assertEqual(plan.mode.value, "standalone")
            self.assertFalse((root / ".ai-verse-brain").exists())
            self.assertIn(str(root / ".ai-verse-brain"), plan.creates)

    def test_standalone_initialize_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = initialize(str(root))
            self.assertTrue(first.created)
            installation_id = first.marker["installation_id"]
            second = initialize(str(root))
            self.assertFalse(second.created)
            self.assertEqual(second.marker["installation_id"], installation_id)
            self.assertTrue((root / ".ai-verse-brain" / "installation.json").is_file())
            self.assertTrue((root / ".ai-verse-brain" / "runtime").is_dir())

    def test_newer_state_schema_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            initialize(str(root))
            marker = root / ".ai-verse-brain" / "installation.json"
            data = json.loads(marker.read_text(encoding="utf-8"))
            data["state_schema_version"] = "9.0"
            marker.write_text(json.dumps(data), encoding="utf-8")
            plan = plan_init(str(root))
            self.assertFalse(plan.safe_to_apply)
            self.assertTrue(any("newer" in item for item in plan.blockers))
            with self.assertRaises(ValidationError):
                initialize(str(root))

    def test_incompatible_ai_verse_never_falls_back_to_standalone(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "AI-VERSE.yaml").write_text(
                'schema_version: "1.0"\narchitecture: legacy\n', encoding="utf-8"
            )
            plan = plan_init(str(root))
            self.assertFalse(plan.safe_to_apply)
            self.assertEqual(plan.mode.value, "incompatible-ai-verse")
            self.assertFalse((root / ".ai-verse-brain").exists())

    def test_native_ai_verse_without_brain_slot_is_blocked_without_patch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest = 'schema_version: "2.0"\narchitecture: unified-workspace\n'
            (root / "AI-VERSE.yaml").write_text(manifest, encoding="utf-8")
            (root / "operator").mkdir()
            (root / "workspaces").mkdir()
            plan = plan_init(str(root))
            self.assertFalse(plan.safe_to_apply)
            self.assertTrue(any("extensions.brain" in item for item in plan.blockers))
            self.assertEqual((root / "AI-VERSE.yaml").read_text(encoding="utf-8"), manifest)
            self.assertFalse((root / "operator" / "brain").exists())

    def test_native_ai_verse_with_slot_initializes_only_brain_owned_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest = (
                'schema_version: "2.0"\n'
                'architecture: unified-workspace\n'
                'extensions:\n'
                '  brain:\n'
                '    supported: true\n'
            )
            (root / "AI-VERSE.yaml").write_text(manifest, encoding="utf-8")
            (root / "operator").mkdir()
            (root / "workspaces").mkdir()
            result = initialize(str(root))
            self.assertTrue(result.created)
            self.assertTrue((root / "operator" / "brain" / "installation.json").is_file())
            self.assertTrue((root / "runtime" / "ai-verse-brain").is_dir())
            self.assertEqual((root / "AI-VERSE.yaml").read_text(encoding="utf-8"), manifest)
            self.assertFalse((root / ".ai-verse-brain").exists())


class OnboardingShipmentTests(unittest.TestCase):
    def answers(self):
        return {
            "desired_state": "Ship a reliable intelligence layer",
            "success_definition": "The system measurably closes important gaps without violating user authority",
            "goals": ["Reach public beta"],
            "boundaries": ["Never silently change user goals"],
            "constraints": ["Remain local-first"],
            "practices": ["Review initiatives weekly"],
        }

    def test_onboarding_requires_explicit_direction_and_success(self):
        with tempfile.TemporaryDirectory() as temp:
            initialize(temp)
            service = OnboardingService(BrainController(temp))
            plan = service.plan()
            keys = {item.key for item in plan.questions if item.required}
            self.assertEqual(keys, {"desired_state", "success_definition"})
            with self.assertRaises(ValidationError):
                service.apply({"goals": ["Do something"]})

    def test_onboarding_is_explicit_and_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            initialize(temp)
            service = OnboardingService(BrainController(temp))
            first = service.apply(self.answers())
            self.assertTrue(first.created_refs)
            self.assertTrue(first.plan.complete_enough_to_orient)
            second = service.apply(self.answers())
            self.assertEqual(second.created_refs, [])
            self.assertEqual(len(second.existing_refs), 6)

            controller = BrainController(temp)
            desired = [
                item for item in controller.store.list("intent", "operator", {"CONFIRMED", "ACTIVE"})
                if item.payload.get("subtype") == "desired_state"
            ]
            self.assertEqual(len(desired), 1)
            self.assertEqual(desired[0].created_by, "user:onboarding")

    def test_onboarding_rejects_unknown_fields(self):
        with tempfile.TemporaryDirectory() as temp:
            initialize(temp)
            service = OnboardingService(BrainController(temp))
            answers = self.answers()
            answers["permission_matrix"] = {"send_message": "allow"}
            with self.assertRaises(ValidationError):
                service.apply(answers)

    def test_doctor_reports_installation_and_onboarding_readiness(self):
        with tempfile.TemporaryDirectory() as temp:
            initialize(temp)
            before = run_doctor(temp)
            onboarding_before = [item for item in before.checks if item.name == "onboarding"]
            self.assertEqual(onboarding_before[0].severity, "WARN")

            OnboardingService(BrainController(temp)).apply(self.answers())
            report = run_doctor(temp)
            checks = {item.name: item for item in report.checks}
            self.assertEqual(checks["installation"].severity, "PASS")
            self.assertEqual(checks["onboarding"].severity, "PASS")
            marker = read_installation_marker(temp)
            self.assertIsNotNone(marker)


if __name__ == "__main__":
    unittest.main()
