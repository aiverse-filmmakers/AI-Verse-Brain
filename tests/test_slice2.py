import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from aiverse_brain.authority import AuthorityTier
from aiverse_brain.direction import GapProposal, InitiativeProposal, OpportunityProposal
from aiverse_brain.errors import AuthorityError, CooldownActive, DuplicateOpportunity, EvaluationError, PolicyViolation, ValidationError
from aiverse_brain.evaluator import CriterionVerdict, EvaluationResult, Independence
from aiverse_brain.models import EvidenceRef
from aiverse_brain.policy import BrainPolicy, ProactivityLevel
from aiverse_brain.progress import AttemptObservation
from aiverse_brain.ranking import NotificationClass, ScoreComponents
from aiverse_brain.controller import BrainController


def components():
    return ScoreComponents(0.9, 0.9, 0.8, 0.9, 0.8, 0.8, 0.8, 0.1, 0.1, 0.1, 0.1)


def objective_payload(*, criteria=1, verification_level="V1", max_attempts=8, stall_threshold=3):
    return {
        "outcome": "verified result",
        "criteria": [
            {"id": f"c{i+1}", "statement": f"criterion {i+1}", "status": "unverified"}
            for i in range(criteria)
        ],
        "progress": "progressing",
        "verification_level": verification_level,
        "budget": {"max_attempts": max_attempts},
        "stall_threshold": stall_threshold,
    }


def run_objective(controller, payload):
    obj = controller.create("objective", "operator", "QUEUED", payload)
    obj = controller.transition("objective", "operator", obj.id, "READY", source=AuthorityTier.VALIDATED_STRATEGY, actor="brain")
    return controller.transition("objective", "operator", obj.id, "RUNNING", source=AuthorityTier.VALIDATED_STRATEGY, actor="brain")


def validated_learning(controller):
    learning = controller.learning.record_observation(
        "operator", "Use verification before promotion",
        [EvidenceRef("user-correction", "USER_CONFIRMATION")],
        source=AuthorityTier.EXPLICIT_USER,
        actor="user",
    )
    learning = controller.transition("learning", "operator", learning.id, "HYPOTHESIS", source=AuthorityTier.VALIDATED_STRATEGY, actor="brain")
    learning = controller.transition("learning", "operator", learning.id, "PATTERN", source=AuthorityTier.VALIDATED_STRATEGY, actor="brain")
    learning = controller.transition("learning", "operator", learning.id, "REFLECTION", source=AuthorityTier.VALIDATED_STRATEGY, actor="brain")
    return controller.transition("learning", "operator", learning.id, "VALIDATED_LEARNING", source=AuthorityTier.VALIDATED_STRATEGY, actor="brain")


class DirectionSliceTests(unittest.TestCase):
    def test_gap_to_qualified_opportunity_to_initiative(self):
        with tempfile.TemporaryDirectory() as temp:
            controller = BrainController(temp)
            gap = controller.direction.create_gap("operator", GapProposal(["goal-1"], ["context-1"], "publishing is below desired cadence"))
            opp, ranked = controller.direction.propose_opportunity(
                "operator", OpportunityProposal([gap.id], "Build a repeatable publishing workflow", 0.9), components()
            )
            self.assertTrue(ranked.eligible)
            opp = controller.direction.qualify_opportunity("operator", opp.id)
            initiative = controller.direction.propose_initiative(
                "operator", opp.id,
                InitiativeProposal(["goal-1"], [gap.id], "A repeatable workflow closes the consistency gap", "validated weekly workflow", components()),
            )
            self.assertEqual(initiative.status, "PROPOSED")
            source = controller.store.load("opportunity", "operator", opp.id)
            self.assertEqual(source.status, "PROPOSED_INITIATIVE")

    def test_duplicate_proposal_is_blocked(self):
        with tempfile.TemporaryDirectory() as temp:
            controller = BrainController(temp)
            gap = controller.direction.create_gap("operator", GapProposal(["goal-1"], ["context-1"], "gap"))
            proposal = OpportunityProposal([gap.id], "Same intervention", 0.8)
            controller.direction.propose_opportunity("operator", proposal, components())
            with self.assertRaises(DuplicateOpportunity):
                controller.direction.propose_opportunity("operator", proposal, components())

    def test_dismissed_proposal_respects_cooldown(self):
        with tempfile.TemporaryDirectory() as temp:
            controller = BrainController(temp)
            gap = controller.direction.create_gap("operator", GapProposal(["goal-1"], ["context-1"], "gap"))
            proposal = OpportunityProposal([gap.id], "Do not nag", 0.8)
            opp, _ = controller.direction.propose_opportunity("operator", proposal, components())
            controller.transition("opportunity", "operator", opp.id, "DISMISSED", source=AuthorityTier.EXPLICIT_USER, actor="user")
            with self.assertRaises(CooldownActive):
                controller.direction.propose_opportunity("operator", proposal, components())


