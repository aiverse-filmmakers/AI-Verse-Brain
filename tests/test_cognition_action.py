import shutil
import tempfile
import unittest
from pathlib import Path

from aiverse_brain.action_boundary import ActionExecutor, ActionRequest, ApprovalGrant
from aiverse_brain.authority import AuthorityTier
from aiverse_brain.cadence import Trigger
from aiverse_brain.cognition import CognitionContractError, CognitionProposal, CognitionPurpose, CognitionRequest, validate_proposal
from aiverse_brain.controller import BrainController
from aiverse_brain.errors import PermissionDenied, UncertainActionOutcome
from aiverse_brain.models import Scope
from aiverse_brain.orchestrator import TickPlanner
from aiverse_brain.policy import BrainPolicy, ProactivityLevel


class FakeHost:
    def __init__(self, response=None, error=None):
        self.response = response or {"status": "succeeded", "receipt_id": "receipt-1", "result": {"ok": True}}
        self.error = error
        self.calls = 0
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
        if self.error:
            raise self.error
        return dict(self.response)


class CognitionBoundaryTests(unittest.TestCase):
    def request(self):
        return CognitionRequest(
            purpose=CognitionPurpose.GAP_ANALYSIS,
            scope=Scope("operator"),
            context_refs=["context:current"],
            output_contract={"proposal_kinds": ["gap", "model_belief"]},
        )

    def test_scope_mismatch_is_rejected(self):
        request = self.request()
        proposal = CognitionProposal(
            request.request_id, request.purpose, Scope("workspace:other"), "gap",
            {"desired_state_refs": ["goal"], "current_state_refs": ["current"], "interpretation": "gap"},
            0.8, "model-x",
        )
        with self.assertRaises(CognitionContractError):
            validate_proposal(request, proposal)

    def test_policy_kind_cannot_be_proposed(self):
        request = self.request()
        with self.assertRaises(CognitionContractError):
            CognitionProposal(request.request_id, request.purpose, request.scope, "policy", {}, 0.8, "model-x")

    def test_privileged_nested_mutation_is_rejected(self):
        request = self.request()
        with self.assertRaises(CognitionContractError):
            CognitionProposal(
                request.request_id, request.purpose, request.scope, "model_belief",
                {"statement": "x", "nested": {"permission_matrix": {"send_message": "allow"}}},
                0.8, "model-x",
            )

    def test_output_contract_is_enforced(self):
        request = self.request()
        proposal = CognitionProposal(
            request.request_id, request.purpose, request.scope, "initiative",
            {"serves": ["goal"], "gap_refs": ["gap"], "hypothesis": "x", "outcome": "y", "score_components": {}},
            0.8, "model-x",
        )
        with self.assertRaises(CognitionContractError):
            validate_proposal(request, proposal)


class TickPlannerTests(unittest.TestCase):
    def test_scheduled_orientation_plans_cognition_but_no_model_or_tool_call(self):
        with tempfile.TemporaryDirectory() as temp:
            controller = BrainController(temp)
            planner = TickPlanner(controller)
            trigger = Trigger("scheduled_orientation", Scope("operator"), "tick-1")
            plan = planner.plan(trigger)
            self.assertEqual([item.purpose for item in plan.cognition_requests], [
                CognitionPurpose.ORIENT,
                CognitionPurpose.GAP_ANALYSIS,
                CognitionPurpose.OPPORTUNITY_DISCOVERY,
            ])
            self.assertTrue(all(item.scope.value == "operator" for item in plan.cognition_requests))


