from __future__ import annotations

import unittest

from aiverse_brain.errors import ValidationError
from aiverse_brain.learning import admit_skills_learning_candidate


class LearningCandidateGateTests(unittest.TestCase):
    def candidate(self, **changes):
        value = {
            "candidate_id": "learn-run-1",
            "scope": "workspace:alpha",
            "suggested_owner": "skills",
            "kind": "create",
            "summary": "A reusable verified delivery procedure.",
            "skill_id": "alpha-delivery-review",
            "evidence_refs": ["run:1", "session:1"],
            "success_signal": ["delivery completed successfully"],
            "failure_signal": [],
            "risk": "low",
            "confidence": 0.95,
            "created_at": "2026-09-14T13:00:00Z",
            "requested_capabilities": [],
            "requested_dependencies": [],
            "requires_connection": False,
            "requires_credential": False,
            "source_ownership": "agent_learned",
        }
        value.update(changes)
        return value

    def test_substantial_create_routes_to_skills(self):
        result = admit_skills_learning_candidate(
            self.candidate(),
            bound_scope="workspace:alpha",
            substantial_task=True,
        )
        self.assertEqual(result["state"], "admitted")
        env = result["envelope"]
        self.assertEqual(env["suggested_owner"], "skills")
        self.assertEqual(env["skill_id"], "alpha-delivery-review")
        self.assertEqual(env["scope"], {"aiverse_scope": "workspace:alpha"})
        self.assertEqual(env["evidence_refs"], ["run:1", "session:1"])

    def test_trivial_task_is_ignored_before_owner_mutation(self):
        result = admit_skills_learning_candidate(
            self.candidate(),
            bound_scope="workspace:alpha",
            substantial_task=False,
        )
        self.assertEqual(result["state"], "ignored")

    def test_non_skills_owner_and_low_confidence_are_ignored(self):
        owner = admit_skills_learning_candidate(
            self.candidate(suggested_owner="memory"),
            bound_scope="workspace:alpha",
            substantial_task=True,
        )
        self.assertEqual(owner["state"], "ignored")
        confidence = admit_skills_learning_candidate(
            self.candidate(confidence=0.59),
            bound_scope="workspace:alpha",
            substantial_task=True,
        )
        self.assertEqual(confidence["state"], "ignored")

    def test_scope_and_authority_fields_fail_closed(self):
        with self.assertRaisesRegex(ValidationError, "trusted bound scope"):
            admit_skills_learning_candidate(
                self.candidate(scope="workspace:beta"),
                bound_scope="workspace:alpha",
                substantial_task=True,
            )
        with self.assertRaisesRegex(ValidationError, "forbidden"):
            admit_skills_learning_candidate(
                self.candidate(approval=True),
                bound_scope="workspace:alpha",
                substantial_task=True,
            )

    def test_safe_ids_and_bounded_evidence_are_required(self):
        with self.assertRaisesRegex(ValidationError, "safe skill_id"):
            admit_skills_learning_candidate(
                self.candidate(skill_id="../escape"),
                bound_scope="workspace:alpha",
                substantial_task=True,
            )
        with self.assertRaisesRegex(ValidationError, "must not be empty"):
            admit_skills_learning_candidate(
                self.candidate(evidence_refs=[]),
                bound_scope="workspace:alpha",
                substantial_task=True,
            )

    def test_repair_is_target_bound(self):
        result = admit_skills_learning_candidate(
            self.candidate(
                kind="repair",
                skill_id=None,
                target_skill_id="existing-learned",
            ),
            bound_scope="workspace:alpha",
            substantial_task=True,
        )
        self.assertEqual(result["state"], "admitted")
        self.assertEqual(result["envelope"]["target_skill_id"], "existing-learned")
        with self.assertRaisesRegex(ValidationError, "may only match"):
            admit_skills_learning_candidate(
                self.candidate(
                    kind="repair",
                    skill_id="different",
                    target_skill_id="existing-learned",
                ),
                bound_scope="workspace:alpha",
                substantial_task=True,
            )

    def test_workspace_local_requires_workspace_bound_scope(self):
        result = admit_skills_learning_candidate(
            self.candidate(source_ownership="workspace_local"),
            bound_scope="workspace:alpha",
            substantial_task=True,
        )
        self.assertEqual(result["envelope"]["scope"], {"workspace_id": "alpha"})
        with self.assertRaisesRegex(ValidationError, "workspace-bound"):
            admit_skills_learning_candidate(
                self.candidate(
                    scope="operator",
                    source_ownership="workspace_local",
                ),
                bound_scope="operator",
                substantial_task=True,
            )


if __name__ == "__main__":
    unittest.main()
