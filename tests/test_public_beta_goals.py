import json
import tempfile
import unittest
from pathlib import Path

from aiverse_brain.authority import AuthorityTier
from aiverse_brain.controller import BrainController
from aiverse_brain.errors import AuthorityError, RevisionConflict, ValidationError
from aiverse_brain.extension_registry import brain_attachment
from aiverse_brain.installation import initialize
from aiverse_brain.lifecycle import (
    disable_component, enable_component, lifecycle_status, setup_component, uninstall_component, update_component,
)
from aiverse_brain.models import EvidenceRef, utc_now


def direct(ref):
    return EvidenceRef(
        ref=ref, evidence_class="DIRECT_MEASUREMENT", observed_at=utc_now(),
        scope="operator", source_kind="test", source_ref=ref, independence="fresh_context",
    )


def make_native(root: Path):
    (root / "operator").mkdir(parents=True, exist_ok=True)
    (root / "workspaces").mkdir(parents=True, exist_ok=True)
    (root / "AI-VERSE.yaml").write_text(
        'schema_version: "2.0"\narchitecture: unified-workspace\n', encoding="utf-8"
    )


class GoalContractTests(unittest.TestCase):
    def test_goal_lifecycle_persists_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            initialize(temp)
            goals = BrainController(temp).goals
            created = goals.create(
                "operator", objective="Ship verified beta", operation_id="create-1",
                criteria=[{"id": "tests", "statement": "tests pass"}],
                completion_contract={
                    "outcome": "Verified beta ships",
                    "verification": [{"id": "ci", "statement": "CI succeeds", "evidence_ref": "ci:1"}],
                    "constraints": ["Do not broaden user intent"],
                    "boundaries": ["No permission expansion"],
                    "stop_when": [],
                },
            )
            replay = goals.create(
                "operator", objective="Ship verified beta", operation_id="create-1",
                criteria=[{"id": "tests", "statement": "tests pass"}],
                completion_contract={
                    "outcome": "Verified beta ships",
                    "verification": [{"id": "ci", "statement": "CI succeeds", "evidence_ref": "ci:1"}],
                    "constraints": ["Do not broaden user intent"],
                    "boundaries": ["No permission expansion"],
                    "stop_when": [],
                },
            )
            self.assertTrue(replay.replayed)
            self.assertEqual(replay.goal["goal_id"], created.goal["goal_id"])
            with self.assertRaises(ValidationError):
                goals.create("operator", objective="Changed objective", operation_id="create-1")
            restarted = BrainController(temp).goals.get("operator", created.goal["goal_id"])
            self.assertEqual(restarted["objective"], "Ship verified beta")
            self.assertEqual(restarted["status"], "active")

    def test_operator_controls_edit_pause_resume_clear_and_stale_version(self):
        with tempfile.TemporaryDirectory() as temp:
            initialize(temp)
            service = BrainController(temp).goals
            goal = service.create("operator", objective="Original", operation_id="g1").goal
            with self.assertRaises(AuthorityError):
                service.edit(
                    "operator", goal["goal_id"], expected_version=goal["version"], operation_id="edit-model",
                    objective="Model replacement", source=AuthorityTier.TEMPORARY_HYPOTHESIS,
                )
            edited = service.edit(
                "operator", goal["goal_id"], expected_version=goal["version"], operation_id="edit-user",
                objective="User replacement",
            ).goal
            with self.assertRaises(RevisionConflict):
                service.edit(
                    "operator", goal["goal_id"], expected_version=goal["version"],
                    operation_id="stale-edit", objective="stale",
                )
            paused = service.transition(
                "operator", goal["goal_id"], expected_version=edited["version"],
                operation_id="pause-1", action="pause",
            ).goal
            resumed = service.transition(
                "operator", goal["goal_id"], expected_version=paused["version"],
                operation_id="resume-1", action="resume",
            ).goal
            self.assertGreater(resumed["activation_epoch"], paused["activation_epoch"])
            cleared = service.transition(
                "operator", goal["goal_id"], expected_version=resumed["version"],
                operation_id="clear-1", action="clear",
            ).goal
            self.assertEqual(cleared["status"], "cleared")
            self.assertEqual(len(service.list("operator")), 1)

    def test_completion_requires_bound_non_model_evidence_and_deterministic_gate(self):
        with tempfile.TemporaryDirectory() as temp:
            initialize(temp)
            service = BrainController(temp).goals
            created = service.create(
                "operator", objective="Pass contract", operation_id="create",
                criteria=[{"id": "c1", "statement": "criterion passes"}],
                completion_contract={
                    "outcome": "done",
                    "verification": [{"id": "gate", "statement": "gate passes", "evidence_ref": "gate:ok"}],
                },
            ).goal
            weak = EvidenceRef(ref="weak", evidence_class="MODEL_INFERENCE", observed_at=utc_now(), scope="operator")
            with self.assertRaises(ValidationError):
                service.evaluate(
                    "operator", created["goal_id"], expected_version=created["version"],
                    evidence_refs=[weak],
                    criterion_results=[{"criterion_id": "c1", "status": "passed", "evidence_refs": ["weak"]}],
                )
            evidence = [direct("criterion:ok"), direct("gate:ok")]
            criterion_results = [{"criterion_id": "c1", "status": "passed", "evidence_refs": ["criterion:ok"]}]
            verdict = service.evaluate(
                "operator", created["goal_id"], expected_version=created["version"],
                evidence_refs=evidence, criterion_results=criterion_results,
            )
            self.assertEqual(verdict.verdict, "complete")
            completed = service.transition(
                "operator", created["goal_id"], expected_version=created["version"],
                operation_id="complete", action="complete",
                evidence_refs=evidence, criterion_results=criterion_results,
                source=AuthorityTier.VERIFIED_EVIDENCE,
            ).goal
            self.assertEqual(completed["status"], "complete")

    def test_budget_and_no_progress_are_backstops_not_completion(self):
        with tempfile.TemporaryDirectory() as temp:
            initialize(temp)
            service = BrainController(temp).goals
            goal = service.create(
                "operator", objective="Bounded work", operation_id="create",
                budget_policy={"max_turns": 20, "no_progress_limit": 2},
            ).goal
            first = service.record_progress(
                "operator", goal["goal_id"], expected_version=goal["version"],
                operation_id="p1", progress_token="same",
            ).goal
            second = service.record_progress(
                "operator", goal["goal_id"], expected_version=first["version"],
                operation_id="p2", progress_token="same",
            ).goal
            third = service.record_progress(
                "operator", goal["goal_id"], expected_version=second["version"],
                operation_id="p3", progress_token="same",
            ).goal
            self.assertEqual(third["status"], "blocked")
            self.assertNotEqual(third["status"], "complete")
            contract = service.continuation_contract("operator", goal["goal_id"])
            self.assertFalse(contract["may_continue"])