class AttentionSliceTests(unittest.TestCase):
    def test_p1_observant_does_not_surface(self):
        with tempfile.TemporaryDirectory() as temp:
            controller = BrainController(temp)
            decision = controller.attention.claim_notification(
                scope="operator", fingerprint="x", notification=NotificationClass.SURFACE,
                policy=controller.policy.attention, proactivity=ProactivityLevel.P1_OBSERVANT,
            )
            self.assertFalse(decision.allowed)
            self.assertEqual(decision.notification, NotificationClass.STORE)

    def test_notification_cooldown_persists(self):
        with tempfile.TemporaryDirectory() as temp:
            controller = BrainController(temp)
            now = datetime(2026, 9, 9, 8, 0, tzinfo=timezone.utc)
            first = controller.attention.claim_notification(
                scope="operator", fingerprint="same", notification=NotificationClass.SURFACE,
                policy=controller.policy.attention, proactivity=ProactivityLevel.P2_ADVISORY,
                session_id="s1", now=now,
            )
            second = controller.attention.claim_notification(
                scope="operator", fingerprint="same", notification=NotificationClass.SURFACE,
                policy=controller.policy.attention, proactivity=ProactivityLevel.P2_ADVISORY,
                session_id="s2", now=now + timedelta(hours=1),
            )
            self.assertTrue(first.allowed)
            self.assertFalse(second.allowed)
            self.assertEqual(second.reason, "notification_cooldown")

    def test_interrupt_budget_downgrades_without_silently_dropping(self):
        with tempfile.TemporaryDirectory() as temp:
            policy = BrainPolicy()
            policy.attention.max_interruptions_per_day = 1
            controller = BrainController(temp, policy)
            now = datetime(2026, 9, 9, 8, 0, tzinfo=timezone.utc)
            first = controller.attention.claim_notification(
                scope="operator", fingerprint="one", notification=NotificationClass.INTERRUPT,
                policy=policy.attention, proactivity=ProactivityLevel.P2_ADVISORY, session_id="s", now=now,
            )
            second = controller.attention.claim_notification(
                scope="operator", fingerprint="two", notification=NotificationClass.INTERRUPT,
                policy=policy.attention, proactivity=ProactivityLevel.P2_ADVISORY, session_id="s", now=now + timedelta(minutes=1),
            )
            self.assertEqual(first.notification, NotificationClass.INTERRUPT)
            self.assertTrue(second.allowed)
            self.assertEqual(second.notification, NotificationClass.SURFACE)
            self.assertEqual(second.reason, "interrupt_budget_downgrade")


