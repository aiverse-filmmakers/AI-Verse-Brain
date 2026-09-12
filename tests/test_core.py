import tempfile
import unittest
from pathlib import Path

from aiverse_brain.authority import AuthorityTier, assert_control_channel, assert_self_evolution_fields
from aiverse_brain.cadence import Trigger
from aiverse_brain.controller import BrainController
from aiverse_brain.errors import AuthorityError, DuplicateTrigger, PermissionDenied, PolicyViolation, RevisionConflict, ScopeError, TransitionError, ValidationError
from aiverse_brain.installation import initialize
from aiverse_brain.models import BrainObject, EvidenceRef, Scope
from aiverse_brain.policy import BrainPolicy, ProactivityLevel
from aiverse_brain.ranking import Eligibility, ScoreComponents, NotificationClass, rank
from aiverse_brain.state_machine import assert_transition
from aiverse_brain.storage import ObjectStore, StorageLayout
from aiverse_brain.verification import Criterion, VerificationFactors, VerificationLevel, select_level
from aiverse_brain.write_router import WriteRoute, classify_write


def initiative_payload(label="x"):
    return {
        "serves": ["goal-1"],
        "gap_refs": ["gap-1"],
        "hypothesis": label,
        "outcome": "verified improvement",
        "score_components": {},
    }


def objective_payload(status="unverified", evidence=None):
    criterion = {"id": "c1", "statement": "verified result", "status": status}
    if evidence is not None:
        criterion["evidence_refs"] = evidence
    return {"outcome": "done", "criteria": [criterion], "progress": "complete_unverified"}


class ScopeContractTests(unittest.TestCase):
    def test_workspace_scope_matches_os_workspace_id_schema(self):
        self.assertEqual(Scope("workspace:film-project").workspace_id, "film-project")
        for invalid in ("workspace:film_project", "workspace:film.project"):
            with self.assertRaises(ScopeError):
                Scope(invalid)


class StateMachineTests(unittest.TestCase):
    def test_brain_cannot_confirm_goal_without_user_authority(self):
        with self.assertRaises(AuthorityError):
            assert_transition("intent", "PROPOSED", "CONFIRMED", AuthorityTier.VALIDATED_STRATEGY)
        assert_transition("intent", "PROPOSED", "CONFIRMED", AuthorityTier.EXPLICIT_USER)

    def test_creation_cannot_bypass_goal_confirmation(self):
        with tempfile.TemporaryDirectory() as temp:
            controller = BrainController(temp)
            payload = {"subtype": "goal", "statement": "become excellent"}
            with self.assertRaises(TransitionError):
                controller.create("intent", "operator", "ACTIVE", payload)
            confirmed = controller.create("intent", "operator", "CONFIRMED", payload, source=AuthorityTier.EXPLICIT_USER, actor="user")
            self.assertEqual(confirmed.status, "CONFIRMED")

    def test_brain_cannot_create_policy(self):
        with tempfile.TemporaryDirectory() as temp:
            controller = BrainController(temp)
            with self.assertRaises(AuthorityError):
                controller.create("policy", "operator", "ACTIVE", {"proactivity": "P2"})

    def test_invalid_transition_rejected(self):
        with self.assertRaises(TransitionError):
            assert_transition("initiative", "DISCOVERED", "COMPLETED", AuthorityTier.EXPLICIT_USER)


class AuthorityTests(unittest.TestCase):
    def test_external_data_is_not_control_channel(self):
        with self.assertRaises(AuthorityError):
            assert_control_channel(AuthorityTier.EXTERNAL_DATA)

    def test_self_evolution_cannot_change_permissions(self):
        with self.assertRaises(AuthorityError):
            assert_self_evolution_fields(["permission_matrix"])


class PolicyTests(unittest.TestCase):
    def test_proactivity_does_not_grant_send_permission(self):
        policy = BrainPolicy(proactivity=ProactivityLevel.P4_DELEGATED)
        with self.assertRaises(PermissionDenied):
            policy.assert_pre_authorized("send_message", in_scope=True, within_budget=True, reversible=True)

    def test_wip_cap_is_enforced(self):
        with tempfile.TemporaryDirectory() as temp:
            policy = BrainPolicy()
            policy.attention.max_active_initiatives = 1
            controller = BrainController(temp, policy)
            first = controller.create("initiative", "operator", "DISCOVERED", initiative_payload("a"))
            first = controller.transition("initiative", "operator", first.id, "PROPOSED", source=AuthorityTier.TEMPORARY_HYPOTHESIS, actor="brain")
            controller.transition("initiative", "operator", first.id, "ACCEPTED", source=AuthorityTier.EXPLICIT_USER, actor="user")
            second = controller.create("initiative", "operator", "DISCOVERED", initiative_payload("b"))
            second = controller.transition("initiative", "operator", second.id, "PROPOSED", source=AuthorityTier.TEMPORARY_HYPOTHESIS, actor="brain")
            with self.assertRaises(PolicyViolation):
                controller.transition("initiative", "operator", second.id, "ACCEPTED", source=AuthorityTier.EXPLICIT_USER, actor="user")


class RankingTests(unittest.TestCase):
    def _components(self):
        return ScoreComponents(0.9, 0.9, 0.8, 0.9, 0.8, 0.8, 0.8, 0.1, 0.1, 0.1, 0.1)

    def test_hard_gate_beats_high_score(self):
        result = rank(Eligibility(permission_compatible=False), self._components())
        self.assertFalse(result.eligible)
        self.assertIsNone(result.score)
        self.assertEqual(result.notification, NotificationClass.DROP)

    def test_high_value_item_can_interrupt(self):
        result = rank(Eligibility(), self._components())
        self.assertTrue(result.eligible)
        self.assertGreaterEqual(result.score, 0.82)
        self.assertEqual(result.notification, NotificationClass.INTERRUPT)


