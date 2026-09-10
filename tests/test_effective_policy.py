import tempfile
import unittest
from pathlib import Path

from aiverse_brain.action_boundary import ActionRequest
from aiverse_brain.authority import AuthorityTier
from aiverse_brain.cadence import Trigger
from aiverse_brain.cadence_hooks import render_cadence_hooks
from aiverse_brain.controller import BrainController
from aiverse_brain.errors import PermissionDenied, ValidationError
from aiverse_brain.installation import initialize
from aiverse_brain.models import BrainObject, Scope
from aiverse_brain.policy import BrainPolicy, ProactivityLevel
from aiverse_brain.runtime import BrainRuntime
from aiverse_brain.storage import ObjectStore, StorageLayout


class NoopHost:
    def __init__(self):
        self.action_calls = 0

    def read_context(self, scope):
        return {"scope": scope}

    def retrieve_history(self, query, scope):
        return []

    def list_capabilities(self, scope):
        return []

    def list_connections(self, scope):
        return []

    def request_action(self, request):
        self.action_calls += 1
        return {"status": "succeeded", "effect_occurred": False, "result": {}}

    def request_evaluation(self, request):
        return {}

    def schedule_trigger(self, trigger):
        return {}

    def cancel_trigger(self, trigger_id):
        return None

    def notify_user(self, notification):
        return None

    def write_route(self, classification, payload, scope):
        return None


class NoopReasoner:
    model_id = "noop"

    def reason(self, request, context):
        return {"proposals": []}


class EffectivePolicyTests(unittest.TestCase):
    @staticmethod
    def persist_restrictive_policy(root):
        controller = BrainController(root)
        policy = controller.create(
            "policy",
            "operator",
            "ACTIVE",
            {
                "proactivity": "P0",
                "action_policy": {"read_local": "deny"},
                "resources": {"max_background_ticks_per_day": 1},
            },
            source=AuthorityTier.EXPLICIT_USER,
            actor="user",
        )
        return controller, policy

    def test_persisted_denial_survives_restart_cadence_and_runtime(self):
        with tempfile.TemporaryDirectory() as temp:
            controller, _ = self.persist_restrictive_policy(temp)
            self.assertEqual(controller.policy.proactivity, ProactivityLevel.P0_REACTIVE)
            self.assertEqual(controller.policy.action_decision("read_local"), "deny")

            restarted = BrainController(temp)
            self.assertEqual(restarted.policy.proactivity, ProactivityLevel.P0_REACTIVE)
            self.assertEqual(restarted.policy.action_decision("read_local"), "deny")

            hooks = render_cadence_hooks(temp, vendor="codex")
            self.assertEqual([item["trigger_type"] for item in hooks], ["session_start", "session_end"])

            runtime = BrainRuntime(temp)
            runtime.run_tick(
                Trigger("scheduled_orientation", Scope("operator"), "persisted-policy-cadence"),
                host=NoopHost(),
                reasoner=NoopReasoner(),
            )
            self.assertEqual(runtime.policy.proactivity, ProactivityLevel.P0_REACTIVE)
            self.assertEqual(runtime.policy.action_decision("read_local"), "deny")

            host = NoopHost()
            request = ActionRequest(
                action_class="read_local",
                scope=Scope("operator"),
                operation="read_context",
                parameters={"path": "CURRENT.md"},
                idempotency_key="persisted-denial",
                reversible=True,
            )
            with self.assertRaises(PermissionDenied):
                runtime.execute_action(request, host=host)
            self.assertEqual(host.action_calls, 0)

    def test_runtime_reloads_policy_after_approved_update(self):
        with tempfile.TemporaryDirectory() as temp:
            controller = BrainController(temp)
            persisted = controller.create(
                "policy",
                "operator",
                "ACTIVE",
                {"proactivity": "P2", "action_policy": {"read_local": "allow_within_scope"}},
                source=AuthorityTier.EXPLICIT_USER,
                actor="user",
            )
            runtime = BrainRuntime(temp)

            runtime.controller.update_policy(
                persisted.id,
                "operator",
                {"proactivity": "P0", "action_policy": {"read_local": "deny"}},
                source=AuthorityTier.EXPLICIT_USER,
                actor="user",
            )

            host = NoopHost()
            request = ActionRequest(
                action_class="read_local",
                scope=Scope("operator"),
                operation="read_context",
                parameters={},
                idempotency_key="reload-after-policy-update",
                reversible=True,
            )
            with self.assertRaises(PermissionDenied):
                runtime.execute_action(request, host=host)
            self.assertEqual(runtime.policy.proactivity, ProactivityLevel.P0_REACTIVE)
            self.assertEqual(runtime.policy.action_decision("read_local"), "deny")
            self.assertEqual(host.action_calls, 0)

    def test_cadence_override_cannot_weaken_canonical_policy(self):
        with tempfile.TemporaryDirectory() as temp:
            self.persist_restrictive_policy(temp)
            with self.assertRaises(ValidationError):
                render_cadence_hooks(temp, vendor="codex", proactivity=2)

    def test_caller_policy_override_may_not_weaken_canonical_policy(self):
        with tempfile.TemporaryDirectory() as temp:
            self.persist_restrictive_policy(temp)
            with self.assertRaises(ValidationError):
                BrainController(temp, policy=BrainPolicy())

    def test_workspace_policy_cannot_weaken_operator_restriction(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "operator").mkdir()
            (root / "workspaces" / "a").mkdir(parents=True)
            (root / "AI-VERSE.yaml").write_text(
                'schema_version: "2.0"\narchitecture: unified-workspace\nextensions:\n  brain:\n    supported: true\n    enabled: true\n',
                encoding="utf-8",
            )
            initialize(str(root))
            controller = BrainController(str(root))
            controller.create(
                "policy",
                "operator",
                "ACTIVE",
                {"action_policy": {"read_local": "deny"}},
                source=AuthorityTier.EXPLICIT_USER,
                actor="user",
            )
            with self.assertRaises(ValidationError):
                controller.create(
                    "policy",
                    "workspace:a",
                    "ACTIVE",
                    {"action_policy": {"read_local": "allow_within_scope"}},
                    source=AuthorityTier.EXPLICIT_USER,
                    actor="user",
                )

    def test_malformed_or_conflicting_active_policies_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            layout = StorageLayout(Path(temp), "standalone")
            store = ObjectStore(layout)
            malformed = BrainObject.new(
                "policy",
                "operator",
                "ACTIVE",
                {"action_policy": {"not_an_action": "deny"}},
                created_by="fixture",
            )
            store.save(malformed, expected_revision=-1)
            with self.assertRaises(ValidationError):
                BrainController(temp)

        with tempfile.TemporaryDirectory() as temp:
            layout = StorageLayout(Path(temp), "standalone")
            store = ObjectStore(layout)
            for value in ("P0", "P1"):
                obj = BrainObject.new("policy", "operator", "ACTIVE", {"proactivity": value}, created_by="fixture")
                store.save(obj, expected_revision=-1)
            with self.assertRaises(ValidationError):
                BrainController(temp)


if __name__ == "__main__":
    unittest.main()
