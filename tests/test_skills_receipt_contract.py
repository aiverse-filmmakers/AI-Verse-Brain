from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aiverse_brain.action_boundary import ActionExecutor, ActionRequest
from aiverse_brain.authority import AuthorityTier
from aiverse_brain.controller import BrainController
from aiverse_brain.errors import EvaluationError, UncertainActionOutcome, ValidationError
from aiverse_brain.models import EvidenceRef, Scope
from aiverse_brain.policy import BrainPolicy
from aiverse_brain.skills_receipt import (
    SkillsExecutionIdentity,
    apply_receipt_to_objective,
    evaluation_from_receipt,
    translate_action_receipt,
)


DIGEST = "b" * 64
IDENTITY = SkillsExecutionIdentity(
    capability_id="aiverse-skills:demo-skill",
    generation_id="gen-20260910T120000000000Z-deadbeef",
    package_digest_sha256=DIGEST,
)


def request(*, key="skills-receipt-1", action_class="send_message"):
    return ActionRequest(
        action_class=action_class,
        scope=Scope("operator"),
        operation="demo.operation",
        parameters={"value": "hello"},
        idempotency_key=key,
        in_scope=True,
        within_budget=True,
        reversible=False,
    )


def receipt_for(req, *, status="success", effect_state=None, effect_source=None):
    side_effect = req.is_side_effect
    if effect_state is None:
        effect_state = "occurred" if side_effect else "not_occurred"
    if effect_source is None:
        effect_source = "ai_verse_os" if side_effect else "skill_runtime"
    return {
        "contract": "aiverse-execution-receipt-v2",
        "receipt_id": f"receipt-{req.idempotency_key}",
        "status": status,
        "summary": "skill execution result",
        "binding": {
            "request_fingerprint": req.fingerprint(),
            "scope": req.scope.value,
            "action_class": req.action_class,
            "operation": req.operation,
            "provider_id": "aiverse-skills",
            "capability_id": IDENTITY.capability_id,
            "generation_id": IDENTITY.generation_id,
            "package_digest": {
                "algorithm": "aiverse-package-sha256-v1",
                "value": IDENTITY.package_digest_sha256,
            },
        },
        "effect": {
            "state": effect_state,
            "source_kind": effect_source,
            "source_ref": "os-effect:1" if effect_source == "ai_verse_os" else "skill-run:1",
            "independence": "same_context",
        },
        "verification_context": {
            "evaluator_id": "skills-runtime",
            "independence": "same_context",
        },
        "verification": [],
        "warnings": [],
        "remaining_uncertainty": [],
        "trace_id": f"trace-{req.idempotency_key}",
    }


def allow_send_policy():
    policy = BrainPolicy()
    policy.action_policy["send_message"] = "allow_within_scope"
    return policy


class ReceiptHost:
    def __init__(self, req, receipt):
        self.req = req
        self.receipt = receipt
        self.action_calls = 0

    def authorize_action(self, permission_request):
        return {
            "decision": "allow",
            "request_fingerprint": permission_request["request_fingerprint"],
            "scope": permission_request["scope"],
            "action_class": permission_request["action_class"],
            "source": "test-os",
            "reason": "allowed for receipt test",
        }

    def request_action(self, payload):
        self.action_calls += 1
        return translate_action_receipt(self.receipt, self.req, IDENTITY)


def objective_payload(*, verification_level="V2"):
    return {
        "outcome": "verified result",
        "criteria": [{"id": "c1", "statement": "effect is verified", "status": "unverified"}],
        "progress": "progressing",
        "verification_level": verification_level,
        "budget": {"max_attempts": 8},
        "stall_threshold": 3,
    }


def verifying_objective(controller, *, verification_level="V2"):
    obj = controller.create("objective", "operator", "QUEUED", objective_payload(verification_level=verification_level))
    obj = controller.transition("objective", "operator", obj.id, "READY", source=AuthorityTier.VALIDATED_STRATEGY, actor="brain")
    obj = controller.transition("objective", "operator", obj.id, "RUNNING", source=AuthorityTier.VALIDATED_STRATEGY, actor="brain")
    return controller.transition("objective", "operator", obj.id, "VERIFYING", source=AuthorityTier.VALIDATED_STRATEGY, actor="brain")


