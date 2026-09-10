import tempfile
import unittest
from pathlib import Path

from aiverse_brain.action_boundary import ActionExecutor, ActionRequest, ApprovalGrant
from aiverse_brain.errors import PermissionDenied
from aiverse_brain.models import Scope
from aiverse_brain.policy import BrainPolicy


class PermissionHost:
    def __init__(self, decisions=("allow",), *, malformed=False, wrong_fingerprint=False):
        self.decisions = list(decisions)
        self.malformed = malformed
        self.wrong_fingerprint = wrong_fingerprint
        self.permission_calls = 0
        self.action_calls = 0

    def authorize_action(self, request):
        self.permission_calls += 1
        if self.malformed:
            return {"decision": "allow"}
        index = min(self.permission_calls - 1, len(self.decisions) - 1)
        decision = self.decisions[index]
        return {
            "decision": decision,
            "request_fingerprint": "0" * 64 if self.wrong_fingerprint else request["request_fingerprint"],
            "scope": request["scope"],
            "action_class": request["action_class"],
            "source": "os:test-policy",
            "reason": f"test host decision: {decision}",
        }

    def request_action(self, request):
        self.action_calls += 1
        return {
            "status": "succeeded",
            "receipt_id": "intersection-receipt",
            "effect_occurred": True,
            "result": {"ok": True},
        }


def send_request(key="intersection-1"):
    return ActionRequest(
        action_class="send_message",
        scope=Scope("operator"),
        operation="send",
        parameters={"to": "example", "text": "hello"},
        idempotency_key=key,
        in_scope=True,
        within_budget=True,
        reversible=False,
    )


def brain_allows_send():
    policy = BrainPolicy()
    policy.action_policy["send_message"] = "allow_within_scope"
    return policy


class PermissionIntersectionAcceptanceTests(unittest.TestCase):
    def test_host_denial_blocks_even_when_brain_allows(self):
        with tempfile.TemporaryDirectory() as temp:
            host = PermissionHost(("deny",))
            executor = ActionExecutor(Path(temp), brain_allows_send())
            with self.assertRaises(PermissionDenied):
                executor.execute(send_request(), host, host_idempotency_supported=True)
            self.assertEqual(host.action_calls, 0)

    def test_brain_denial_blocks_even_when_host_allows(self):
        with tempfile.TemporaryDirectory() as temp:
            host = PermissionHost(("allow",))
            policy = BrainPolicy()
            policy.action_policy["send_message"] = "deny"
            executor = ActionExecutor(Path(temp), policy)
            with self.assertRaises(PermissionDenied):
                executor.execute(send_request(), host, host_idempotency_supported=True)
            self.assertEqual(host.action_calls, 0)

    def test_host_approval_requirement_adds_to_brain_policy(self):
        with tempfile.TemporaryDirectory() as temp:
            host = PermissionHost(("approval_required",))
            executor = ActionExecutor(Path(temp), brain_allows_send())
            with self.assertRaises(PermissionDenied):
                executor.execute(send_request(), host, host_idempotency_supported=True)
            self.assertEqual(host.action_calls, 0)

    def test_exact_user_approval_satisfies_host_requirement_without_weakening_brain(self):
        with tempfile.TemporaryDirectory() as temp:
            request = send_request()
            host = PermissionHost(("approval_required",))
            executor = ActionExecutor(Path(temp), brain_allows_send())
            outcome = executor.execute(
                request,
                host,
                approval=ApprovalGrant.for_request(request, granted_by="user"),
                host_idempotency_supported=True,
            )
            self.assertEqual(outcome.status, "succeeded")
            self.assertEqual(host.action_calls, 1)
            self.assertGreaterEqual(host.permission_calls, 2)

    def test_permission_is_rechecked_at_dispatch_and_late_revocation_prevents_effect(self):
        with tempfile.TemporaryDirectory() as temp:
            host = PermissionHost(("allow", "deny"))
            executor = ActionExecutor(Path(temp), brain_allows_send())
            outcome = executor.execute(send_request(), host, host_idempotency_supported=True)
            self.assertEqual(outcome.status, "failed")
            self.assertEqual(host.permission_calls, 2)
            self.assertEqual(host.action_calls, 0)

    def test_malformed_or_wrongly_bound_host_decision_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            for label, host in (
                ("malformed", PermissionHost(malformed=True)),
                ("wrong-fingerprint", PermissionHost(wrong_fingerprint=True)),
            ):
                with self.subTest(label=label):
                    executor = ActionExecutor(Path(temp), brain_allows_send())
                    with self.assertRaises(PermissionDenied):
                        executor.execute(send_request(label), host, host_idempotency_supported=True)
                    self.assertEqual(host.action_calls, 0)

    def test_host_without_permission_operation_fails_closed(self):
        class LegacyHost:
            def __init__(self):
                self.action_calls = 0

            def request_action(self, request):
                self.action_calls += 1
                return {"status": "succeeded", "receipt_id": "bad"}

        with tempfile.TemporaryDirectory() as temp:
            host = LegacyHost()
            executor = ActionExecutor(Path(temp), brain_allows_send())
            with self.assertRaises(PermissionDenied):
                executor.execute(send_request(), host, host_idempotency_supported=True)
            self.assertEqual(host.action_calls, 0)

    def test_completed_duplicate_never_dispatches_effect_twice(self):
        with tempfile.TemporaryDirectory() as temp:
            request = send_request()
            host = PermissionHost(("allow",))
            executor = ActionExecutor(Path(temp), brain_allows_send())
            first = executor.execute(request, host, host_idempotency_supported=True)
            second = executor.execute(request, host, host_idempotency_supported=True)
            self.assertEqual(first.status, "succeeded")
            self.assertTrue(second.duplicate)
            self.assertEqual(host.action_calls, 1)


if __name__ == "__main__":
    unittest.main()
