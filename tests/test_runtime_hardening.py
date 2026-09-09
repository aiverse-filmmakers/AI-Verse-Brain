import tempfile
import unittest

from aiverse_brain import AuthorityTier, BrainRuntime, Scope
from aiverse_brain.cadence import Trigger


class FakeHost:
    def read_context(self, scope):
        return {"scope": scope}
    def retrieve_history(self, query, scope):
        return []
    def list_capabilities(self, scope):
        return []
    def list_connections(self, scope):
        return []
    def request_action(self, request):
        raise AssertionError("cognition must not execute actions")
    def request_evaluation(self, request):
        return {}
    def schedule_trigger(self, trigger):
        return {}
    def cancel_trigger(self, trigger_id):
        return None
    def notify_user(self, notification):
        raise AssertionError("runtime must not notify implicitly")
    def write_route(self, classification, payload, scope):
        return None


class FabricatedGoalReasoner:
    model_id = "fabricated-goal"
    def reason(self, request, context):
        return {"proposals": [{
            "proposal_kind": "gap",
            "confidence": 0.9,
            "payload": {
                "desired_state_refs": ["brain:intent:not-a-real-goal"],
                "current_state_refs": ["host:current"],
                "interpretation": "Invent a goal and manufacture a gap.",
            },
        }]}


class BooleanConfidenceReasoner:
    model_id = "bool-confidence"
    def reason(self, request, context):
        return {"proposals": [{
            "proposal_kind": "gap",
            "confidence": True,
            "payload": {
                "desired_state_refs": ["brain:intent:any"],
                "current_state_refs": ["host:current"],
                "interpretation": "bad numeric contract",
            },
        }]}


class RuntimeHardeningTests(unittest.TestCase):
    def runtime_with_goal(self, temp):
        runtime = BrainRuntime(temp)
        runtime.controller.create(
            "intent", "operator", "CONFIRMED",
            {"subtype": "goal", "statement": "Real user goal"},
            source=AuthorityTier.EXPLICIT_USER, actor="user",
        )
        return runtime

    def test_valid_model_envelope_cannot_fabricate_desired_state(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = self.runtime_with_goal(temp)
            result = runtime.run_tick(
                Trigger("event", Scope("operator"), "fabricated-goal"),
                host=FakeHost(), reasoner=FabricatedGoalReasoner(),
            )
            self.assertFalse(result.ok)
            self.assertEqual(runtime.controller.store.list("gap", "operator"), [])
            self.assertTrue(any(item.stage == "proposal_application" for item in result.errors))

    def test_boolean_confidence_is_not_accepted_as_numeric(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = self.runtime_with_goal(temp)
            result = runtime.run_tick(
                Trigger("event", Scope("operator"), "bool-confidence"),
                host=FakeHost(), reasoner=BooleanConfidenceReasoner(),
            )
            self.assertFalse(result.ok)
            self.assertTrue(any("confidence must be numeric" in item.message for item in result.errors))


if __name__ == "__main__":
    unittest.main()