class ProgressSliceTests(unittest.TestCase):
    def test_repeated_non_progress_stalls(self):
        with tempfile.TemporaryDirectory() as temp:
            controller = BrainController(temp)
            obj = run_objective(controller, objective_payload(stall_threshold=2))
            controller.progress.record_attempt("operator", obj.id, AttemptObservation("state-a"))
            controller.progress.record_attempt("operator", obj.id, AttemptObservation("state-a"))
            update = controller.progress.record_attempt("operator", obj.id, AttemptObservation("state-a"))
            self.assertEqual(update.status, "STALLED")
            self.assertEqual(update.progress, "stalled")

    def test_changed_state_without_evidence_is_not_progress(self):
        with tempfile.TemporaryDirectory() as temp:
            controller = BrainController(temp)
            obj = run_objective(controller, objective_payload(stall_threshold=3))
            controller.progress.record_attempt("operator", obj.id, AttemptObservation("a"))
            update = controller.progress.record_attempt("operator", obj.id, AttemptObservation("b"))
            self.assertFalse(update.meaningful_progress)
            self.assertEqual(update.non_progressing_attempts, 1)

    def test_changed_state_with_evidence_is_progress(self):
        with tempfile.TemporaryDirectory() as temp:
            controller = BrainController(temp)
            obj = run_objective(controller, objective_payload())
            controller.progress.record_attempt("operator", obj.id, AttemptObservation("a"))
            update = controller.progress.record_attempt(
                "operator", obj.id, AttemptObservation("b", [EvidenceRef("measurement-1", "DIRECT_MEASUREMENT")])
            )
            self.assertTrue(update.meaningful_progress)
            self.assertEqual(update.non_progressing_attempts, 0)
            self.assertEqual(update.status, "RUNNING")

    def test_attempt_budget_blocks_without_expansion(self):
        with tempfile.TemporaryDirectory() as temp:
            controller = BrainController(temp)
            obj = run_objective(controller, objective_payload(max_attempts=2, stall_threshold=5))
            controller.progress.record_attempt("operator", obj.id, AttemptObservation("a"))
            update = controller.progress.record_attempt("operator", obj.id, AttemptObservation("a"))
            self.assertEqual(update.status, "BLOCKED")
            self.assertEqual(update.blocked_on, "attempt_budget_exhausted")

    def test_parallel_objective_cap(self):
        with tempfile.TemporaryDirectory() as temp:
            policy = BrainPolicy()
            policy.resources.max_parallel_objectives = 1
            controller = BrainController(temp, policy)
            first = controller.create("objective", "operator", "QUEUED", objective_payload())
            controller.transition("objective", "operator", first.id, "READY", source=AuthorityTier.VALIDATED_STRATEGY, actor="brain")
            second = controller.create("objective", "operator", "QUEUED", objective_payload())
            with self.assertRaises(PolicyViolation):
                controller.transition("objective", "operator", second.id, "READY", source=AuthorityTier.VALIDATED_STRATEGY, actor="brain")


