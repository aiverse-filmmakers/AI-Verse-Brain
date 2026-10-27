import tempfile
import unittest

from aiverse_brain import AuthorityTier, BrainController
from aiverse_brain.errors import ValidationError


class IntentOwnerServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.controller = BrainController(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def capture(self, *, statement="Build a sustainable practice", operation_id="learn-1",
                source=AuthorityTier.EXPLICIT_USER, supersedes=None, expected_revision=None):
        return self.controller.intents.capture(
            "operator",
            subtype="goal",
            statement=statement,
            operation_id=operation_id,
            evidence_ref="host://session/turn/user-message-1",
            source=source,
            supersedes=supersedes,
            expected_revision=expected_revision,
        )

    def test_explicit_goal_is_saved_as_current_brain_intent(self):
        result = self.capture()
        self.assertEqual(result["state"], "saved")
        self.assertEqual(result["status"], "ACTIVE")
        self.assertTrue(result["changed"])
        snapshot = self.controller.intents.read("operator")
        item = next(row for row in snapshot["intents"] if row["id"] == result["ref"].split(":")[-1])
        self.assertEqual(item["statement"], "Build a sustainable practice")
        self.assertIn("host://session/turn/user-message-1", item["source_refs"])

    def test_inferred_intent_stays_proposed_and_out_of_current_snapshot(self):
        result = self.capture(source=AuthorityTier.TEMPORARY_HYPOTHESIS)
        self.assertEqual(result["state"], "awaiting-confirmation")
        self.assertEqual(result["status"], "PROPOSED")
        self.assertEqual(self.controller.intents.read("operator")["intents"], [])

    def test_explicit_correction_supersedes_exact_revision_and_replays_safely(self):
        first = self.capture()
        first_id = first["ref"].split(":")[-1]
        prior = self.controller.store.load("intent", "operator", first_id)
        correction = self.capture(
            statement="Build a sustainable and profitable practice",
            operation_id="learn-correction-1",
            supersedes=first_id,
            expected_revision=prior.revision,
        )
        self.assertEqual(correction["state"], "saved")
        self.assertEqual(self.controller.store.load("intent", "operator", first_id).status, "SUPERSEDED")
        self.assertEqual(self.controller.store.load("intent", "operator", correction["ref"].split(":")[-1]).status, "ACTIVE")

        replay = self.capture(
            statement="Build a sustainable and profitable practice",
            operation_id="learn-correction-1",
            supersedes=first_id,
            expected_revision=prior.revision,
        )
        self.assertTrue(replay["replayed"])
        self.assertFalse(replay["changed"])
        self.assertEqual(replay["ref"], correction["ref"])
        with self.assertRaisesRegex(ValidationError, "already superseded"):
            self.capture(
                statement="A competing correction",
                operation_id="learn-correction-2",
                supersedes=first_id,
                expected_revision=prior.revision,
            )

    def test_correction_preserves_existing_workspace_visibility_links(self):
        first = self.capture()
        first_id = first["ref"].split(":")[-1]
        prior = self.controller.store.load("intent", "operator", first_id)
        prior = self.controller.link_workspace_intent(
            prior.id,
            "workspace:alpha",
            expected_revision=prior.revision,
            operation_id="learn-link-alpha",
            evidence_ref="host://session/user-message-link",
        )
        correction = self.capture(
            statement="Build a sustainable practice with two weekly writing mornings",
            operation_id="learn-correction-with-link",
            supersedes=first_id,
            expected_revision=prior.revision,
        )
        corrected = self.controller.store.load(
            "intent", "operator", correction["ref"].split(":")[-1]
        )
        self.assertEqual(corrected.payload["workspace_links"], ["workspace:alpha"])

    def test_stale_correction_does_not_change_prior(self):
        first = self.capture()
        first_id = first["ref"].split(":")[-1]
        with self.assertRaisesRegex(ValidationError, "stale correction revision"):
            self.capture(
                statement="A different goal",
                operation_id="stale-correction",
                supersedes=first_id,
                expected_revision=self.controller.store.load("intent", "operator", first_id).revision + 1,
            )
        self.assertEqual(self.controller.store.load("intent", "operator", first_id).status, "ACTIVE")

    def test_owner_mismatch_does_not_write_a_second_strategic_store(self):
        self.controller.direction_owner = lambda scope: "os"
        result = self.capture()
        self.assertEqual(result["state"], "owner-required")
        self.assertEqual(self.controller.store.list("intent", "operator"), [])

    def test_correction_requires_explicit_user_source(self):
        first = self.capture()
        first_id = first["ref"].split(":")[-1]
        prior = self.controller.store.load("intent", "operator", first_id)
        with self.assertRaisesRegex(ValidationError, "explicit user declaration"):
            self.capture(
                statement="An inferred replacement",
                operation_id="inferred-correction",
                source=AuthorityTier.TEMPORARY_HYPOTHESIS,
                supersedes=first_id,
                expected_revision=prior.revision,
            )

    def test_operation_id_cannot_be_reused_with_different_intent(self):
        self.capture()
        with self.assertRaisesRegex(ValidationError, "different intent content"):
            self.capture(statement="Different content", operation_id="learn-1")


if __name__ == "__main__":
    unittest.main()