def add_fresh_os_measurement(receipt, *, criterion_id="c1", kind="measurement"):
    receipt["verification_context"] = {
        "evaluator_id": "ai-verse-os-verifier",
        "independence": "fresh_context",
        "builder_context_id": "builder-run",
        "evaluator_context_id": "os-verifier-run",
    }
    receipt["verification"] = [{
        "criterion_id": criterion_id,
        "status": "passed",
        "rationale": "verified after execution",
        "evidence": [{
            "ref": "os-proof:1",
            "kind": kind,
            "source_kind": "ai_verse_os",
            "source_ref": "os-verifier:1",
            "independence": "fresh_context",
            "scope": "operator",
        }],
    }]
    return receipt


class SkillsActionTranslationTests(unittest.TestCase):
    def test_success_translates_to_brain_success_and_persists_generation_binding(self):
        req = request()
        skills_receipt = receipt_for(req)
        with tempfile.TemporaryDirectory() as temp:
            executor = ActionExecutor(Path(temp), allow_send_policy())
            host = ReceiptHost(req, skills_receipt)
            outcome = executor.execute(req, host, host_idempotency_supported=True)
            self.assertEqual(outcome.status, "succeeded")
            self.assertEqual(outcome.receipt_id, skills_receipt["receipt_id"])
            stored = executor.ledger.read(req)
            binding = stored["response"]["execution_binding"]
            self.assertEqual(binding["request_fingerprint"], req.fingerprint())
            self.assertEqual(binding["generation_id"], IDENTITY.generation_id)
            self.assertEqual(binding["capability_id"], IDENTITY.capability_id)
            self.assertEqual(binding["package_digest"]["value"], DIGEST)

    def test_stale_action_or_generation_is_rejected(self):
        req = request()
        wrong_action = receipt_for(req)
        wrong_action["binding"]["request_fingerprint"] = "c" * 64
        with self.assertRaisesRegex(ValidationError, "request_fingerprint"):
            translate_action_receipt(wrong_action, req, IDENTITY)

        wrong_generation = receipt_for(req)
        stale_identity = SkillsExecutionIdentity(IDENTITY.capability_id, "gen-stale", DIGEST)
        with self.assertRaisesRegex(ValidationError, "generation_id"):
            translate_action_receipt(wrong_generation, req, stale_identity)

    def test_trace_id_never_substitutes_for_stable_receipt(self):
        req = request()
        skills_receipt = receipt_for(req)
        skills_receipt["receipt_id"] = skills_receipt["trace_id"]
        with self.assertRaisesRegex(ValidationError, "trace_id is not proof"):
            translate_action_receipt(skills_receipt, req, IDENTITY)

    def test_partial_or_failed_effects_translate_conservatively(self):
        req = request()
        partial = receipt_for(req, status="partial", effect_state="occurred", effect_source="skill_runtime")
        translated = translate_action_receipt(partial, req, IDENTITY)
        self.assertEqual(translated["status"], "uncertain")
        self.assertIs(translated["effect_occurred"], True)
        with tempfile.TemporaryDirectory() as temp:
            executor = ActionExecutor(Path(temp), allow_send_policy())
            host = ReceiptHost(req, partial)
            with self.assertRaises(UncertainActionOutcome):
                executor.execute(req, host, host_idempotency_supported=True)

        blocked_req = request(key="blocked")
        blocked = receipt_for(blocked_req, status="blocked", effect_state="not_occurred", effect_source="skill_runtime")
        translated = translate_action_receipt(blocked, blocked_req, IDENTITY)
        self.assertEqual(translated["status"], "failed")
        self.assertIs(translated["effect_occurred"], False)

    def test_successful_side_effect_requires_os_effect_verification(self):
        req = request()
        self_asserted = receipt_for(req, effect_source="skill_runtime")
        with self.assertRaisesRegex(ValidationError, "requires AI-Verse OS effect verification"):
            translate_action_receipt(self_asserted, req, IDENTITY)


