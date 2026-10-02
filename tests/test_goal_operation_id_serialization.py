from concurrent.futures import ThreadPoolExecutor
import tempfile
import threading
import unittest

from aiverse_brain.controller import BrainController
from aiverse_brain.errors import ValidationError
from aiverse_brain.installation import initialize


IDEMPOTENCY_MESSAGE = "operation_id was already used with a different Goal mutation payload"


class GoalOperationIdSerializationTests(unittest.TestCase):
    def _run_cross_goal_conflict(self, service, operation_id, left_call, right_call):
        original_begin = service._begin
        barrier = threading.Barrier(2)
        calls = threading.local()

        def synchronized_begin(scope, current_operation_id, request):
            if current_operation_id == operation_id:
                seen = getattr(calls, "seen", 0)
                calls.seen = seen + 1
                if seen == 0:
                    barrier.wait(timeout=5)
            return original_begin(scope, current_operation_id, request)

        service._begin = synchronized_begin
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(left_call), executor.submit(right_call)]
                outcomes = []
                for future in futures:
                    try:
                        outcomes.append(("ok", future.result(timeout=10)))
                    except Exception as exc:
                        outcomes.append(("error", exc))
        finally:
            service._begin = original_begin

        successes = [value for kind, value in outcomes if kind == "ok"]
        errors = [value for kind, value in outcomes if kind == "error"]
        self.assertEqual(len(successes), 1, outcomes)
        self.assertEqual(len(errors), 1, outcomes)
        self.assertIsInstance(errors[0], ValidationError)
        self.assertEqual(str(errors[0]), IDEMPOTENCY_MESSAGE)
        return successes[0]

    def _new_goal_pair(self, service, prefix):
        left = service.create(
            "operator",
            objective=f"{prefix} left",
            operation_id=f"{prefix}-create-left",
        ).goal
        right = service.create(
            "operator",
            objective=f"{prefix} right",
            operation_id=f"{prefix}-create-right",
        ).goal
        return left, right

    def _assert_exactly_one_revision_advanced(self, service, left, right, winner):
        current_left = service.get("operator", left["goal_id"])
        current_right = service.get("operator", right["goal_id"])
        deltas = [
            current_left["version"] - left["version"],
            current_right["version"] - right["version"],
        ]
        self.assertEqual(sorted(deltas), [0, 1])
        winner_now = service.get("operator", winner.goal["goal_id"])
        self.assertEqual(winner_now["version"], winner.goal["version"])
        return current_left, current_right

    def test_cross_goal_same_operation_id_edit_commits_exactly_one_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            initialize(temp)
            service = BrainController(temp).goals
            left, right = self._new_goal_pair(service, "edit")
            operation_id = "shared-edit-operation"

            winner = self._run_cross_goal_conflict(
                service,
                operation_id,
                lambda: service.edit(
                    "operator",
                    left["goal_id"],
                    expected_version=left["version"],
                    operation_id=operation_id,
                    objective="edited left",
                ),
                lambda: service.edit(
                    "operator",
                    right["goal_id"],
                    expected_version=right["version"],
                    operation_id=operation_id,
                    objective="edited right",
                ),
            )

            current_left, current_right = self._assert_exactly_one_revision_advanced(
                service, left, right, winner
            )
            changed = [
                current_left["objective"] != left["objective"],
                current_right["objective"] != right["objective"],
            ]
            self.assertEqual(sum(changed), 1)
            receipt = service._receipt("operator", operation_id)
            self.assertEqual(receipt["goal_id"], winner.goal["goal_id"])
            self.assertEqual(receipt["goal_version"], winner.goal["version"])

    def test_cross_goal_same_operation_id_transition_commits_exactly_one_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            initialize(temp)
            service = BrainController(temp).goals
            left, right = self._new_goal_pair(service, "transition")
            operation_id = "shared-transition-operation"

            winner = self._run_cross_goal_conflict(
                service,
                operation_id,
                lambda: service.transition(
                    "operator",
                    left["goal_id"],
                    expected_version=left["version"],
                    operation_id=operation_id,
                    action="pause",
                ),
                lambda: service.transition(
                    "operator",
                    right["goal_id"],
                    expected_version=right["version"],
                    operation_id=operation_id,
                    action="pause",
                ),
            )

            current_left, current_right = self._assert_exactly_one_revision_advanced(
                service, left, right, winner
            )
            self.assertEqual(
                sorted([current_left["status"], current_right["status"]]),
                ["active", "paused"],
            )

    def test_cross_goal_same_operation_id_criteria_mutation_commits_exactly_one(self):
        with tempfile.TemporaryDirectory() as temp:
            initialize(temp)
            service = BrainController(temp).goals
            left, right = self._new_goal_pair(service, "criteria")
            operation_id = "shared-criteria-operation"

            winner = self._run_cross_goal_conflict(
                service,
                operation_id,
                lambda: service.criteria_add(
                    "operator",
                    left["goal_id"],
                    expected_version=left["version"],
                    operation_id=operation_id,
                    criterion={"id": "left-proof", "statement": "left proof"},
                ),
                lambda: service.criteria_add(
                    "operator",
                    right["goal_id"],
                    expected_version=right["version"],
                    operation_id=operation_id,
                    criterion={"id": "right-proof", "statement": "right proof"},
                ),
            )

            current_left, current_right = self._assert_exactly_one_revision_advanced(
                service, left, right, winner
            )
            self.assertEqual(
                sorted([len(current_left["criteria"]), len(current_right["criteria"])]),
                [0, 1],
            )

    def test_cross_goal_same_operation_id_progress_commits_exactly_one_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            initialize(temp)
            service = BrainController(temp).goals
            left, right = self._new_goal_pair(service, "progress")
            operation_id = "shared-progress-operation"

            winner = self._run_cross_goal_conflict(
                service,
                operation_id,
                lambda: service.record_progress(
                    "operator",
                    left["goal_id"],
                    expected_version=left["version"],
                    operation_id=operation_id,
                    progress_token="left-progress",
                    tokens_used=5,
                ),
                lambda: service.record_progress(
                    "operator",
                    right["goal_id"],
                    expected_version=right["version"],
                    operation_id=operation_id,
                    progress_token="right-progress",
                    tokens_used=7,
                ),
            )

            current_left, current_right = self._assert_exactly_one_revision_advanced(
                service, left, right, winner
            )
            self.assertEqual(
                sorted([
                    current_left["progress"]["attempts"],
                    current_right["progress"]["attempts"],
                ]),
                [0, 1],
            )
            self.assertEqual(
                sorted([
                    current_left["progress"]["tokens_used"],
                    current_right["progress"]["tokens_used"],
                ]),
                [0, winner.goal["progress"]["tokens_used"]],
            )

    def test_operation_id_equal_to_goal_id_does_not_self_conflict(self):
        with tempfile.TemporaryDirectory() as temp:
            initialize(temp)
            service = BrainController(temp).goals
            goal = service.create(
                "operator",
                objective="self-lock edge",
                operation_id="self-lock-create",
            ).goal

            edited = service.edit(
                "operator",
                goal["goal_id"],
                expected_version=goal["version"],
                operation_id=goal["goal_id"],
                objective="self-lock edge edited",
            ).goal

            self.assertEqual(edited["objective"], "self-lock edge edited")
            self.assertEqual(edited["version"], goal["version"] + 1)


if __name__ == "__main__":
    unittest.main()
