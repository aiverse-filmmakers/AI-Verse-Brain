import json
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import aiverse_brain.direction_ownership as direction_ownership

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

    def test_explicit_handback_exports_brain_direction_before_returning_os_ownership(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "host"
            root.mkdir()
            make_native(root)
            current = root / "operator" / "context" / "CURRENT.md"
            current.write_text(
                "# Current Operator Context\n\n"
                "## Current priorities\n\n- Initial OS direction\n\n"
                "## Current state\n\nRelease hardening is active.\n",
                encoding="utf-8",
            )

            controller = BrainController(str(root))
            ownership = DirectionOwnershipService(controller)
            ownership.handover("operator", confirm_import=True)
            OnboardingService(controller).apply(
                {
                    "desired_state": "A shipped dependable beta",
                    "success_definition": "Real members can install and use it safely",
                    "goals": ["Finish release hardening"],
                    "boundaries": ["Never silently reactivate stale strategy"],
                    "constraints": ["Preserve canonical user state"],
                },
                "operator",
            )

            plan = ownership.plan_return_to_os("operator")
            self.assertTrue(plan.can_handover)
            self.assertEqual(plan.current_owner, "brain")
            self.assertEqual(plan.target_path, "operator/context/CURRENT.md")
            self.assertGreaterEqual(len(plan.export_items), 5)
            with self.assertRaises(ValidationError):
                ownership.handback_to_os("operator", confirm_export=False)

            result = ownership.handback_to_os("operator", confirm_export=True)
            self.assertEqual(result.owner, "os")
            self.assertEqual(controller.direction_owner("operator"), "os")

            text = current.read_text(encoding="utf-8")
            self.assertIn("## Current priorities", text)
            self.assertIn("- Desired state: A shipped dependable beta", text)
            self.assertIn("- Goal: Finish release hardening", text)
            self.assertIn("## Current state\n\nRelease hardening is active.", text)

            registry = read_registry(root)
            record = registry["scopes"]["operator"]
            self.assertEqual(record["owner"], "os")
            self.assertEqual(record["state"], "active")
            self.assertTrue(record["export_confirmed"])
            self.assertTrue(record["brain_export_path"].startswith(".aiverse/direction/exports/"))
            self.assertTrue((root / record["brain_export_path"]).is_file())
            self.assertEqual(record["os_source_path"], "operator/context/CURRENT.md")

            intents = controller.store.list("intent", "operator", {"CONFIRMED", "ACTIVE"})
            self.assertGreaterEqual(len(intents), 5)

    def test_interrupted_handback_never_flips_owner_before_os_strategy_exists(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "host"
            root.mkdir()
            make_native(root)
            current = root / "operator" / "context" / "CURRENT.md"
            current.write_text(
                "# Current Operator Context\n\n"
                "## Current priorities\n\n- Keep release safe\n\n"
                "## Current state\n\nOperational.\n",
                encoding="utf-8",
            )
            controller = BrainController(str(root))
            service = DirectionOwnershipService(controller)
            service.handover("operator", confirm_import=True)

            original_write = direction_ownership._atomic_json_write

            def fail_owner_flip(root_arg, target, data):
                record = data.get("scopes", {}).get("operator", {})
                if record.get("owner") == "os":
                    raise RuntimeError("simulated interruption before owner flip")
                return original_write(root_arg, target, data)

            with patch.object(direction_ownership, "_atomic_json_write", side_effect=fail_owner_flip):
                with self.assertRaises(RuntimeError):
                    service.handback_to_os("operator", confirm_export=True)

            self.assertEqual(BrainController(str(root)).direction_owner("operator"), "brain")
            self.assertIn("- Goal: Keep release safe", current.read_text(encoding="utf-8"))

            resumed = DirectionOwnershipService(BrainController(str(root))).handback_to_os(
                "operator", confirm_export=True
            )
            self.assertEqual(resumed.owner, "os")
            self.assertEqual(BrainController(str(root)).direction_owner("operator"), "os")

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

    def test_concurrent_workspace_handovers_preserve_both_registry_records(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "host"
            root.mkdir()
            make_native(root)
            for workspace_id in ("alpha", "beta"):
                current = root / "workspaces" / workspace_id / "context" / "CURRENT.md"
                current.parent.mkdir(parents=True)
                current.write_text(
                    "# Current Workspace Context\n\n## Current state\n\nOperational only.\n",
                    encoding="utf-8",
                )

            original_write = direction_ownership._atomic_json_write
            first_write_started = threading.Event()
            release_first_write = threading.Event()
            write_counter_lock = threading.Lock()
            write_counter = {"count": 0}

            def hold_first_registry_write(*args, **kwargs):
                with write_counter_lock:
                    write_counter["count"] += 1
                    call_number = write_counter["count"]
                if call_number == 1:
                    first_write_started.set()
                    if not release_first_write.wait(timeout=5):
                        raise RuntimeError("timed out waiting to release first ownership registry write")
                return original_write(*args, **kwargs)

            start = threading.Barrier(2)

            def handover(workspace_id):
                controller = BrainController(str(root))
                service = DirectionOwnershipService(controller)
                start.wait(timeout=5)
                return service.handover(f"workspace:{workspace_id}", confirm_import=True)

            with patch.object(direction_ownership, "_atomic_json_write", side_effect=hold_first_registry_write):
                with ThreadPoolExecutor(max_workers=2) as pool:
                    alpha = pool.submit(handover, "alpha")
                    beta = pool.submit(handover, "beta")
                    self.assertTrue(first_write_started.wait(timeout=5))
                    time.sleep(0.1)
                    release_first_write.set()
                    alpha_result = alpha.result(timeout=10)
                    beta_result = beta.result(timeout=10)

            self.assertEqual(alpha_result.owner, "brain")
            self.assertEqual(beta_result.owner, "brain")
            restarted = BrainController(str(root))
            registry = read_registry(root)
            self.assertEqual(registry["scopes"]["workspace:alpha"]["owner"], "brain")
            self.assertEqual(registry["scopes"]["workspace:alpha"]["state"], "active")
            self.assertEqual(registry["scopes"]["workspace:beta"]["owner"], "brain")
            self.assertEqual(registry["scopes"]["workspace:beta"]["state"], "active")
            self.assertEqual(restarted.direction_owner("workspace:alpha"), "brain")
            self.assertEqual(restarted.direction_owner("workspace:beta"), "brain")

    def test_interrupted_resume_cannot_erase_concurrent_other_scope_handover(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "host"
            root.mkdir()
            make_native(root)

            alpha_current = root / "workspaces" / "alpha" / "context" / "CURRENT.md"
            alpha_current.parent.mkdir(parents=True)
            alpha_current.write_text(
                "# Current Workspace Context\n\n"
                "## Objective\n\nPreserve Alpha direction through recovery.\n\n"
                "## Current state\n\nOperational.\n",
                encoding="utf-8",
            )
            beta_current = root / "workspaces" / "beta" / "context" / "CURRENT.md"
            beta_current.parent.mkdir(parents=True)
            beta_current.write_text(
                "# Current Workspace Context\n\n## Current state\n\nOperational.\n",
                encoding="utf-8",
            )

            interrupted_controller = BrainController(str(root))
            interrupted_service = DirectionOwnershipService(interrupted_controller)
            original_transition = interrupted_controller.transition
            transition_calls = {"count": 0}

            def fail_first_confirmation(*args, **kwargs):
                transition_calls["count"] += 1
                if transition_calls["count"] == 1:
                    raise RuntimeError("simulated interruption after Alpha ownership flip")
                return original_transition(*args, **kwargs)

            with patch.object(interrupted_controller, "transition", side_effect=fail_first_confirmation):
                with self.assertRaises(RuntimeError):
                    interrupted_service.handover("workspace:alpha", confirm_import=True)

            interrupted_registry = read_registry(root)
            self.assertEqual(interrupted_registry["scopes"]["workspace:alpha"]["owner"], "brain")
            self.assertEqual(interrupted_registry["scopes"]["workspace:alpha"]["state"], "activating")

            original_write = direction_ownership._atomic_json_write
            first_write_started = threading.Event()
            release_first_write = threading.Event()
            write_counter_lock = threading.Lock()
            write_counter = {"count": 0}

            def hold_first_recovery_write(*args, **kwargs):
                with write_counter_lock:
                    write_counter["count"] += 1
                    call_number = write_counter["count"]
                if call_number == 1:
                    first_write_started.set()
                    if not release_first_write.wait(timeout=5):
                        raise RuntimeError("timed out waiting to release recovery registry write")
                return original_write(*args, **kwargs)

            start = threading.Barrier(2)

            def resume_alpha():
                controller = BrainController(str(root))
                service = DirectionOwnershipService(controller)
                start.wait(timeout=5)
                return service.handover("workspace:alpha", confirm_import=True)

            def handover_beta():
                controller = BrainController(str(root))
                service = DirectionOwnershipService(controller)
                start.wait(timeout=5)
                return service.handover("workspace:beta", confirm_import=True)

            with patch.object(direction_ownership, "_atomic_json_write", side_effect=hold_first_recovery_write):
                with ThreadPoolExecutor(max_workers=2) as pool:
                    alpha = pool.submit(resume_alpha)
                    beta = pool.submit(handover_beta)
                    self.assertTrue(first_write_started.wait(timeout=5))
                    time.sleep(0.1)
                    release_first_write.set()
                    alpha_result = alpha.result(timeout=10)
                    beta_result = beta.result(timeout=10)

            self.assertEqual(alpha_result.state, "active")
            self.assertEqual(beta_result.state, "active")
            restarted = BrainController(str(root))
            registry = read_registry(root)
            for scope in ("workspace:alpha", "workspace:beta"):
                self.assertEqual(registry["scopes"][scope]["owner"], "brain")
                self.assertEqual(registry["scopes"][scope]["state"], "active")
                self.assertEqual(restarted.direction_owner(scope), "brain")

            alpha_intents = restarted.store.list("intent", "workspace:alpha", {"CONFIRMED"})
            self.assertEqual(len(alpha_intents), 1)
            self.assertEqual(
                alpha_intents[0].payload["statement"],
                "Preserve Alpha direction through recovery.",
            )

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