class ImprovementContractTests(unittest.TestCase):
    class Host:
        def __init__(self):
            self.calls = []
        def write_route(self, classification, payload, scope):
            self.calls.append((classification, payload, scope))
            return "skills:proposal:123"

    def test_brain_emits_candidate_but_owner_performs_durable_write(self):
        with tempfile.TemporaryDirectory() as temp:
            initialize(temp)
            controller = BrainController(temp)
            candidate = controller.improvements.create(
                "operator", suggested_owner="skills", kind="create",
                summary="Reusable safe procedure", evidence_refs=[direct("eval:1")],
                risk="low", confidence=0.9, evaluation_criteria=["replay succeeds"],
            )
            self.assertEqual(candidate.status, "CANDIDATE")
            host = self.Host()
            routed = controller.improvements.route("operator", candidate.id, host)
            self.assertTrue(routed["routed"])
            self.assertEqual(routed["owner_ref"], "skills:proposal:123")
            self.assertEqual(host.calls[0][0], "repeatable_execution")

    def test_skill_repair_is_exact_generation_bound(self):
        with tempfile.TemporaryDirectory() as temp:
            initialize(temp)
            controller = BrainController(temp)
            with self.assertRaises(ValidationError):
                controller.improvements.create(
                    "operator", suggested_owner="skills", kind="repair", summary="fix it",
                    evidence_refs=[direct("failure:1")], risk="low", confidence=0.9,
                    target_skill_id="skill-x",
                )
            candidate = controller.improvements.create(
                "operator", suggested_owner="skills", kind="repair", summary="bounded fix",
                evidence_refs=[direct("failure:2")], risk="low", confidence=0.9,
                target_skill_id="skill-x", target_generation="gen-1", target_digest="abc123",
            )
            self.assertEqual(candidate.payload["target_generation"], "gen-1")


