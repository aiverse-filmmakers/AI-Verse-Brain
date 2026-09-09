import tempfile
import unittest

from aiverse_brain import AuthorityTier, BrainRuntime, Scope
from aiverse_brain.cadence import Trigger
from aiverse_brain.errors import DuplicateTrigger
from aiverse_brain.policy import BrainPolicy, ProactivityLevel


SCORES = {
    "goal_alignment": 0.9,
    "expected_impact": 0.9,
    "urgency": 0.8,
    "strategic_leverage": 0.8,
    "readiness_4c": 0.8,
    "reversibility": 0.8,
    "effort_cost": 0.2,
    "attention_cost": 0.2,
    "risk": 0.2,
    "opportunity_cost": 0.2,
}


class FakeHost:
    def __init__(self):
        self.action_calls = 0
        self.notifications = 0

    def read_context(self, scope):
        return {"scope": scope, "current": "fixture"}

    def retrieve_history(self, query, scope):
        return [{"event": "one", "scope": scope}]

    def list_capabilities(self, scope):
        return [{"name": "read"}]

    def list_connections(self, scope):
        return [{"name": "fixture"}]

    def request_action(self, request):
        self.action_calls += 1
        return {"status": "succeeded", "receipt_id": "r1", "result": {}}

    def request_evaluation(self, request):
        return {}

    def schedule_trigger(self, trigger):
        return {}

    def cancel_trigger(self, trigger_id):
        return None

    def notify_user(self, notification):
        self.notifications += 1

    def write_route(self, classification, payload, scope):
        return None


class DirectionReasoner:
    model_id = "fixture-reasoner"

    def reason(self, request, context):
        purpose = request["purpose"]
        if purpose == "gap_analysis":
            goals = [item for item in context["brain_state"] if item["kind"] == "intent"]
            return {"proposals": [{
                "proposal_kind": "gap",
                "confidence": 0.8,
                "payload": {
                    "desired_state_refs": [f"brain:intent:{goals[0]['id']}"],
                    "current_state_refs": ["host:current"],
                    "interpretation": "Current state does not yet satisfy the confirmed goal.",
                },
            }]}
        if purpose == "opportunity_discovery":
            gaps = [item for item in context["brain_state"] if item["kind"] == "gap" and item["status"] == "ACTIVE"]
            if not gaps:
                return {"proposals": []}
            return {"proposals": [{
                "proposal_kind": "opportunity",
                "confidence": 0.85,
                "payload": {
                    "gap_refs": [gaps[0]["id"]],
                    "hypothesis": "A bounded initiative can close this gap.",
                    "score_components": dict(SCORES),
                },
            }]}
        return {"proposals": []}


class MaliciousReasoner:
    model_id = "malicious"

    def reason(self, request, context):
        return {"proposals": [{
            "proposal_kind": "gap",
            "confidence": 0.99,
            "payload": {
                "desired_state_refs": ["x"],
                "current_state_refs": ["y"],
                "interpretation": "x",
            },
            "scope": "workspace:other",
        }]}


class ObjectiveReasoner:
    model_id = "objective-reasoner"

    def __init__(self, intent_id, prepass=False):
        self.intent_id = intent_id
        self.prepass = prepass

    def reason(self, request, context):
        criterion = {"id": "c1", "statement": "Outcome exists"}
        if self.prepass:
            criterion["status"] = "passed"
            criterion["evidence_refs"] = ["fake"]
        return {"proposals": [{
            "proposal_kind": "objective",
            "confidence": 0.8,
            "payload": {
                "serves_ref": f"intent:{self.intent_id}",
                "outcome": "Produce the bounded result",
                "criteria": [criterion],
                "verification_factors": {"impact": 0.4},
                "budget": {"max_attempts": 999},
                "stall_threshold": 999,
            },
        }]}


class RuntimePipelineTests(unittest.TestCase):
    def create_runtime_with_goal(self, temp):
        runtime = BrainRuntime(temp, BrainPolicy(proactivity=ProactivityLevel.P2_ADVISORY))
        goal = runtime.controller.create(
            "intent",
            "operator",
            "CONFIRMED",
            {"subtype": "goal", "statement": "Reach the desired outcome"},
            source=AuthorityTier.EXPLICIT_USER,
            actor="user",
        )
        return runtime, goal

    def test_direction_tick_applies_gap_and_qualified_opportunity_without_notifying_host(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime, _ = self.create_runtime_with_goal(temp)
            host = FakeHost()
            result = runtime.run_tick(
                Trigger("scheduled_orientation", Scope("operator"), "runtime-1"),
                host=host,
                reasoner=DirectionReasoner(),
                session_id="s1",
            )
            self.assertTrue(result.ok)
            self.assertEqual(len(runtime.controller.store.list("gap", "operator")), 1)
            opportunities = runtime.controller.store.list("opportunity", "operator")
            self.assertEqual(len(opportunities), 1)
            self.assertEqual(opportunities[0].status, "QUALIFIED")
            self.assertEqual(host.notifications, 0)
            self.assertEqual(host.action_calls, 0)
            self.assertTrue(result.surface_items)

    def test_malicious_control_envelope_is_rejected_without_state_write(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime, _ = self.create_runtime_with_goal(temp)
            result = runtime.run_tick(
                Trigger("event", Scope("operator"), "runtime-malicious"),
                host=FakeHost(),
                reasoner=MaliciousReasoner(),
            )
            self.assertFalse(result.ok)
            self.assertEqual(runtime.controller.store.list("gap", "operator"), [])
            self.assertTrue(any(item.stage == "reasoner" for item in result.errors))

    def test_model_cannot_prepass_objective_criteria(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime, goal = self.create_runtime_with_goal(temp)
            bad = runtime.run_tick(
                Trigger("objective_wake", Scope("operator"), "objective-bad"),
                host=FakeHost(),
                reasoner=ObjectiveReasoner(goal.id, prepass=True),
            )
            self.assertFalse(bad.ok)
            self.assertEqual(runtime.controller.store.list("objective", "operator"), [])

            good = runtime.run_tick(
                Trigger("objective_wake", Scope("operator"), "objective-good"),
                host=FakeHost(),
                reasoner=ObjectiveReasoner(goal.id, prepass=False),
            )
            self.assertTrue(good.ok)
            objectives = runtime.controller.store.list("objective", "operator")
            self.assertEqual(len(objectives), 1)
            objective = objectives[0]
            self.assertEqual(objective.status, "QUEUED")
            self.assertEqual(objective.payload["criteria"][0]["status"], "unverified")
            self.assertEqual(objective.payload["verification_level"], "V1")
            self.assertEqual(objective.payload["budget"]["max_attempts"], runtime.policy.resources.max_objective_attempts)
            self.assertEqual(objective.payload["stall_threshold"], runtime.policy.resources.max_non_progressing_attempts_before_stall)

    def test_whole_tick_receipt_prevents_duplicate_replay(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime, _ = self.create_runtime_with_goal(temp)
            trigger = Trigger("scheduled_orientation", Scope("operator"), "runtime-dedupe")
            runtime.run_tick(trigger, host=FakeHost(), reasoner=DirectionReasoner())
            with self.assertRaises(DuplicateTrigger):
                runtime.run_tick(trigger, host=FakeHost(), reasoner=DirectionReasoner())


if __name__ == "__main__":
    unittest.main()
