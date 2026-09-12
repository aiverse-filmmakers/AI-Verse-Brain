import json
import tempfile
import unittest
from pathlib import Path

from aiverse_brain.cadence_plan import plan_cadence
from aiverse_brain.doctor import run_doctor
from aiverse_brain.errors import ScopeError
from aiverse_brain.extension_registry import attach_brain, set_brain_enabled
from aiverse_brain.integration import HostMode, inspect_host, native_path_contract, plan_integration
from aiverse_brain.policy import BrainPolicy, ProactivityLevel
from aiverse_brain.storage import StorageLayout


def snapshot(root: Path):
    return sorted(str(path.relative_to(root)) for path in root.rglob("*") if path.is_file())


def make_native(root: Path, *, brain_slot=False, enabled=True):
    (root / "operator" / "context").mkdir(parents=True)
    (root / "operator" / "memory").mkdir(parents=True)
    (root / "operator" / "decisions").mkdir(parents=True)
    (root / "workspaces" / "alpha" / "context").mkdir(parents=True)
    (root / "workspaces" / "alpha" / "memory").mkdir(parents=True)
    (root / "workspaces" / "alpha" / "decisions").mkdir(parents=True)
    (root / "knowledge").mkdir()
    text = 'schema_version: "2.0"\narchitecture: unified-workspace\n'
    (root / "AI-VERSE.yaml").write_text(text, encoding="utf-8")
    if brain_slot:
        attach_brain(str(root))
        if not enabled:
            set_brain_enabled(str(root), False)


class HostDetectionTests(unittest.TestCase):
    def test_standalone_detection_is_read_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            before = snapshot(root)
            report = inspect_host(temp)
            plan = plan_integration(temp)
            after = snapshot(root)
            self.assertEqual(report.mode, HostMode.STANDALONE)
            self.assertTrue(plan.safe_to_apply)
            self.assertEqual(before, after)
            self.assertFalse((root / ".ai-verse-brain").exists())

    def test_native_detection_and_paths_are_read_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            make_native(root)
            before = snapshot(root)
            report = inspect_host(temp)
            operator = native_path_contract(temp, "operator")
            workspace = native_path_contract(temp, "workspace:alpha")
            after = snapshot(root)
            self.assertEqual(report.mode, HostMode.AI_VERSE_OS_V2)
            self.assertEqual(Path(operator.brain_state).parts[-2:], ("operator", "brain"))
            self.assertEqual(Path(workspace.current_context).parts[-4:], ("workspaces", "alpha", "context", "CURRENT.md"))
            self.assertEqual(before, after)
            self.assertFalse((root / ".ai-verse-brain").exists())

    def test_incompatible_ai_verse_refuses_standalone_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "operator").mkdir()
            (root / "workspaces").mkdir()
            (root / "AI-VERSE.yaml").write_text('schema_version: "1.0"\narchitecture: old-layout\n', encoding="utf-8")
            report = inspect_host(temp)
            self.assertEqual(report.mode, HostMode.INCOMPATIBLE_AI_VERSE)
            self.assertFalse(report.compatible)
            with self.assertRaises(ScopeError):
                StorageLayout.detect(root)
            self.assertFalse((root / ".ai-verse-brain").exists())

    def test_memory_detection_is_optional_and_read_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            make_native(root)
            marker = root / "scripts" / "ai-verse-memory" / "memory.py"
            marker.parent.mkdir(parents=True)
            marker.write_text("# fixture\n", encoding="utf-8")
            before = snapshot(root)
            report = inspect_host(temp)
            after = snapshot(root)
            self.assertTrue(report.memory_detected)
            self.assertEqual(before, after)

    def test_missing_brain_extension_is_blocker_not_implicit_patch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            make_native(root, brain_slot=False)
            before = (root / "AI-VERSE.yaml").read_text(encoding="utf-8")
            plan = plan_integration(temp)
            after = (root / "AI-VERSE.yaml").read_text(encoding="utf-8")
            self.assertFalse(plan.safe_to_apply)
            self.assertTrue(plan.blockers)
            self.assertEqual(before, after)

    def test_disabled_brain_registration_is_blocker(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            make_native(root, brain_slot=True, enabled=False)
            report = inspect_host(temp)
            plan = plan_integration(temp)
            self.assertTrue(report.brain_extension_slot)
            self.assertTrue(report.brain_supported)
            self.assertFalse(report.brain_enabled)
            self.assertFalse(report.brain_registration_valid)
            self.assertFalse(plan.safe_to_apply)
            self.assertTrue(any("enabled" in item for item in plan.blockers))

    def test_brain_extension_registration_unblocks_plan_without_writing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            make_native(root, brain_slot=True, enabled=True)
            before = snapshot(root)
            report = inspect_host(temp)
            plan = plan_integration(temp)
            after = snapshot(root)
            self.assertTrue(report.brain_registration_valid)
            self.assertTrue(plan.safe_to_apply)
            self.assertEqual(before, after)


class DoctorTests(unittest.TestCase):
    def test_doctor_warns_missing_slot_but_does_not_fail_native_host(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            make_native(root)
            report = run_doctor(temp)
            self.assertTrue(report.ok)
            severities = {item.name: item.severity for item in report.checks}
            self.assertEqual(severities["brain-attachment"], "WARN")

    def test_doctor_detects_cross_scope_state(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            make_native(root, brain_slot=True)
            directory = root / "workspaces" / "alpha" / "brain" / "initiatives"
            directory.mkdir(parents=True)
            (directory / "bad.json").write_text(json.dumps({"scope": "operator", "kind": "initiative"}), encoding="utf-8")
            report = run_doctor(temp)
            self.assertFalse(report.ok)
            self.assertTrue(any(item.name == "scope-isolation" and item.severity == "FAIL" for item in report.checks))


class CadencePlanTests(unittest.TestCase):
    def test_p0_has_no_scheduled_background_requests(self):
        policy = BrainPolicy(proactivity=ProactivityLevel.P0_REACTIVE)
        requests = plan_cadence(policy, "operator")
        self.assertEqual({item.delivery for item in requests}, {"event_hook"})

    def test_p2_background_interval_respects_tick_budget(self):
        policy = BrainPolicy(proactivity=ProactivityLevel.P2_ADVISORY)
        policy.resources.max_background_ticks_per_day = 4
        requests = plan_cadence(policy, "operator")
        orientation = next(item for item in requests if item.trigger_type == "scheduled_orientation")
        self.assertGreaterEqual(orientation.interval_seconds, 21600)

    def test_proactivity_does_not_change_action_policy(self):
        low = BrainPolicy(proactivity=ProactivityLevel.P0_REACTIVE)
        high = BrainPolicy(proactivity=ProactivityLevel.P4_DELEGATED)
        self.assertEqual(low.action_policy, high.action_policy)


if __name__ == "__main__":
    unittest.main()