class StrategyRollbackTests(unittest.TestCase):
    @staticmethod
    def payload(previous=None):
        return {
            "evolution_tier": "E1", "applies_when": ["task"], "instruction": ["do safe thing"],
            "exclusions": [], "helpful_evidence_count": 1, "harmful_evidence_count": 0,
            "evaluation_refs": ["eval-1"], "regression_passed": True,
            "source_learning_ref": None, "previous_revision_ref": previous,
        }

    def test_rollback_restores_previous_known_good_strategy(self):
        with tempfile.TemporaryDirectory() as temp:
            initialize(temp)
            controller = BrainController(temp)
            previous = controller.create("strategy_rule", "operator", "CANDIDATE", self.payload())
            previous = controller.transition(
                "strategy_rule", "operator", previous.id, "ACTIVE",
                source=AuthorityTier.VALIDATED_STRATEGY, actor="test",
            )
            candidate = controller.create("strategy_rule", "operator", "CANDIDATE", self.payload())
            controller.strategy_revisions.link_previous("operator", candidate.id, previous.id)
            current = controller.strategy_revisions.promote_revision(
                "operator", candidate.id, source=AuthorityTier.VALIDATED_STRATEGY,
            )
            self.assertEqual(controller.store.load("strategy_rule", "operator", previous.id).status, "RETIRED")
            result = controller.strategy_revisions.rollback("operator", current.id)
            self.assertEqual(result.state, "complete")
            self.assertEqual(controller.store.load("strategy_rule", "operator", previous.id).status, "ACTIVE")
            self.assertEqual(controller.store.load("strategy_rule", "operator", current.id).status, "ROLLED_BACK")


class LifecycleAndAdoptionTests(unittest.TestCase):
    def test_setup_status_and_standalone_to_native_adoption_preserve_goal(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            setup = setup_component(str(root), apply=True)
            self.assertTrue(setup["ok"])
            self.assertEqual(lifecycle_status(str(root)).state, "ready")
            created = BrainController(str(root)).goals.create(
                "operator", objective="survive adoption", operation_id="adopt-goal"
            ).goal
            make_native(root)
            planned = setup_component(str(root), apply=False)
            self.assertTrue(planned["adoption"]["needed"])
            applied = setup_component(str(root), apply=True)
            self.assertTrue(applied["ok"])
            self.assertFalse((root / ".ai-verse-brain").exists())
            self.assertTrue((root / "operator" / "brain" / "installation.json").is_file())
            goal = BrainController(str(root)).goals.get("operator", created["goal_id"])
            self.assertEqual(goal["objective"], "survive adoption")
            self.assertIsNotNone(brain_attachment(str(root)))

    def test_disable_enable_update_uninstall_are_symmetric_and_preserve_state(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            make_native(root)
            setup_component(str(root), apply=True)
            marker = root / "operator" / "brain" / "installation.json"
            data = json.loads(marker.read_text(encoding="utf-8"))
            data["package_version"] = "0.0.0"
            marker.write_text(json.dumps(data), encoding="utf-8")
            disabled = disable_component(str(root), apply=True)
            self.assertEqual(disabled["status"]["state"], "disabled")
            update_component(str(root), apply=True)
            self.assertFalse(brain_attachment(str(root))["enabled"])
            enabled = enable_component(str(root), apply=True)
            self.assertTrue(enabled["attachment"]["enabled"])
            uninstalled = uninstall_component(str(root), apply=True)
            self.assertTrue(uninstalled["canonical_brain_state_preserved"])
            self.assertTrue(marker.is_file())
            self.assertIsNone(brain_attachment(str(root)))


if __name__ == "__main__":
    unittest.main()