class VerificationTests(unittest.TestCase):
    def test_pass_requires_evidence(self):
        criterion = Criterion("c1", "tests pass")
        with self.assertRaises(ValidationError):
            criterion.mark("passed", [])
        criterion.mark("passed", [EvidenceRef("test-run-1", "DIRECT_MEASUREMENT")])
        self.assertEqual(criterion.status, "passed")

    def test_objective_cannot_pass_unverified(self):
        with tempfile.TemporaryDirectory() as temp:
            controller = BrainController(temp)
            obj = controller.create("objective", "operator", "QUEUED", objective_payload())
            obj = controller.transition("objective", "operator", obj.id, "READY", source=AuthorityTier.VALIDATED_STRATEGY, actor="brain")
            obj = controller.transition("objective", "operator", obj.id, "RUNNING", source=AuthorityTier.VALIDATED_STRATEGY, actor="brain")
            obj = controller.transition("objective", "operator", obj.id, "VERIFYING", source=AuthorityTier.VALIDATED_STRATEGY, actor="brain")
            with self.assertRaises(ValidationError):
                controller.transition("objective", "operator", obj.id, "PASSED", source=AuthorityTier.VALIDATED_STRATEGY, actor="brain")

    def test_objective_can_pass_with_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            controller = BrainController(temp)
            obj = controller.create("objective", "operator", "QUEUED", objective_payload("passed", ["eval-1"]))
            obj = controller.transition("objective", "operator", obj.id, "READY", source=AuthorityTier.VALIDATED_STRATEGY, actor="brain")
            obj = controller.transition("objective", "operator", obj.id, "RUNNING", source=AuthorityTier.VALIDATED_STRATEGY, actor="brain")
            obj = controller.transition("objective", "operator", obj.id, "VERIFYING", source=AuthorityTier.VALIDATED_STRATEGY, actor="brain")
            obj = controller.transition("objective", "operator", obj.id, "PASSED", source=AuthorityTier.VERIFIED_EVIDENCE, actor="evaluator")
            self.assertEqual(obj.status, "PASSED")

    def test_high_impact_is_v3(self):
        factors = VerificationFactors(impact=0.9, irreversibility=0.8)
        self.assertEqual(select_level(factors), VerificationLevel.V3_HIGH_IMPACT)


class StorageTests(unittest.TestCase):
    def test_payload_validation_is_enforced_on_write(self):
        with tempfile.TemporaryDirectory() as temp:
            store = ObjectStore(StorageLayout(Path(temp), "standalone"))
            obj = BrainObject.new("initiative", "operator", "DISCOVERED", {"hypothesis": "too little"})
            with self.assertRaises(ValidationError):
                store.save(obj, expected_revision=-1)

    def test_invalid_status_is_rejected_on_write(self):
        with tempfile.TemporaryDirectory() as temp:
            store = ObjectStore(StorageLayout(Path(temp), "standalone"))
            obj = BrainObject.new("initiative", "operator", "MAGIC_DONE", initiative_payload())
            with self.assertRaises(ValidationError):
                store.save(obj, expected_revision=-1)

    def test_lookup_id_cannot_traverse(self):
        with tempfile.TemporaryDirectory() as temp:
            store = ObjectStore(StorageLayout(Path(temp), "standalone"))
            with self.assertRaises(ValidationError):
                store.load("initiative", "operator", "../../escape")

    def test_optimistic_concurrency(self):
        with tempfile.TemporaryDirectory() as temp:
            store = ObjectStore(StorageLayout(Path(temp), "standalone"))
            obj = BrainObject.new("initiative", "operator", "DISCOVERED", initiative_payload())
            saved = store.save(obj, expected_revision=-1)
            stale = BrainObject.from_dict(saved.to_dict())
            saved.status = "PROPOSED"
            saved = store.save(saved, expected_revision=1)
            stale.status = "PROPOSED"
            with self.assertRaises(RevisionConflict):
                store.save(stale, expected_revision=1)

    def test_native_workspace_isolation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "operator").mkdir()
            (root / "workspaces" / "a").mkdir(parents=True)
            (root / "workspaces" / "b").mkdir(parents=True)
            (root / "AI-VERSE.yaml").write_text(
                'schema_version: "2.0"\narchitecture: unified-workspace\nextensions:\n  brain:\n    supported: true\n    enabled: true\n',
                encoding="utf-8",
            )
            initialize(str(root))
            controller = BrainController(str(root))
            controller.create("initiative", "workspace:a", "DISCOVERED", initiative_payload("a"))
            self.assertEqual(len(controller.store.list("initiative", "workspace:a")), 1)
            self.assertEqual(len(controller.store.list("initiative", "workspace:b")), 0)
            self.assertFalse((root / ".ai-verse-brain").exists())


class CadenceTests(unittest.TestCase):
    def test_trigger_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            controller = BrainController(temp)
            trigger = Trigger("session_start", Scope("operator"), "same-key")
            controller.run_trigger(trigger)
            with self.assertRaises(DuplicateTrigger):
                controller.run_trigger(trigger)


class WriteRouterTests(unittest.TestCase):
    def test_write_ownership(self):
        self.assertEqual(classify_write("current_state"), WriteRoute.OS_CONTEXT)
        self.assertEqual(classify_write("historical_experience"), WriteRoute.MEMORY_HISTORY)
        self.assertEqual(classify_write("initiative"), WriteRoute.BRAIN_STATE)


if __name__ == "__main__":
    unittest.main()
