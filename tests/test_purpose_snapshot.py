import json
import tempfile
import unittest

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


class PurposeWorkspaceLinkSnapshotTests(unittest.TestCase):
    def test_snapshot_exposes_only_exact_operator_link_and_redacts_other_links(self):
        with tempfile.TemporaryDirectory() as root:
            controller = BrainController(root)
            goal = controller.create(
                "intent", "operator", "CONFIRMED",
                {"subtype": "goal", "statement": "Protect creative time",
                 "workspace_links": ["workspace:alpha", "workspace:beta"],
                 "workspace_link_operations": [
                     {"id": "op-secret-beta", "action": "add", "workspace_scope": "workspace:beta",
                      "evidence_ref": "turn:private"}]},
                source=AuthorityTier.EXPLICIT_USER, actor="user:test",
            )
            snapshot = build_purpose_snapshot(controller, "workspace:alpha")
            linked = snapshot["linked_operator_intents"][0]
            self.assertEqual(linked["id"], goal.id)
            self.assertEqual(linked["linked_to_scope"], "workspace:alpha")
            self.assertNotIn("workspace_links", linked["payload"])
            self.assertNotIn("workspace_link_operations", linked["payload"])
            self.assertNotIn("workspace:beta", json.dumps(linked))
            operator_snapshot = build_purpose_snapshot(controller, "operator")
            self.assertNotIn("workspace_links", json.dumps(operator_snapshot))
            self.assertNotIn("workspace_link_operations", json.dumps(operator_snapshot))

    def test_snapshot_includes_operator_link_while_workspace_direction_is_os(self):
        with tempfile.TemporaryDirectory() as root:
            controller = BrainController(root)
            goal = controller.create(
                "intent", "operator", "CONFIRMED",
                {"subtype": "goal", "statement": "Protect creative time",
                 "workspace_links": ["workspace:alpha"]},
                source=AuthorityTier.EXPLICIT_USER, actor="user:test",
            )
            original_owner = controller.direction_owner
            controller.direction_owner = lambda scope: "os" if scope == "workspace:alpha" else original_owner(scope)
            snapshot = build_purpose_snapshot(controller, "workspace:alpha")
            self.assertEqual(snapshot["direction_owner"], "os")
            self.assertEqual(snapshot["status"], "unavailable")
            self.assertEqual(snapshot["linked_operator_intents"][0]["id"], goal.id)
            self.assertEqual(snapshot["strategic_objects"]["intents"], [])