class EvaluatorSliceTests(unittest.TestCase):
    def test_v2_rejects_same_context(self):
        result = EvaluationResult(
            "obj", "V2", Independence.SAME_CONTEXT,
            [CriterionVerdict("c1", "passed", [EvidenceRef("test", "DIRECT_MEASUREMENT")])],
            evaluator_id="eval",
        )
        with self.assertRaises(EvaluationError):
            result.validate()

    def test_v3_rejects_fresh_context_only(self):
        result = EvaluationResult(
            "obj", "V3", Independence.FRESH_CONTEXT,
            [CriterionVerdict("c1", "passed", [EvidenceRef("test", "DIRECT_MEASUREMENT")])],
            evaluator_id="eval", builder_context_id="builder", evaluator_context_id="fresh",
        )
        with self.assertRaises(EvaluationError):
            result.validate()

    def test_evaluation_applies_and_passes_objective(self):
        with tempfile.TemporaryDirectory() as temp:
            controller = BrainController(temp)
            obj = run_objective(controller, objective_payload(verification_level="V2"))
            obj = controller.transition("objective", "operator", obj.id, "VERIFYING", source=AuthorityTier.VALIDATED_STRATEGY, actor="brain")
            result = EvaluationResult(
                obj.id, "V2", Independence.FRESH_CONTEXT,
                [CriterionVerdict("c1", "passed", [EvidenceRef("test-run", "DIRECT_MEASUREMENT")])],
                evaluator_id="eval", builder_context_id="builder", evaluator_context_id="fresh",
            )
            obj = controller.evaluator.apply_to_objective("operator", obj.id, result)
            self.assertEqual(obj.status, "PASSED")
            self.assertEqual(obj.payload["progress"], "verified_complete")
            self.assertTrue(obj.payload["evaluation_refs"])

    def test_missing_criterion_becomes_insufficient_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            controller = BrainController(temp)
            obj = run_objective(controller, objective_payload(criteria=2, verification_level="V2"))
            obj = controller.transition("objective", "operator", obj.id, "VERIFYING", source=AuthorityTier.VALIDATED_STRATEGY, actor="brain")
            result = EvaluationResult(
                obj.id, "V2", Independence.FRESH_CONTEXT,
                [CriterionVerdict("c1", "passed", [EvidenceRef("test-run", "DIRECT_MEASUREMENT")])],
                evaluator_id="eval", builder_context_id="builder", evaluator_context_id="fresh",
            )
            obj = controller.evaluator.apply_to_objective("operator", obj.id, result)
            self.assertEqual(obj.status, "INSUFFICIENT_EVIDENCE")
            self.assertEqual(obj.payload["criteria"][1]["status"], "insufficient_evidence")


class FreshnessSliceTests(unittest.TestCase):
    def test_stale_belief_is_marked_stale(self):
        with tempfile.TemporaryDirectory() as temp:
            controller = BrainController(temp)
            observed = "2026-09-09T00:00:00Z"
            belief = controller.freshness.create_belief(
                "operator", domain="world_model", statement="metric is low", epistemic_state="known", confidence=0.9,
                evidence_refs=[EvidenceRef("metric", "DIRECT_MEASUREMENT", observed_at=observed)],
                observed_at=observed, max_age_seconds=60,
            )
            assessment = controller.freshness.review(
                "operator", belief.id, now=datetime(2026, 9, 9, 1, 0, tzinfo=timezone.utc)
            )
            self.assertEqual(assessment.state, "stale")
            stored = controller.store.load("model_belief", "operator", belief.id)
            self.assertEqual(stored.payload["epistemic_state"], "stale")

    def test_contradicted_belief_requires_verified_refresh(self):
        with tempfile.TemporaryDirectory() as temp:
            controller = BrainController(temp)
            belief = controller.freshness.create_belief(
                "operator", domain="world_model", statement="state", epistemic_state="known", confidence=0.8,
                evidence_refs=[EvidenceRef("old", "DIRECT_MEASUREMENT")],
            )
            controller.freshness.mark_contradicted("operator", belief.id, [EvidenceRef("contradiction", "DIRECT_MEASUREMENT")])
            with self.assertRaises(AuthorityError):
                controller.freshness.refresh(
                    "operator", belief.id, evidence_refs=[EvidenceRef("new", "DIRECT_MEASUREMENT")],
                    source=AuthorityTier.TEMPORARY_HYPOTHESIS,
                )


