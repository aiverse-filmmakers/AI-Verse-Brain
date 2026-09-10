import json
import tempfile
import unittest
from pathlib import Path

from aiverse_brain.authority import AuthorityTier
from aiverse_brain.cadence import Trigger
from aiverse_brain.cli import main as cli_main
from aiverse_brain.controller import BrainController
from aiverse_brain.errors import ValidationError
from aiverse_brain.installation import initialize, plan_init
from aiverse_brain.integration import plan_integration
from aiverse_brain.models import Scope


def make_native(root: Path, *, supported=None, enabled=None, schema="2.0", architecture="unified-workspace"):
    (root / "operator").mkdir(parents=True, exist_ok=True)
    (root / "workspaces").mkdir(parents=True, exist_ok=True)
    lines = [f'schema_version: "{schema}"', f"architecture: {architecture}"]
    if supported is not None or enabled is not None:
        lines.extend(["extensions:", "  brain:"])
        if supported is not None:
            lines.append(f"    supported: {'true' if supported else 'false'}")
        if enabled is not None:
            lines.append(f"    enabled: {'true' if enabled else 'false'}")
    (root / "AI-VERSE.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def tree_snapshot(root: Path):
    items = []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_dir():
            items.append((rel, "dir", None))
        elif path.is_file():
            items.append((rel, "file", path.read_bytes()))
        else:
            items.append((rel, "other", None))
    return items


def confirmed_goal(controller: BrainController, statement="ship safely"):
    return controller.create(
        "intent",
        "operator",
        "CONFIRMED",
        {"subtype": "goal", "statement": statement},
        source=AuthorityTier.EXPLICIT_USER,
        actor="user:test",
    )


class NativeWriteReadinessAcceptanceTests(unittest.TestCase):
    def assert_sdk_write_blocked_without_changes(self, root: Path):
        before = tree_snapshot(root)
        controller = BrainController(str(root))
        self.assertEqual(tree_snapshot(root), before, "constructing a controller must be read-only")
        with self.assertRaises(ValidationError):
            confirmed_goal(controller)
        self.assertEqual(tree_snapshot(root), before)
        self.assertFalse((root / ".ai-verse-brain").exists())
        self.assertFalse((root / "operator" / "brain").exists())
        self.assertFalse((root / "runtime" / "ai-verse-brain").exists())

    def test_missing_registration_blocks_sdk_and_bootstrap_before_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "host"
            root.mkdir()
            make_native(root)
            before = tree_snapshot(root)
            self.assertFalse(plan_integration(str(root)).safe_to_apply)
            self.assertFalse(plan_init(str(root)).safe_to_apply)
            with self.assertRaises(ValidationError):
                initialize(str(root))
            self.assertEqual(tree_snapshot(root), before)
            self.assert_sdk_write_blocked_without_changes(root)

    def test_disabled_registration_blocks_sdk_and_bootstrap_before_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "host"
            root.mkdir()
            make_native(root, supported=True, enabled=False)
            before = tree_snapshot(root)
            self.assertFalse(plan_integration(str(root)).safe_to_apply)
            self.assertFalse(plan_init(str(root)).safe_to_apply)
            with self.assertRaises(ValidationError):
                initialize(str(root))
            self.assertEqual(tree_snapshot(root), before)
            self.assert_sdk_write_blocked_without_changes(root)

    def test_unsupported_registration_blocks_sdk_and_bootstrap_before_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "host"
            root.mkdir()
            make_native(root, supported=False, enabled=True)
            before = tree_snapshot(root)
            self.assertFalse(plan_integration(str(root)).safe_to_apply)
            self.assertFalse(plan_init(str(root)).safe_to_apply)
            with self.assertRaises(ValidationError):
                initialize(str(root))
            self.assertEqual(tree_snapshot(root), before)
            self.assert_sdk_write_blocked_without_changes(root)

    def test_enabled_registration_without_initialization_blocks_normal_sdk_and_runtime_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "host"
            root.mkdir()
            make_native(root, supported=True, enabled=True)
            self.assertTrue(plan_integration(str(root)).safe_to_apply)
            self.assertTrue(plan_init(str(root)).safe_to_apply)
            before = tree_snapshot(root)
            controller = BrainController(str(root))
            self.assertEqual(tree_snapshot(root), before)
            with self.assertRaises(ValidationError):
                confirmed_goal(controller)
            trigger = Trigger("explicit", Scope("operator"), "readiness:uninitialized")
            with self.assertRaises(ValidationError):
                controller.trigger_ledger.claim(trigger)
            self.assertEqual(tree_snapshot(root), before)

    def test_initialization_is_the_only_native_bootstrap_exception(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "host"
            root.mkdir()
            make_native(root, supported=True, enabled=True)
            result = initialize(str(root))
            self.assertTrue(result.created)
            self.assertTrue((root / "operator" / "brain" / "installation.json").is_file())
            saved = confirmed_goal(BrainController(str(root)))
            self.assertEqual(saved.status, "CONFIRMED")
            self.assertTrue((root / "operator" / "brain" / "intent" / f"{saved.id}.json").is_file())

    def test_disabling_registration_after_init_blocks_sdk_runtime_and_cli_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "host"
            root.mkdir()
            make_native(root, supported=True, enabled=True)
            initialize(str(root))
            first = confirmed_goal(BrainController(str(root)), "first goal")
            manifest = root / "AI-VERSE.yaml"
            manifest.write_text(
                'schema_version: "2.0"\narchitecture: unified-workspace\nextensions:\n  brain:\n    supported: true\n    enabled: false\n',
                encoding="utf-8",
            )
            before = tree_snapshot(root)

            controller = BrainController(str(root))
            self.assertEqual(tree_snapshot(root), before)
            with self.assertRaises(ValidationError):
                confirmed_goal(controller, "must not persist")
            trigger = Trigger("explicit", Scope("operator"), "readiness:disabled")
            with self.assertRaises(ValidationError):
                controller.trigger_ledger.claim(trigger)
            self.assertEqual(tree_snapshot(root), before)

            answers = base / "answers.json"
            answers.write_text(
                json.dumps(
                    {
                        "desired_state": "do not write while disabled",
                        "success_definition": "no new native Brain state",
                    }
                ),
                encoding="utf-8",
            )
            rc = cli_main(["onboard", str(root), "--answers", str(answers), "--apply"])
            self.assertEqual(rc, 2)
            self.assertEqual(tree_snapshot(root), before)
            self.assertTrue((root / "operator" / "brain" / "intent" / f"{first.id}.json").is_file())

    def test_incompatible_ai_verse_host_never_gets_parallel_or_native_brain_state(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "host"
            root.mkdir()
            make_native(root, supported=True, enabled=True, schema="3.0")
            before = tree_snapshot(root)
            self.assertFalse(plan_integration(str(root)).safe_to_apply)
            self.assertFalse(plan_init(str(root)).safe_to_apply)
            with self.assertRaises(ValidationError):
                initialize(str(root))
            self.assertEqual(tree_snapshot(root), before)
            self.assertFalse((root / ".ai-verse-brain").exists())
            self.assertFalse((root / "operator" / "brain").exists())


if __name__ == "__main__":
    unittest.main()
