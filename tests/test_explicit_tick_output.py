import tempfile
import unittest

from aiverse_brain.authority import AuthorityTier
from aiverse_brain.cadence import Trigger
from aiverse_brain.host_selection import HostSelection
from aiverse_brain.models import Scope
from aiverse_brain.runtime import BrainRuntime
from aiverse_brain.tick_output import build_tick_summary


class QuietHost:
    def read_context(self, scope):
        return {"scope": scope, "current": "fixture"}

    def retrieve_history(self, query, scope):
        return []

    def list_capabilities(self, scope):
        return []

    def list_connections(self, scope):
        return []

    def request_action(self, request):
        raise AssertionError("tick orientation must not dispatch an action")

    def request_evaluation(self, request):
        return {}

    def schedule_trigger(self, trigger):
        return {}

    def cancel_trigger(self, trigger_id):
        return None

    def notify_user(self, notification):
        raise AssertionError("runtime must not notify the host implicitly")

    def write_route(self, classification, payload, scope):
        return None


class CountingReasoner:
    model_id = "counting-reasoner"

    def __init__(self):
        self.calls = 0

    def reason(self, request, context):
        self.calls += 1
        return {"proposals": []}


def selection(host):
    return HostSelection(
        host=host,
        mode="fixture-host",
        real_host=True,
        adapter_id="fixture:host",
        operations=("read_context", "retrieve_history", "list_capabilities", "list_connections"),
    )


class ExplicitTickOutputTests(unittest.TestCase):
    def test_explicit_tick_returns_useful_deterministic_orientation_without_reasoner_call(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = BrainRuntime(temp)
            goal = runtime.controller.create(
                "intent",
                "operator",
                "CONFIRMED",
                {"subtype": "goal", "statement": "Ship the current release safely"},
                source=AuthorityTier.EXPLICIT_USER,
                actor="user",
            )
            host = QuietHost()
            reasoner = CountingReasoner()
            result = runtime.run_tick(
                Trigger("explicit", Scope("operator"), "explicit-useful-output"),
                host=host,
                reasoner=reasoner,
            )
            summary = build_tick_summary(result, selection(host), runtime)

            self.assertTrue(summary["ok"])
            self.assertEqual(summary["reasoner_calls"], 0)
            self.assertEqual(reasoner.calls, 0)
            self.assertEqual(summary["orientation"]["mode"], "deterministic")
            self.assertIs(summary["orientation"]["reasoner_used"], False)
            self.assertIn(summary["orientation"]["direction_owner"], {"brain", "os"})
            goals = summary["orientation"]["state"]["goals"]
            self.assertEqual(goals["total"], 1)
            self.assertEqual(goals["items"][0]["id"], goal.id)
            self.assertEqual(goals["items"][0]["label"], "Ship the current release safely")
            self.assertEqual(summary["cognition"], [{
                "purpose": "orient",
                "mode": "deterministic_orientation",
                "proposal_kinds": [],
            }])
            self.assertEqual(summary["applied"], [])
            self.assertEqual(summary["surface_items"], [])

    def test_manual_and_scheduled_ticks_report_same_persisted_effective_policy(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = BrainRuntime(temp)
            runtime.controller.create(
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
            host = QuietHost()

            explicit = runtime.run_tick(
                Trigger("explicit", Scope("operator"), "policy-explicit"),
                host=host,
                reasoner=CountingReasoner(),
            )
            explicit_summary = build_tick_summary(explicit, selection(host), runtime)

            scheduled_reasoner = CountingReasoner()
            scheduled = runtime.run_tick(
                Trigger("scheduled_orientation", Scope("operator"), "policy-scheduled"),
                host=host,
                reasoner=scheduled_reasoner,
            )
            scheduled_summary = build_tick_summary(scheduled, selection(host), runtime)

            self.assertEqual(
                explicit_summary["orientation"]["effective_policy"],
                scheduled_summary["orientation"]["effective_policy"],
            )
            policy = explicit_summary["orientation"]["effective_policy"]
            self.assertEqual(policy["proactivity"], {"level": 0, "name": "P0_REACTIVE"})
            self.assertEqual(policy["max_background_ticks_per_day"], 1)
            self.assertEqual(scheduled_reasoner.calls, 2)
            self.assertEqual(scheduled_summary["cognition"][0]["mode"], "deterministic_orientation")
            self.assertEqual(scheduled_summary["cognition"][1]["mode"], "reasoner_proposals")

    def test_orientation_output_is_bounded_but_reports_full_counts(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = BrainRuntime(temp)
            for index in range(7):
                runtime.controller.create(
                    "intent",
                    "operator",
                    "CONFIRMED",
                    {"subtype": "goal", "statement": f"Goal {index}"},
                    source=AuthorityTier.EXPLICIT_USER,
                    actor="user",
                )
            host = QuietHost()
            result = runtime.run_tick(
                Trigger("explicit", Scope("operator"), "bounded-orientation"),
                host=host,
                reasoner=CountingReasoner(),
            )
            goals = build_tick_summary(result, selection(host), runtime)["orientation"]["state"]["goals"]
            self.assertEqual(goals["total"], 7)
            self.assertEqual(goals["shown"], 5)
            self.assertTrue(goals["truncated"])
            self.assertEqual(len(goals["items"]), 5)


if __name__ == "__main__":
    unittest.main()
