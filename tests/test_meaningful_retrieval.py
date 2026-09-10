import unittest

from aiverse_brain.cognition import CognitionPurpose, CognitionRequest
from aiverse_brain.errors import ValidationError
from aiverse_brain.models import Scope
from aiverse_brain.reasoner import ContextAssembler
from aiverse_brain.retrieval import build_retrieval_query, rank_capabilities


class _Object:
    def __init__(self, data):
        self.data = dict(data)

    def to_dict(self):
        return dict(self.data)


class _Store:
    def __init__(self, by_kind=None):
        self.by_kind = by_kind or {}

    def list(self, kind, scope, statuses=None):
        return [_Object(item) for item in self.by_kind.get(kind, [])]


class _Controller:
    def __init__(self, by_kind=None):
        self.store = _Store(by_kind)


class RecordingHost:
    def __init__(self, *, current=None, history=None, capabilities=None):
        self.current = current or {}
        self.history = history or []
        self.capabilities = capabilities or []
        self.history_queries = []

    def read_context(self, scope):
        return dict(self.current)

    def retrieve_history(self, query, scope):
        self.history_queries.append((query, scope))
        return list(self.history)

    def list_capabilities(self, scope):
        return list(self.capabilities)

    def list_connections(self, scope):
        return []


class MeaningfulRetrievalTests(unittest.TestCase):
    def test_history_query_uses_real_task_context_not_internal_purpose_label(self):
        controller = _Controller({
            "objective": [{
                "id": "obj-retention",
                "kind": "objective",
                "scope": "operator",
                "status": "RUNNING",
                "payload": {
                    "outcome": "Reduce customer churn by improving onboarding activation",
                    "criteria": [{"id": "c1", "statement": "Activation improves"}],
                },
            }],
        })
        host = RecordingHost(
            current={"current_context": "Trial users abandon the onboarding setup before activation."},
            history=[{"memory": "A previous onboarding simplification improved activation."}],
        )
        request = CognitionRequest(
            purpose=CognitionPurpose.REFLECTION,
            scope=Scope("operator"),
            context_refs=[],
            output_contract={"proposal_kinds": ["learning"]},
        )

        bundle = ContextAssembler(controller, host).build(request)
        query, scope = host.history_queries[0]

        self.assertEqual(scope, "operator")
        self.assertNotEqual(query, "reflection")
        self.assertIn("churn", query.lower())
        self.assertIn("onboarding", query.lower())
        self.assertIn("activation", query.lower())
        self.assertEqual(bundle.retrieval_queries["history"], query)
        self.assertEqual(bundle.history[0]["memory"], "A previous onboarding simplification improved activation.")

    def test_same_purpose_changes_query_when_objective_changes(self):
        request = CognitionRequest(
            purpose=CognitionPurpose.REFLECTION,
            scope=Scope("operator"),
            context_refs=[],
            output_contract={"proposal_kinds": ["learning"]},
        )
        first = ContextAssembler(
            _Controller({"objective": [{
                "id": "a", "kind": "objective", "status": "RUNNING",
                "payload": {"outcome": "Improve video render reliability"},
            }]}),
            RecordingHost(),
        ).build(request).retrieval_queries["history"]
        second = ContextAssembler(
            _Controller({"objective": [{
                "id": "b", "kind": "objective", "status": "RUNNING",
                "payload": {"outcome": "Reduce customer support response time"},
            }]}),
            RecordingHost(),
        ).build(request).retrieval_queries["history"]

        self.assertNotEqual(first, second)
        self.assertIn("render", first.lower())
        self.assertIn("support", second.lower())

    def test_capabilities_are_ranked_before_reasoning_limit(self):
        capabilities = [
            {
                "id": f"aiverse-skills:noise-{i}",
                "name": f"Unrelated capability {i}",
                "description": "Generic media formatting helper",
                "operators": [],
                "dependencies": [],
            }
            for i in range(80)
        ]
        relevant = {
            "id": "aiverse-skills:database-migration-guardian",
            "name": "Database Migration Guardian",
            "description": "Plan and verify a database migration with rollback and downtime safeguards.",
            "operators": ["database"],
            "dependencies": ["verification-harness"],
        }
        capabilities.append(relevant)

        controller = _Controller({
            "objective": [{
                "id": "obj-db",
                "kind": "objective",
                "scope": "operator",
                "status": "READY",
                "payload": {"outcome": "Perform the database migration with rollback and no downtime"},
            }],
        })
        host = RecordingHost(capabilities=capabilities)
        request = CognitionRequest(
            purpose=CognitionPurpose.OBJECTIVE_PLANNING,
            scope=Scope("operator"),
            context_refs=[],
            output_contract={"proposal_kinds": ["objective"]},
        )

        bundle = ContextAssembler(
            controller,
            host,
            max_capabilities=3,
            max_capability_candidates=100,
        ).build(request)

        self.assertEqual(len(bundle.capabilities), 3)
        self.assertEqual(bundle.capabilities[0]["id"], relevant["id"])
        self.assertIn("database", bundle.retrieval_queries["capabilities"].lower())
        self.assertIn("rollback", bundle.retrieval_queries["capabilities"].lower())

    def test_provider_v1_metadata_fields_contribute_to_ranking(self):
        items = [
            {
                "id": "aiverse-skills:plain",
                "name": "Plain Helper",
                "description": "General helper",
                "operators": [],
                "dependencies": [],
            },
            {
                "id": "aiverse-skills:workflow-agent",
                "name": "Workflow Agent",
                "description": "General helper",
                "operators": ["browser-workflow"],
                "dependencies": ["email-triage"],
            },
        ]
        ranked = rank_capabilities(
            items,
            "Use a browser workflow for email triage",
            limit=1,
            max_candidates=10,
        )
        self.assertEqual(ranked[0]["id"], "aiverse-skills:workflow-agent")

    def test_capability_candidate_overflow_fails_closed_instead_of_truncating(self):
        host = RecordingHost(capabilities=[
            {"id": f"cap-{i}", "name": f"Capability {i}", "description": "x"}
            for i in range(6)
        ])
        request = CognitionRequest(
            purpose=CognitionPurpose.OBJECTIVE_PLANNING,
            scope=Scope("operator"),
            context_refs=[],
            output_contract={"proposal_kinds": ["objective"]},
        )
        with self.assertRaisesRegex(ValidationError, "more than 5 capability candidates"):
            ContextAssembler(
                _Controller(),
                host,
                max_capabilities=2,
                max_capability_candidates=5,
            ).build(request)

    def test_query_is_bounded_even_with_large_host_context(self):
        request = CognitionRequest(
            purpose=CognitionPurpose.GAP_ANALYSIS,
            scope=Scope("operator"),
            context_refs=["host:event:large"],
            output_contract={"proposal_kinds": ["gap"]},
        )
        query = build_retrieval_query(
            request,
            {"current_context": "important-state " * 1000},
            [],
            target="history",
        )
        self.assertLessEqual(len(query), 2048)
        self.assertTrue(query.startswith("Recall prior facts"))

    def test_zero_score_ties_preserve_provider_order_deterministically(self):
        items = [
            {"id": "cap-z", "name": "Zeta", "description": "alpha"},
            {"id": "cap-a", "name": "Alpha", "description": "beta"},
        ]
        ranked = rank_capabilities(items, "quantum glacier", limit=2, max_candidates=10)
        self.assertEqual([item["id"] for item in ranked], ["cap-z", "cap-a"])


if __name__ == "__main__":
    unittest.main()
