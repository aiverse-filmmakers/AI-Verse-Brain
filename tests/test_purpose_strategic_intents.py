import tempfile
import unittest

from aiverse_brain import AuthorityTier, BrainController, build_purpose_snapshot
from aiverse_brain.errors import AuthorityError, ValidationError
from aiverse_brain.models import BrainObject
from aiverse_brain.validation import validate_payload


PURPOSE_SUBTYPES = ("problem", "mission", "strategy")


def _create_confirmed(controller, subtype, *, scope="operator", statement=None):
    return controller.create(
        "intent",
        scope,
        "CONFIRMED",
        {"subtype": subtype, "statement": statement or f"confirmed {subtype}"},
        source=AuthorityTier.EXPLICIT_USER,
        actor="user:test",
    )


class _ScopedStore:
    def __init__(self, objects):
        self.objects = list(objects)

    def list(self, kind, scope, statuses=None):
        return [
            obj for obj in self.objects
            if obj.kind == kind and obj.scope.value == scope and (statuses is None or obj.status in statuses)
        ]

    def load(self, kind, scope, object_id):
        for obj in self.objects:
            if obj.kind == kind and obj.scope.value == scope and obj.id == object_id:
                return obj
        raise KeyError((kind, scope, object_id))


class _ScopedController:
    def __init__(self, objects):
        self.store = _ScopedStore(objects)

    @staticmethod
    def direction_owner(scope):
        return "brain"


class PurposeStrategicIntentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.controller = BrainController(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_new_purpose_subtypes_are_valid_intent_payloads(self):
        for subtype in PURPOSE_SUBTYPES:
            with self.subTest(subtype=subtype):
                validate_payload("intent", {"subtype": subtype, "statement": f"one {subtype}"})

    def test_privileged_purpose_subtypes_cannot_be_directly_confirmed_by_model(self):
        for subtype in PURPOSE_SUBTYPES:
            with self.subTest(subtype=subtype):
                with self.assertRaises(AuthorityError):
                    self.controller.create(
                        "intent",
                        "operator",
                        "CONFIRMED",
                        {"subtype": subtype, "statement": "model suggestion"},
                        source=AuthorityTier.TEMPORARY_HYPOTHESIS,
                        actor="brain:test",
                    )

    def test_unconfirmed_candidates_are_not_current_purpose_truth(self):
        for subtype in PURPOSE_SUBTYPES:
            candidate = self.controller.create(
                "intent",
                "operator",
                "PROPOSED",
                {"subtype": subtype, "statement": f"candidate {subtype}"},
                source=AuthorityTier.TEMPORARY_HYPOTHESIS,
                actor="brain:test",
            )
            snapshot = build_purpose_snapshot(self.controller, "operator")
            ids = {item["id"] for item in snapshot["strategic_objects"]["intents"]}
            self.assertNotIn(candidate.id, ids)

    def test_confirmed_purpose_subtypes_have_exact_snapshot_semantics(self):
        expected = {"problem": "problem", "mission": "mission", "strategy": "strategy"}
        for subtype, semantic_kind in expected.items():
            obj = _create_confirmed(self.controller, subtype)
            snapshot = build_purpose_snapshot(self.controller, "operator")
            view = next(item for item in snapshot["strategic_objects"]["intents"] if item["id"] == obj.id)
            self.assertEqual(view["semantic_kind"], semantic_kind)
            self.assertEqual(view["canonical_ref"], {
                "owner": "ai-verse-brain",
                "scope": "operator",
                "kind": "intent",
                "id": obj.id,
                "version": str(obj.revision),
            })

    def test_paused_is_current_but_superseded_is_not(self):
        obj = _create_confirmed(self.controller, "strategy", statement="pause me")
        obj = self.controller.transition(
            "intent", "operator", obj.id, "ACTIVE",
            source=AuthorityTier.EXPLICIT_USER, actor="user:test",
        )
        obj = self.controller.transition(
            "intent", "operator", obj.id, "PAUSED",
            source=AuthorityTier.EXPLICIT_USER, actor="user:test",
        )
        snapshot = build_purpose_snapshot(self.controller, "operator")
        self.assertIn(obj.id, {item["id"] for item in snapshot["strategic_objects"]["intents"]})

        self.controller.transition(
            "intent", "operator", obj.id, "SUPERSEDED",
            source=AuthorityTier.EXPLICIT_USER, actor="user:test",
        )
        snapshot = build_purpose_snapshot(self.controller, "operator")
        self.assertNotIn(obj.id, {item["id"] for item in snapshot["strategic_objects"]["intents"]})

    def test_privileged_strategic_supersession_requires_explicit_user_authority(self):
        obj = _create_confirmed(self.controller, "mission")
        with self.assertRaises(AuthorityError):
            self.controller.transition(
                "intent", "operator", obj.id, "SUPERSEDED",
                source=AuthorityTier.VALIDATED_STRATEGY, actor="brain:test",
            )
        current = self.controller.store.load("intent", "operator", obj.id)
        self.assertEqual(current.status, "CONFIRMED")

    def test_candidate_supersedes_does_not_retire_prior_truth(self):
        prior = _create_confirmed(self.controller, "mission", statement="prior mission")
        candidate = self.controller.create(
            "intent",
            "operator",
            "PROPOSED",
            {"subtype": "mission", "statement": "replacement candidate"},
            source=AuthorityTier.TEMPORARY_HYPOTHESIS,
            actor="brain:test",
            supersedes=prior.id,
        )
        self.assertEqual(candidate.supersedes, prior.id)
        self.assertEqual(self.controller.store.load("intent", "operator", prior.id).status, "CONFIRMED")
        snapshot = build_purpose_snapshot(self.controller, "operator")
        ids = {item["id"] for item in snapshot["strategic_objects"]["intents"]}
        self.assertIn(prior.id, ids)
        self.assertNotIn(candidate.id, ids)

    def test_purpose_supersedes_requires_same_subtype(self):
        prior = _create_confirmed(self.controller, "problem")
        with self.assertRaises(ValidationError):
            self.controller.create(
                "intent",
                "operator",
                "PROPOSED",
                {"subtype": "mission", "statement": "not the same semantic chain"},
                source=AuthorityTier.TEMPORARY_HYPOTHESIS,
                actor="brain:test",
                supersedes=prior.id,
            )

    def test_purpose_supersedes_cannot_cross_scope(self):
        prior = BrainObject.new(
            "intent", "workspace:alpha", "CONFIRMED",
            {"subtype": "strategy", "statement": "alpha strategy"},
            created_by="user:test",
        )
        isolated = object.__new__(BrainController)
        isolated.store = _ScopedStore([prior])
        with self.assertRaises(KeyError):
            isolated._validate_purpose_supersedes(
                "workspace:beta",
                {"subtype": "strategy", "statement": "beta strategy"},
                prior.id,
            )

    def test_legacy_intents_are_not_reinterpreted_as_new_purpose_subtypes(self):
        legacy = _create_confirmed(
            self.controller,
            "desired_state",
            statement="A sentence that sounds like a mission",
        )
        snapshot = build_purpose_snapshot(self.controller, "operator")
        view = next(item for item in snapshot["strategic_objects"]["intents"] if item["id"] == legacy.id)
        self.assertEqual(view["payload"]["subtype"], "desired_state")
        self.assertEqual(view["semantic_kind"], "desired_outcome")

    def test_strategy_rule_is_not_reclassified_as_strategic_intent(self):
        self.controller.create(
            "strategy_rule",
            "operator",
            "CANDIDATE",
            {"evolution_tier": "E1", "applies_when": ["planning"], "instruction": ["prefer evidence"]},
            source=AuthorityTier.TEMPORARY_HYPOTHESIS,
            actor="brain:test",
        )
        snapshot = build_purpose_snapshot(self.controller, "operator")
        self.assertTrue(all(
            item["semantic_kind"] != "strategy"
            for item in snapshot["strategic_objects"]["intents"]
        ))

    def test_workspace_purpose_truth_is_exact_scope_only(self):
        alpha = BrainObject.new(
            "intent", "workspace:alpha", "CONFIRMED",
            {"subtype": "mission", "statement": "alpha mission"},
            created_by="user:test",
        )
        beta = BrainObject.new(
            "intent", "workspace:beta", "CONFIRMED",
            {"subtype": "mission", "statement": "beta mission"},
            created_by="user:test",
        )
        scoped = _ScopedController([alpha, beta])
        alpha_snapshot = build_purpose_snapshot(scoped, "workspace:alpha")
        ids = {item["id"] for item in alpha_snapshot["strategic_objects"]["intents"]}
        self.assertIn(alpha.id, ids)
        self.assertNotIn(beta.id, ids)


if __name__ == "__main__":
    unittest.main()
