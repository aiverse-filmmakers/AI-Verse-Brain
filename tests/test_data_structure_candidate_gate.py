from __future__ import annotations

import unittest

from aiverse_brain.errors import ValidationError
from aiverse_brain.learning import admit_data_structure_candidate


class DataStructureCandidateGateTests(unittest.TestCase):
    def candidate(self, **changes):
        value = {
            "candidate_id": "data-run-1",
            "scope": "workspace:alpha",
            "suggested_owner": "data",
            "summary": "Repeated Client Alpha contact state is structured current truth.",
            "evidence_refs": ["run:1", "session:1"],
            "confidence": 0.95,
            "created_at": "2026-09-14T15:00:00Z",
            "repeated_evidence": True,
            "current_truth": True,
            "structured_operational": True,
            "contains_secret": False,
            "privacy_ambiguous": False,
            "permission_expansion": False,
            "destructive": False,
            "structure": {
                "space": {
                    "spaceId": "crm",
                    "name": "CRM",
                    "authority": "local_canonical",
                },
                "schema": {
                    "spaceId": "crm",
                    "entity": "contacts",
                    "name": "Contacts",
                    "fields": {
                        "email": {"type": "string", "required": True},
                        "name": {"type": "string"},
                    },
                },
            },
            "match": {"field": "email", "value": "a@example.test"},
            "record": {
                "data": {
                    "email": "a@example.test",
                    "name": "A",
                },
            },
        }
        value.update(changes)
        return value

    def test_repeated_structured_current_truth_routes_to_data(self):
        result = admit_data_structure_candidate(
            self.candidate(),
            bound_scope="workspace:alpha",
            substantial_task=True,
        )
        self.assertEqual(result["state"], "admitted")
        env = result["envelope"]
        self.assertEqual(env["scope"], "workspace:alpha")
        self.assertEqual(env["structure"]["space"]["spaceId"], "crm")
        self.assertEqual(env["structure"]["schema"]["entity"], "contacts")
        self.assertEqual(env["match"], {"field": "email", "value": "a@example.test"})

    def test_trivial_operator_or_non_data_candidates_are_ignored(self):
        trivial = admit_data_structure_candidate(
            self.candidate(),
            bound_scope="workspace:alpha",
            substantial_task=False,
        )
        self.assertEqual(trivial["state"], "ignored")
        operator_candidate = self.candidate(scope="operator")
        operator = admit_data_structure_candidate(
            operator_candidate,
            bound_scope="operator",
            substantial_task=True,
        )
        self.assertEqual(operator["state"], "ignored")
        owner = admit_data_structure_candidate(
            self.candidate(suggested_owner="memory"),
            bound_scope="workspace:alpha",
            substantial_task=True,
        )
        self.assertEqual(owner["state"], "ignored")

    def test_automatic_route_requires_repeated_high_confidence_current_truth(self):
        for change in (
            {"confidence": 0.79},
            {"repeated_evidence": False},
            {"current_truth": False},
            {"structured_operational": False},
            {"evidence_refs": ["run:1"]},
        ):
            result = admit_data_structure_candidate(
                self.candidate(**change),
                bound_scope="workspace:alpha",
                substantial_task=True,
            )
            self.assertEqual(result["state"], "ignored")

    def test_secret_privacy_permission_and_destructive_flags_block_auto_route(self):
        for flag in (
            "contains_secret",
            "privacy_ambiguous",
            "permission_expansion",
            "destructive",
        ):
            result = admit_data_structure_candidate(
                self.candidate(**{flag: True}),
                bound_scope="workspace:alpha",
                substantial_task=True,
            )
            self.assertEqual(result["state"], "ignored")
            self.assertIn(flag, result["reason"])

    def test_scope_and_structure_shape_fail_closed(self):
        with self.assertRaisesRegex(ValidationError, "trusted bound scope"):
            admit_data_structure_candidate(
                self.candidate(scope="workspace:beta"),
                bound_scope="workspace:alpha",
                substantial_task=True,
            )
        broken = self.candidate()
        broken["structure"] = {
            "space": {
                "spaceId": "crm",
                "name": "CRM",
                "authority": "external",
            },
            "schema": broken["structure"]["schema"],
        }
        with self.assertRaisesRegex(ValidationError, "local_canonical"):
            admit_data_structure_candidate(
                broken,
                bound_scope="workspace:alpha",
                substantial_task=True,
            )

    def test_match_is_required_for_duplicate_safe_record_routing(self):
        with self.assertRaisesRegex(ValidationError, "match field"):
            admit_data_structure_candidate(
                self.candidate(match={"field": "missing", "value": "x"}),
                bound_scope="workspace:alpha",
                substantial_task=True,
            )
        with self.assertRaisesRegex(ValidationError, "exact match value"):
            admit_data_structure_candidate(
                self.candidate(
                    match={"field": "email", "value": "b@example.test"},
                ),
                bound_scope="workspace:alpha",
                substantial_task=True,
            )

    def test_runtime_cannot_smuggle_authority_or_unbounded_structure(self):
        with self.assertRaisesRegex(ValidationError, "unsupported fields"):
            admit_data_structure_candidate(
                self.candidate(approval=True),
                bound_scope="workspace:alpha",
                substantial_task=True,
            )
        with self.assertRaisesRegex(ValidationError, "JSON-serializable"):
            admit_data_structure_candidate(
                self.candidate(record={"data": {"email": "a@example.test", "x": {1, 2}}}),
                bound_scope="workspace:alpha",
                substantial_task=True,
            )


if __name__ == "__main__":
    unittest.main()
