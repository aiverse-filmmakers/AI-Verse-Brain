import pytest

from aiverse_brain import AuthorityTier, BrainController, build_purpose_snapshot
from aiverse_brain.errors import AuthorityError, ValidationError
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


@pytest.mark.parametrize("subtype", PURPOSE_SUBTYPES)
def test_new_purpose_subtypes_are_valid_intent_payloads(subtype):
    validate_payload("intent", {"subtype": subtype, "statement": f"one {subtype}"})


@pytest.mark.parametrize("subtype", PURPOSE_SUBTYPES)
def test_privileged_purpose_subtypes_cannot_be_directly_confirmed_by_model(subtype, tmp_path):
    controller = BrainController(str(tmp_path))
    with pytest.raises(AuthorityError):
        controller.create(
            "intent",
            "operator",
            "CONFIRMED",
            {"subtype": subtype, "statement": "model suggestion"},
            source=AuthorityTier.TEMPORARY_HYPOTHESIS,
            actor="brain:test",
        )


@pytest.mark.parametrize("subtype", PURPOSE_SUBTYPES)
def test_unconfirmed_candidate_is_not_current_purpose_truth(subtype, tmp_path):
    controller = BrainController(str(tmp_path))
    candidate = controller.create(
        "intent",
        "operator",
        "PROPOSED",
        {"subtype": subtype, "statement": "candidate"},
        source=AuthorityTier.TEMPORARY_HYPOTHESIS,
        actor="brain:test",
    )
    snapshot = build_purpose_snapshot(controller, "operator")
    ids = {item["id"] for item in snapshot["strategic_objects"]["intents"]}
    assert candidate.id not in ids


@pytest.mark.parametrize(
    ("subtype", "semantic_kind"),
    (("problem", "problem"), ("mission", "mission"), ("strategy", "strategy")),
)
def test_confirmed_purpose_subtypes_have_exact_snapshot_semantics(subtype, semantic_kind, tmp_path):
    controller = BrainController(str(tmp_path))
    obj = _create_confirmed(controller, subtype)
    snapshot = build_purpose_snapshot(controller, "operator")
    view = next(item for item in snapshot["strategic_objects"]["intents"] if item["id"] == obj.id)
    assert view["semantic_kind"] == semantic_kind
    assert view["canonical_ref"] == {
        "owner": "ai-verse-brain",
        "scope": "operator",
        "kind": "intent",
        "id": obj.id,
        "version": str(obj.revision),
    }


def test_paused_is_current_but_superseded_is_not(tmp_path):
    controller = BrainController(str(tmp_path))
    paused = _create_confirmed(controller, "strategy", statement="pause me")
    paused = controller.transition(
        "intent", "operator", paused.id, "ACTIVE",
        source=AuthorityTier.EXPLICIT_USER, actor="user:test",
    )
    paused = controller.transition(
        "intent", "operator", paused.id, "PAUSED",
        source=AuthorityTier.EXPLICIT_USER, actor="user:test",
    )
    snapshot = build_purpose_snapshot(controller, "operator")
    assert paused.id in {item["id"] for item in snapshot["strategic_objects"]["intents"]}

    controller.transition(
        "intent", "operator", paused.id, "SUPERSEDED",
        source=AuthorityTier.EXPLICIT_USER, actor="user:test",
    )
    snapshot = build_purpose_snapshot(controller, "operator")
    assert paused.id not in {item["id"] for item in snapshot["strategic_objects"]["intents"]}


def test_privileged_strategic_supersession_requires_explicit_user_authority(tmp_path):
    controller = BrainController(str(tmp_path))
    obj = _create_confirmed(controller, "mission")
    with pytest.raises(AuthorityError):
        controller.transition(
            "intent", "operator", obj.id, "SUPERSEDED",
            source=AuthorityTier.VALIDATED_STRATEGY, actor="brain:test",
        )
    current = controller.store.load("intent", "operator", obj.id)
    assert current.status == "CONFIRMED"


def test_candidate_supersedes_does_not_retire_prior_truth(tmp_path):
    controller = BrainController(str(tmp_path))
    prior = _create_confirmed(controller, "mission", statement="prior mission")
    candidate = controller.create(
        "intent",
        "operator",
        "PROPOSED",
        {"subtype": "mission", "statement": "replacement candidate"},
        source=AuthorityTier.TEMPORARY_HYPOTHESIS,
        actor="brain:test",
        supersedes=prior.id,
    )
    assert candidate.supersedes == prior.id
    assert controller.store.load("intent", "operator", prior.id).status == "CONFIRMED"
    snapshot = build_purpose_snapshot(controller, "operator")
    assert prior.id in {item["id"] for item in snapshot["strategic_objects"]["intents"]}
    assert candidate.id not in {item["id"] for item in snapshot["strategic_objects"]["intents"]}


def test_purpose_supersedes_requires_same_subtype(tmp_path):
    controller = BrainController(str(tmp_path))
    prior = _create_confirmed(controller, "problem")
    with pytest.raises(ValidationError):
        controller.create(
            "intent",
            "operator",
            "PROPOSED",
            {"subtype": "mission", "statement": "not the same semantic chain"},
            source=AuthorityTier.TEMPORARY_HYPOTHESIS,
            actor="brain:test",
            supersedes=prior.id,
        )


def test_purpose_supersedes_cannot_cross_scope(tmp_path):
    controller = BrainController(str(tmp_path))
    prior = _create_confirmed(controller, "strategy", scope="workspace:alpha")
    with pytest.raises(Exception):
        controller.create(
            "intent",
            "workspace:beta",
            "PROPOSED",
            {"subtype": "strategy", "statement": "cross-scope replacement"},
            source=AuthorityTier.TEMPORARY_HYPOTHESIS,
            actor="brain:test",
            supersedes=prior.id,
        )


def test_legacy_intents_are_not_reinterpreted_as_new_purpose_subtypes(tmp_path):
    controller = BrainController(str(tmp_path))
    legacy = _create_confirmed(controller, "desired_state", statement="A sentence that sounds like a mission")
    snapshot = build_purpose_snapshot(controller, "operator")
    view = next(item for item in snapshot["strategic_objects"]["intents"] if item["id"] == legacy.id)
    assert view["payload"]["subtype"] == "desired_state"
    assert view["semantic_kind"] == "desired_outcome"


def test_strategy_rule_is_not_reclassified_as_strategic_intent(tmp_path):
    controller = BrainController(str(tmp_path))
    controller.create(
        "strategy_rule",
        "operator",
        "CANDIDATE",
        {"evolution_tier": "E1", "applies_when": ["planning"], "instruction": ["prefer evidence"]},
        source=AuthorityTier.TEMPORARY_HYPOTHESIS,
        actor="brain:test",
    )
    snapshot = build_purpose_snapshot(controller, "operator")
    assert all(item["semantic_kind"] != "strategy" for item in snapshot["strategic_objects"]["intents"])


def test_workspace_purpose_truth_is_exact_scope_only(tmp_path):
    controller = BrainController(str(tmp_path))
    alpha = _create_confirmed(controller, "mission", scope="workspace:alpha", statement="alpha mission")
    beta = _create_confirmed(controller, "mission", scope="workspace:beta", statement="beta mission")
    alpha_snapshot = build_purpose_snapshot(controller, "workspace:alpha")
    ids = {item["id"] for item in alpha_snapshot["strategic_objects"]["intents"]}
    assert alpha.id in ids
    assert beta.id not in ids
