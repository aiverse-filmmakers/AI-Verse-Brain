import json

from aiverse_brain import AuthorityTier, BrainController, build_purpose_snapshot


def test_purpose_snapshot_is_read_only_public_shape_without_storage_paths(tmp_path):
    controller = BrainController(str(tmp_path))
    goal = controller.create(
        "intent",
        "operator",
        "CONFIRMED",
        {"subtype": "goal", "statement": "Ship the public beta"},
        source=AuthorityTier.EXPLICIT_USER,
        actor="user:test",
    )

    snapshot = build_purpose_snapshot(controller, "operator")

    assert snapshot["schema_version"] == "1.0"
    assert snapshot["scope"] == "operator"
    assert snapshot["direction_owner"] == "brain"
    assert snapshot["status"] == "ok"
    assert snapshot["strategic_objects"]["intents"][0]["id"] == goal.id
    assert snapshot["strategic_objects"]["intents"][0]["canonical_ref"] == {
        "owner": "ai-verse-brain",
        "scope": "operator",
        "kind": "intent",
        "id": goal.id,
        "version": str(goal.revision),
    }

    encoded = json.dumps(snapshot, sort_keys=True)
    assert str(tmp_path) not in encoded
    assert ".ai-verse-brain" not in encoded
    assert "runtime/" not in encoded
    assert "storage" not in snapshot
    assert "path" not in snapshot


def test_purpose_snapshot_does_not_expose_non_current_intent(tmp_path):
    controller = BrainController(str(tmp_path))
    controller.create(
        "intent",
        "operator",
        "DRAFT",
        {"subtype": "goal", "statement": "Unconfirmed draft"},
        source=AuthorityTier.TEMPORARY_HYPOTHESIS,
        actor="brain:test",
    )

    snapshot = build_purpose_snapshot(controller, "operator")
    assert snapshot["strategic_objects"]["intents"] == []