class ActionBoundaryTests(unittest.TestCase):
    def send_request(self):
        return ActionRequest(
            action_class="send_message",
            scope=Scope("operator"),
            operation="send",
            parameters={"to": "example", "text": "hello"},
            idempotency_key="send-1",
            in_scope=True,
            within_budget=True,
            reversible=False,
        )

    def approval(self, request):
        return ApprovalGrant.for_request(
            request,
            granted_by="user",
            authority=AuthorityTier.EXPLICIT_USER,
        )

    def test_p4_still_requires_approval_for_default_send_policy(self):
        with tempfile.TemporaryDirectory() as temp:
            policy = BrainPolicy(proactivity=ProactivityLevel.P4_DELEGATED)
            executor = ActionExecutor(Path(temp), policy)
            with self.assertRaises(PermissionDenied):
                executor.execute(self.send_request(), FakeHost(), host_idempotency_supported=True)

    def test_exact_approval_allows_side_effect_and_requires_host_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            request = self.send_request()
            host = FakeHost()
            executor = ActionExecutor(Path(temp), BrainPolicy())
            outcome = executor.execute(request, host, approval=self.approval(request), host_idempotency_supported=True)
            self.assertEqual(outcome.status, "succeeded")
            self.assertEqual(outcome.receipt_id, "receipt-1")
            self.assertEqual(host.calls, 1)

    def test_completed_side_effect_survives_runtime_deletion_without_reexecution(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            request = self.send_request()
            host = FakeHost()
            executor = ActionExecutor(root, BrainPolicy())
            executor.execute(request, host, approval=self.approval(request), host_idempotency_supported=True)
            shutil.rmtree(root / ".ai-verse-brain" / "runtime", ignore_errors=True)
            second_executor = ActionExecutor(root, BrainPolicy())
            outcome = second_executor.execute(request, host, approval=self.approval(request), host_idempotency_supported=True)
            self.assertTrue(outcome.duplicate)
            self.assertEqual(outcome.receipt_id, "receipt-1")
            self.assertEqual(host.calls, 1)

    def test_side_effect_success_without_receipt_becomes_uncertain_and_blocks_retry(self):
        with tempfile.TemporaryDirectory() as temp:
            request = self.send_request()
            host = FakeHost({"status": "succeeded", "result": {"ok": True}})
            executor = ActionExecutor(Path(temp), BrainPolicy())
            with self.assertRaises(UncertainActionOutcome):
                executor.execute(request, host, approval=self.approval(request), host_idempotency_supported=False)
            with self.assertRaises(UncertainActionOutcome):
                executor.execute(request, host, approval=self.approval(request), host_idempotency_supported=False)
            self.assertEqual(host.calls, 1)

    def test_uncertain_side_effect_can_be_reconciled_by_verified_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            request = self.send_request()
            host = FakeHost({"status": "uncertain"})
            executor = ActionExecutor(Path(temp), BrainPolicy())
            with self.assertRaises(UncertainActionOutcome):
                executor.execute(request, host, approval=self.approval(request), host_idempotency_supported=True)
            reconciled = executor.reconcile(
                request,
                status="succeeded",
                receipt_id="verified-receipt",
                source=AuthorityTier.VERIFIED_EVIDENCE,
            )
            self.assertEqual(reconciled.status, "succeeded")
            duplicate = executor.execute(request, host, approval=self.approval(request), host_idempotency_supported=True)
            self.assertTrue(duplicate.duplicate)
            self.assertEqual(duplicate.receipt_id, "verified-receipt")
            self.assertEqual(host.calls, 1)

    def test_weak_inference_cannot_reconcile_external_side_effect(self):
        with tempfile.TemporaryDirectory() as temp:
            request = self.send_request()
            executor = ActionExecutor(Path(temp), BrainPolicy())
            with self.assertRaises(UncertainActionOutcome):
                executor.execute(request, FakeHost({"status": "uncertain"}), approval=self.approval(request), host_idempotency_supported=True)
            with self.assertRaises(PermissionDenied):
                executor.reconcile(
                    request,
                    status="succeeded",
                    receipt_id="guessed",
                    source=AuthorityTier.TEMPORARY_HYPOTHESIS,
                )

    def test_host_exception_after_side_effect_dispatch_blocks_automatic_retry(self):
        with tempfile.TemporaryDirectory() as temp:
            request = self.send_request()
            host = FakeHost(error=RuntimeError("network lost after send"))
            executor = ActionExecutor(Path(temp), BrainPolicy())
            with self.assertRaises(UncertainActionOutcome):
                executor.execute(request, host, approval=self.approval(request), host_idempotency_supported=True)
            with self.assertRaises(UncertainActionOutcome):
                executor.execute(request, host, approval=self.approval(request), host_idempotency_supported=True)
            self.assertEqual(host.calls, 1)

    def test_read_local_can_execute_under_default_scope_policy_without_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            request = ActionRequest(
                action_class="read_local",
                scope=Scope("operator"),
                operation="read",
                parameters={"ref": "x"},
                idempotency_key="read-1",
                in_scope=True,
                reversible=True,
            )
            host = FakeHost({"status": "succeeded", "result": {"value": 1}})
            executor = ActionExecutor(Path(temp), BrainPolicy())
            outcome = executor.execute(request, host)
            self.assertEqual(outcome.status, "succeeded")
            self.assertEqual(host.calls, 1)


if __name__ == "__main__":
    unittest.main()