class SkillsVerificationTranslationTests(unittest.TestCase):
    def test_action_success_without_criterion_proof_cannot_close_objective(self):
        req = request(key="no-proof")
        skills_receipt = receipt_for(req)
        skills_receipt["verification_context"] = {
            "evaluator_id": "fresh-evaluator",
            "independence": "fresh_context",
            "builder_context_id": "builder",
            "evaluator_context_id": "fresh",
        }
        with tempfile.TemporaryDirectory() as temp:
            controller = BrainController(temp)
            objective = verifying_objective(controller)
            translated = translate_action_receipt(skills_receipt, req, IDENTITY)
            self.assertEqual(translated["status"], "succeeded")
            result = apply_receipt_to_objective(
                controller,
                scope="operator",
                objective_id=objective.id,
                receipt=skills_receipt,
                request=req,
                identity=IDENTITY,
            )
            self.assertEqual(result.status, "INSUFFICIENT_EVIDENCE")
            self.assertNotEqual(result.payload["progress"], "verified_complete")

    def test_brain_closes_only_after_exact_criterion_has_strong_fresh_evidence(self):
        req = request(key="verified")
        skills_receipt = add_fresh_os_measurement(receipt_for(req))
        with tempfile.TemporaryDirectory() as temp:
            controller = BrainController(temp)
            objective = verifying_objective(controller)
            result = apply_receipt_to_objective(
                controller,
                scope="operator",
                objective_id=objective.id,
                receipt=skills_receipt,
                request=req,
                identity=IDENTITY,
            )
            self.assertEqual(result.status, "PASSED")
            self.assertEqual(result.payload["progress"], "verified_complete")
            evaluation_id = result.payload["evaluation_refs"][-1]
            evaluation = controller.store.load("evaluation", "operator", evaluation_id)
            evidence = evaluation.evidence_refs[0]
            self.assertEqual(evidence.evidence_class, "DIRECT_MEASUREMENT")
            self.assertEqual(evidence.source_kind, "ai_verse_os")
            self.assertEqual(evidence.source_ref, "os-verifier:1")
            self.assertEqual(evidence.independence, "fresh_context")

    def test_wrong_criterion_id_is_rejected_before_objective_mutation(self):
        req = request(key="wrong-criterion")
        skills_receipt = add_fresh_os_measurement(receipt_for(req), criterion_id="not-c1")
        with tempfile.TemporaryDirectory() as temp:
            controller = BrainController(temp)
            objective = verifying_objective(controller)
            with self.assertRaisesRegex(ValidationError, "unknown Brain criterion"):
                evaluation_from_receipt(skills_receipt, req, IDENTITY, objective)
            stored = controller.store.load("objective", "operator", objective.id)
            self.assertEqual(stored.status, "VERIFYING")

    def test_trace_cannot_be_used_as_criterion_evidence(self):
        req = request(key="trace-proof")
        skills_receipt = add_fresh_os_measurement(receipt_for(req))
        skills_receipt["verification"][0]["evidence"][0]["ref"] = skills_receipt["trace_id"]
        with tempfile.TemporaryDirectory() as temp:
            controller = BrainController(temp)
            objective = verifying_objective(controller)
            with self.assertRaisesRegex(ValidationError, "cannot be criterion evidence"):
                evaluation_from_receipt(skills_receipt, req, IDENTITY, objective)

    def test_weak_observation_does_not_become_v2_strong_evidence(self):
        req = request(key="weak-proof")
        skills_receipt = add_fresh_os_measurement(receipt_for(req), kind="observation")
        with tempfile.TemporaryDirectory() as temp:
            controller = BrainController(temp)
            objective = verifying_objective(controller)
            with self.assertRaisesRegex(EvaluationError, "V2/V3 passed criterion requires"):
                evaluation_from_receipt(skills_receipt, req, IDENTITY, objective)

    def test_evidence_provenance_round_trips_without_affecting_legacy_evidence(self):
        legacy = EvidenceRef("legacy", "DIRECT_MEASUREMENT")
        self.assertNotIn("source_kind", legacy.to_dict())
        enriched = EvidenceRef(
            "proof", "DIRECT_MEASUREMENT", scope="operator",
            source_kind="ai_verse_os", source_ref="os:proof", independence="fresh_context",
        )
        rebuilt = EvidenceRef(**enriched.to_dict())
        self.assertEqual(rebuilt.source_kind, "ai_verse_os")
        self.assertEqual(rebuilt.independence, "fresh_context")


if __name__ == "__main__":
    unittest.main()
