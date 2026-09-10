import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiverse_brain.authority import AuthorityTier
from aiverse_brain.controller import BrainController
from aiverse_brain.direction_ownership import DirectionOwnershipService, read_registry
from aiverse_brain.errors import ValidationError
from aiverse_brain.installation import initialize
from aiverse_brain.onboarding import OnboardingService


def make_native(root: Path):
    (root / "operator" / "profile").mkdir(parents=True, exist_ok=True)
    (root / "operator" / "context").mkdir(parents=True, exist_ok=True)
    (root / "workspaces").mkdir(parents=True, exist_ok=True)
    (root / "AI-VERSE.yaml").write_text(
        'schema_version: "2.0"\n'
        'architecture: unified-workspace\n'
        'extensions:\n'
        '  brain:\n'
        '    supported: true\n'
        '    enabled: true\n',
        encoding="utf-8",
    )
    initialize(str(root))


class DirectionOwnershipAcceptanceTests(unittest.TestCase):
    def test_native_default_is_os_and_brain_onboarding_cannot_duplicate_strategy(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "host"
            root.mkdir()
            make_native(root)
            controller = BrainController(str(root))
            service = OnboardingService(controller)

            plan = service.plan("operator")
            self.assertEqual(plan.direction_owner, "os")
            self.assertFalse(plan.strategic_write_enabled)
            self.assertNotIn("desired_state", [q.key for q in plan.questions])
            with self.assertRaises(ValidationError):
                service.apply(
                    {"desired_state": "Ship the product", "success_definition": "It is adopted"},
                    "operator",
                )
            with self.assertRaises(ValidationError):
                controller.create(
                    "intent", "operator", "CONFIRMED",
                    {"subtype": "goal", "statement": "parallel goal"},
                    source=AuthorityTier.EXPLICIT_USER,
                    actor="user:test",
                )
            self.assertEqual(controller.store.list("intent", "operator"), [])

    def test_explicit_handover_imports_existing_os_goals_with_provenance(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "host"
            root.mkdir()
            make_native(root)
            goals = root / "operator" / "profile" / "goals.md"
            goals.write_text(
                "# Operator Goals\n\n## Current horizon\n\n- Launch alpha safely\n- Reach ten real users\n",
                encoding="utf-8",
            )
            current = root / "operator" / "context" / "CURRENT.md"
            current.write_text(
                "# Current Operator Context\n\n## Current priorities\n\n- Reach ten real users\n- Close launch blockers\n",
                encoding="utf-8",
            )
            original_goals = goals.read_bytes()
            original_current = current.read_bytes()

            controller = BrainController(str(root))
            ownership = DirectionOwnershipService(controller)
            plan = ownership.plan("operator")
            self.assertEqual(plan.current_owner, "os")
            self.assertEqual(
                [item.statement for item in plan.import_candidates],
                ["Launch alpha safely", "Reach ten real users", "Close launch blockers"],
            )
            with self.assertRaises(ValidationError):
                ownership.handover("operator", confirm_import=False)

            result = ownership.handover("operator", confirm_import=True)
            self.assertEqual(result.owner, "brain")
            self.assertEqual(result.state, "active")
            self.assertEqual(len(result.brain_refs), 3)
            self.assertEqual(goals.read_bytes(), original_goals)
            self.assertEqual(current.read_bytes(), original_current)

            intents = controller.store.list("intent", "operator", {"CONFIRMED", "ACTIVE"})
            self.assertEqual({i.payload["statement"] for i in intents}, {
                "Launch alpha safely", "Reach ten real users", "Close launch blockers",
            })
            for intent in intents:
                provenance = intent.payload["provenance"]
                self.assertEqual(provenance["source"], "ai-verse-os")
                self.assertTrue(provenance["source_sha256"])
                self.assertTrue(provenance["import_confirmed"])
            view = root / ".aiverse" / "direction" / "views" / "operator.md"
            self.assertTrue(view.is_file())
            self.assertIn("AI-Verse Brain is the strategic direction owner", view.read_text(encoding="utf-8"))

            onboard = OnboardingService(controller)
            after = onboard.plan("operator")
            self.assertEqual(after.direction_owner, "brain")
            self.assertTrue(after.strategic_write_enabled)
            applied = onboard.apply(
                {"desired_state": "A dependable launch", "success_definition": "Users retain after launch"},
                "operator",
            )
            self.assertEqual(len(applied.created_refs), 2)

    def test_interrupted_confirmation_never_reactivates_os_and_resumes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "host"
            root.mkdir()
            make_native(root)
            (root / "operator" / "profile" / "goals.md").write_text(
                "# Operator Goals\n\n## Current horizon\n\n- Preserve this goal\n",
                encoding="utf-8",
            )
            controller = BrainController(str(root))
            service = DirectionOwnershipService(controller)
            original_transition = controller.transition
            calls = {"count": 0}

            def fail_once(*args, **kwargs):
                calls["count"] += 1
                if calls["count"] == 1:
                    raise RuntimeError("simulated interruption after ownership flip")
                return original_transition(*args, **kwargs)

            with patch.object(controller, "transition", side_effect=fail_once):
                with self.assertRaises(RuntimeError):
                    service.handover("operator", confirm_import=True)

            registry = read_registry(root)
            self.assertEqual(registry["scopes"]["operator"]["owner"], "brain")
            self.assertEqual(registry["scopes"]["operator"]["state"], "activating")
            self.assertEqual(BrainController(str(root)).direction_owner("operator"), "brain")

            resumed = DirectionOwnershipService(BrainController(str(root))).handover(
                "operator", confirm_import=True
            )
            self.assertEqual(resumed.owner, "brain")
            self.assertEqual(resumed.state, "active")
            intents = BrainController(str(root)).store.list("intent", "operator", {"CONFIRMED"})
            self.assertEqual([i.payload["statement"] for i in intents], ["Preserve this goal"])

    def test_workspace_handover_is_scope_local_and_imports_objective(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "host"
            root.mkdir()
            make_native(root)
            ws = root / "workspaces" / "film"
            (ws / "context").mkdir(parents=True)
            (ws / "context" / "CURRENT.md").write_text(
                "# Current Workspace Context\n\n## Objective\n\nFinish the pilot with verified continuity.\n\n"
                "## Current state\n\nEditing.\n",
                encoding="utf-8",
            )

            controller = BrainController(str(root))
            result = DirectionOwnershipService(controller).handover(
                "workspace:film", confirm_import=True
            )
            self.assertEqual(result.owner, "brain")
            self.assertEqual(controller.direction_owner("workspace:film"), "brain")
            self.assertEqual(controller.direction_owner("operator"), "os")
            intents = controller.store.list("intent", "workspace:film", {"CONFIRMED"})
            self.assertEqual(len(intents), 1)
            self.assertEqual(intents[0].payload["subtype"], "desired_state")
            self.assertEqual(intents[0].payload["statement"], "Finish the pilot with verified continuity.")

    def test_malformed_owner_registry_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "host"
            root.mkdir()
            make_native(root)
            marker = root / ".aiverse" / "direction" / "ownership.json"
            marker.parent.mkdir(parents=True)
            marker.write_text('{"schema_version": 1, "scopes": {"operator": {"owner": "maybe"}}}\n', encoding="utf-8")
            controller = BrainController(str(root))
            with self.assertRaises(ValidationError):
                controller.direction_owner("operator")
            with self.assertRaises(ValidationError):
                OnboardingService(controller).apply({"goals": ["must not write"]}, "operator")
            self.assertEqual(controller.store.list("intent", "operator"), [])


if __name__ == "__main__":
    unittest.main()
