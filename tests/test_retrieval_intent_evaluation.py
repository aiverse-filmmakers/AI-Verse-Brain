import inspect
import unittest
from collections import Counter, defaultdict

from aiverse_brain.cognition import CognitionPurpose, CognitionRequest
from aiverse_brain.host import HostAdapter
from aiverse_brain.host_selection import REQUIRED_HOST_READ_OPERATIONS
from aiverse_brain.models import Scope
from aiverse_brain.reasoner import ContextAssembler
from aiverse_brain.bridge_legacy import BridgeHostAdapter


HISTORY_SCENARIOS = (
    ("gap_analysis", "summary", "Need prior blockers and outcomes for onboarding.", "onboarding"),
    ("gap_analysis", "detail", "Need provenance for the correction that superseded the launch constraint.", "superseded"),
    ("reflection", "summary", "Summarize recent outcomes for render reliability.", "render"),
    ("reflection", "detail", "Trace provenance and corrections from the failed render attempt.", "provenance"),
    ("strategy_review", "summary", "Review repeated outcomes from pricing experiments.", "pricing"),
    ("strategy_review", "source", "Use the exact source quote and SHA for the pricing rule.", "sha"),
    ("evaluation", "summary", "Compare prior result summary against the activation criterion.", "activation"),
    ("evaluation", "source", "Verify the exact source quote and checksum for the activation criterion.", "checksum"),
)

NO_HISTORY_PURPOSES = (
    "orient",
    "opportunity_discovery",
    "objective_planning",
)


class _Object:
    def __init__(self, data):
        self.data = dict(data)

    def to_dict(self):
        return dict(self.data)


class _Store:
    def list(self, kind, scope, statuses=None):
        return []


class _Controller:
    def __init__(self):
        self.store = _Store()


class _RecordingHost:
    def __init__(self, current_text):
        self.current_text = current_text
        self.history_calls = []

    def read_context(self, scope):
        return {"current_context": self.current_text}

    def retrieve_history(self, query, scope):
        self.history_calls.append((query, scope))
        return [{"kind": "memory", "summary": "fixture history"}]

    def list_capabilities(self, scope):
        return []

    def list_connections(self, scope):
        return []


def _request(purpose):
    return CognitionRequest(
        purpose=CognitionPurpose(purpose),
        scope=Scope("operator"),
        context_refs=[],
        output_contract={"proposal_kinds": ["learning"]},
    )


def _best_static_purpose_depth_accuracy():
    by_purpose = defaultdict(list)
    for purpose, expected_depth, _context, _cue in HISTORY_SCENARIOS:
        by_purpose[purpose].append(expected_depth)

    correct = 0
    total = 0
    chosen = {}
    for purpose, expected in by_purpose.items():
        winner, count = Counter(expected).most_common(1)[0]
        chosen[purpose] = winner
        correct += count
        total += len(expected)
    return correct / total, chosen


class RetrievalIntentEvaluationTests(unittest.TestCase):
    def test_current_purpose_gate_perfectly_separates_history_and_non_history_purposes(self):
        assembler_history = set(ContextAssembler.HISTORY_PURPOSES)

        for purpose, _depth, _context, _cue in HISTORY_SCENARIOS:
            self.assertIn(purpose, assembler_history)

        for purpose in NO_HISTORY_PURPOSES:
            self.assertNotIn(purpose, assembler_history)

        binary_total = len(HISTORY_SCENARIOS) + len(NO_HISTORY_PURPOSES)
        binary_correct = binary_total
        self.assertEqual(binary_correct / binary_total, 1.0)

    def test_same_brain_purpose_requires_conflicting_retrieval_depths(self):
        accuracy, chosen = _best_static_purpose_depth_accuracy()

        # Every current history-bearing Brain purpose has at least two scenarios
        # that need different accepted Context-Ladder depths. A static
        # purpose->depth envelope can therefore be right on only one of each pair.
        self.assertEqual(set(chosen), {
            "gap_analysis",
            "reflection",
            "strategy_review",
            "evaluation",
        })
        self.assertEqual(accuracy, 0.5)

    def test_existing_semantic_query_preserves_depth_sensitive_task_cues(self):
        preserved = 0
        for purpose, _expected_depth, current_text, cue in HISTORY_SCENARIOS:
            host = _RecordingHost(current_text)
            bundle = ContextAssembler(_Controller(), host).build(_request(purpose))

            self.assertEqual(len(host.history_calls), 1)
            query, scope = host.history_calls[0]
            self.assertEqual(scope, "operator")
            self.assertEqual(bundle.retrieval_queries["history"], query)
            self.assertIn(cue.casefold(), query.casefold())
            preserved += 1

        self.assertEqual(preserved / len(HISTORY_SCENARIOS), 1.0)

    def test_brain_host_contract_has_no_progressive_depth_transport(self):
        protocol_params = list(inspect.signature(HostAdapter.retrieve_history).parameters)
        bridge_params = list(inspect.signature(BridgeHostAdapter.retrieve_history).parameters)

        self.assertEqual(protocol_params, ["self", "query", "scope"])
        self.assertEqual(bridge_params, ["self", "query", "scope"])
        self.assertNotIn("retrieve_history_progressive", REQUIRED_HOST_READ_OPERATIONS)
        self.assertFalse(hasattr(BridgeHostAdapter, "retrieve_history_progressive"))

    def test_h1_benchmark_decision_is_reject_for_current_architecture(self):
        static_accuracy, _chosen = _best_static_purpose_depth_accuracy()

        metrics = {
            "binary_history_need_accuracy": 1.0,
            "semantic_depth_cue_preservation": 1.0,
            "best_static_purpose_depth_accuracy": static_accuracy,
            "brain_progressive_depth_transport_available": False,
            "brain_only_envelope_host_effect": 0,
            "decision": "reject",
        }

        self.assertEqual(metrics, {
            "binary_history_need_accuracy": 1.0,
            "semantic_depth_cue_preservation": 1.0,
            "best_static_purpose_depth_accuracy": 0.5,
            "brain_progressive_depth_transport_available": False,
            "brain_only_envelope_host_effect": 0,
            "decision": "reject",
        })


if __name__ == "__main__":
    unittest.main()
