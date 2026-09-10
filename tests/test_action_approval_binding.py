import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from aiverse_brain.action_boundary import ActionExecutor, ActionRequest, ApprovalGrant
from aiverse_brain.errors import PermissionDenied
from aiverse_brain.models import Scope
from aiverse_brain.policy import BrainPolicy


class RecordingHost:
    def __init__(self):
        self.calls = 0
        self.requests = []
        self.permission_calls = 0

    def authorize_action(self, request):
        self.permission_calls += 1
        return {
            "decision": "allow",
            "request_fingerprint": request["request_fingerprint"],
            "scope": request["scope"],
            "action_class": request["action_class"],
            "source": "test-host",
            "reason": "fixture permits the action",
        }

    def request_action(self, request):
        self.calls += 1
        self.requests.append(request)
        return {
            "status": "succeeded",
            "receipt_id": "receipt-binding",
            "effect_occurred": True,
            "result": {"ok": True},
        }


class ApprovalBindingAcceptanceTests(unittest.TestCase):
    def request(self):
        return ActionRequest(
            action_class="send_message",
            scope=Scope("operator"),
            operation="send",
            parameters={
                "to": "alice@example.test",
                "amount": 10,
                "body": {"text": "approved body"},
                "target": "primary",
                "attachments": [{"id": "a1", "enabled": True}],
            },
            idempotency_key="binding-1",
            in_scope=True,
            within_budget=True,
            reversible=False,
            reason="user-approved send",
        )

    def test_parameters_are_deep_copied_and_frozen(self):
        source = {
            "to": "alice@example.test",
            "body": {"text": "approved body"},
            "attachments": [{"id": "a1"}],
        }
        request = ActionRequest(
            action_class="send_message",
            scope=Scope("operator"),
            operation="send",
            parameters=source,
            idempotency_key="freeze-1",
        )
        approved_fingerprint = request.fingerprint()

        source["to"] = "mallory@example.test"
        source["body"]["text"] = "changed"
        source["attachments"][0]["id"] = "changed"

        payload = request.to_dict()["parameters"]
        self.assertEqual(payload["to"], "alice@example.test")
        self.assertEqual(payload["body"]["text"], "approved body")
        self.assertEqual(payload["attachments"][0]["id"], "a1")
        self.assertEqual(request.fingerprint(), approved_fingerprint)

        with self.assertRaises(TypeError):
            request.parameters["to"] = "mallory@example.test"
        with self.assertRaises(TypeError):
            request.parameters["body"]["text"] = "changed"
        with self.assertRaises(TypeError):
            request.parameters["attachments"][0]["id"] = "changed"

    def test_recipient_amount_body_target_or_operation_change_invalidates_approval(self):
        original = self.request()
        approval = ApprovalGrant.for_request(original, granted_by="user")

        changed_parameters = []
        payload = original.to_dict()["parameters"]

        recipient = dict(payload)
        recipient["to"] = "mallory@example.test"
        changed_parameters.append(("recipient", replace(original, parameters=recipient)))

        amount = dict(payload)
        amount["amount"] = 999
        changed_parameters.append(("amount", replace(original, parameters=amount)))

        body = dict(payload)
        body["body"] = {"text": "different body"}
        changed_parameters.append(("body", replace(original, parameters=body)))

        target = dict(payload)
        target["target"] = "secondary"
        changed_parameters.append(("target", replace(original, parameters=target)))

        changed_parameters.append(("operation", replace(original, operation="forward")))

        for label, mutated in changed_parameters:
            with self.subTest(label=label):
                with self.assertRaises(PermissionDenied):
                    approval.assert_valid_for(mutated)

    def test_expired_grant_fails_even_when_policy_does_not_require_approval(self):
        request = ActionRequest(
            action_class="read_local",
            scope=Scope("operator"),
            operation="read",
            parameters={"path": "CURRENT.md"},
            idempotency_key="expired-allow-route",
            reversible=True,
        )
        expired = ApprovalGrant.for_request(
            request,
            granted_by="user",
            expires_at="2000-01-01T00:00:00+00:00",
        )
        host = RecordingHost()
        executor = ActionExecutor(Path(tempfile.mkdtemp()), BrainPolicy())

        with self.assertRaises(PermissionDenied):
            executor.execute(request, host, approval=expired)
        self.assertEqual(host.calls, 0)

    def test_unrelated_grant_cannot_bypass_non_idempotent_side_effect_requirement(self):
        request = self.request()
        other = replace(
            request,
            request_id="other-request",
            idempotency_key="other-idempotency",
            parameters={"to": "other@example.test", "body": {"text": "other"}},
        )
        unrelated = ApprovalGrant.for_request(other, granted_by="user")
        policy = BrainPolicy()
        policy.action_policy["send_message"] = "allow_within_scope"
        host = RecordingHost()

        with tempfile.TemporaryDirectory() as temp:
            executor = ActionExecutor(Path(temp), policy)
            with self.assertRaises(PermissionDenied):
                executor.execute(
                    request,
                    host,
                    approval=unrelated,
                    host_idempotency_supported=False,
                )
        self.assertEqual(host.calls, 0)

    def test_expired_grant_is_validated_even_on_completed_duplicate_route(self):
        request = self.request()
        host = RecordingHost()
        with tempfile.TemporaryDirectory() as temp:
            executor = ActionExecutor(Path(temp), BrainPolicy())
            executor.execute(
                request,
                host,
                approval=ApprovalGrant.for_request(request, granted_by="user"),
                host_idempotency_supported=True,
            )
            expired = ApprovalGrant.for_request(
                request,
                granted_by="user",
                expires_at="2000-01-01T00:00:00+00:00",
            )
            with self.assertRaises(PermissionDenied):
                executor.execute(
                    request,
                    host,
                    approval=expired,
                    host_idempotency_supported=True,
                )
        self.assertEqual(host.calls, 1)

    def test_request_fingerprint_is_rechecked_immediately_before_dispatch(self):
        request = self.request()
        approval = ApprovalGrant.for_request(request, granted_by="user")
        host = RecordingHost()

        with tempfile.TemporaryDirectory() as temp:
            executor = ActionExecutor(Path(temp), BrainPolicy())
            original_write = executor.ledger.write

            def mutate_after_claim(current_request, data):
                original_write(current_request, data)
                if data.get("ledger_status") == "claimed":
                    object.__setattr__(request, "operation", "tampered-after-authorization")

            executor.ledger.write = mutate_after_claim
            with self.assertRaises(PermissionDenied):
                executor.execute(
                    request,
                    host,
                    approval=approval,
                    host_idempotency_supported=True,
                )

        self.assertEqual(host.calls, 0)

    def test_approval_without_fingerprint_is_rejected(self):
        request = self.request()
        legacy_unbound = ApprovalGrant(
            request_id=request.request_id,
            idempotency_key=request.idempotency_key,
            scope=request.scope.value,
            action_class=request.action_class,
            granted_by="user",
        )
        with self.assertRaises(PermissionDenied):
            legacy_unbound.assert_valid_for(request)


if __name__ == "__main__":
    unittest.main()