class LearningSliceTests(unittest.TestCase):
    def test_pattern_requires_repeated_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            controller = BrainController(temp)
            learning = controller.learning.record_observation(
                "operator", "pattern", [EvidenceRef("one", "SINGLE_OBSERVATION")]
            )
            learning = controller.transition("learning", "operator", learning.id, "HYPOTHESIS", source=AuthorityTier.VALIDATED_STRATEGY, actor="brain")
            with self.assertRaises(ValidationError):
                controller.transition("learning", "operator", learning.id, "PATTERN", source=AuthorityTier.VALIDATED_STRATEGY, actor="brain")
            controller.learning.add_evidence(
                "operator", learning.id, [EvidenceRef("two", "SINGLE_OBSERVATION")], source=AuthorityTier.VALIDATED_STRATEGY
            )
            learning = controller.transition("learning", "operator", learning.id, "PATTERN", source=AuthorityTier.VALIDATED_STRATEGY, actor="brain")
            self.assertEqual(learning.status, "PATTERN")

    def test_user_confirmation_cannot_be_faked_by_lower_authority(self):
        with tempfile.TemporaryDirectory() as temp:
            controller = BrainController(temp)
            with self.assertRaises(AuthorityError):
                controller.learning.record_observation(
                    "operator", "fake confirmation", [EvidenceRef("claimed-user", "USER_CONFIRMATION")],
                    source=AuthorityTier.TEMPORARY_HYPOTHESIS,
                )

    def test_e1_strategy_requires_eval_and_regression(self):
        with tempfile.TemporaryDirectory() as temp:
            controller = BrainController(temp)
            learning = validated_learning(controller)
            strategy = controller.learning.create_strategy_candidate(
                "operator", learning.id, evolution_tier="E1", applies_when=["important work"],
                instruction=["verify it"], regression_passed=False,
            )
            with self.assertRaises(ValidationError):
                controller.transition("strategy_rule", "operator", strategy.id, "ACTIVE", source=AuthorityTier.VALIDATED_STRATEGY, actor="brain")
            strategy = controller.learning.record_strategy_outcome(
                "operator", strategy.id, evaluation_ref="eval-1", helpful=True, regression_passed=True
            )
            strategy = controller.transition("strategy_rule", "operator", strategy.id, "ACTIVE", source=AuthorityTier.VALIDATED_STRATEGY, actor="brain")
            self.assertEqual(strategy.status, "ACTIVE")

    def test_e2_strategy_defaults_to_user_approval(self):
        with tempfile.TemporaryDirectory() as temp:
            controller = BrainController(temp)
            payload = {
                "evolution_tier": "E2", "applies_when": ["x"], "instruction": ["y"],
                "evaluation_refs": ["e1", "e2"], "regression_passed": True,
                "helpful_evidence_count": 2, "harmful_evidence_count": 0,
            }
            strategy = controller.create("strategy_rule", "operator", "CANDIDATE", payload, source=AuthorityTier.VALIDATED_STRATEGY)
            with self.assertRaises(AuthorityError):
                controller.transition("strategy_rule", "operator", strategy.id, "ACTIVE", source=AuthorityTier.VALIDATED_STRATEGY, actor="brain")
            strategy = controller.transition("strategy_rule", "operator", strategy.id, "ACTIVE", source=AuthorityTier.EXPLICIT_USER, actor="user")
            self.assertEqual(strategy.status, "ACTIVE")

    def test_e3_cannot_runtime_promote_even_with_user_source(self):
        with tempfile.TemporaryDirectory() as temp:
            controller = BrainController(temp)
            payload = {
                "evolution_tier": "E3", "applies_when": ["x"], "instruction": ["y"],
                "evaluation_refs": ["e1", "e2"], "regression_passed": True,
                "helpful_evidence_count": 2, "harmful_evidence_count": 0,
            }
            strategy = controller.create("strategy_rule", "operator", "CANDIDATE", payload, source=AuthorityTier.VALIDATED_STRATEGY)
            with self.assertRaises(AuthorityError):
                controller.transition("strategy_rule", "operator", strategy.id, "ACTIVE", source=AuthorityTier.EXPLICIT_USER, actor="user")


class EvidenceSliceTests(unittest.TestCase):
    def test_unknown_evidence_class_rejected(self):
        with self.assertRaises(ValidationError):
            EvidenceRef("x", "MAGIC")

    def test_expiry_before_observation_rejected(self):
        with self.assertRaises(ValidationError):
            EvidenceRef("x", "DIRECT_MEASUREMENT", observed_at="2026-09-09T10:00:00Z", expires_at="2026-09-09T09:00:00Z")


if __name__ == "__main__":
    unittest.main()
