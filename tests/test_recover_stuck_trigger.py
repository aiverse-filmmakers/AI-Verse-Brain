"""A crashed scheduled run must not keep its slot forever (FL-28).

A tick claims its trigger slot first. If the process dies mid tick the receipt
stays "claimed" and every later run with the same key fails as a duplicate.
Brain deliberately never replays such a run on its own (it may have done part of
the work), so recovery is an explicit command that existed only as an unused
function. These tests drive that command and the error message pointing to it.
"""
import contextlib
import io
import json
import os
import tempfile
import time
import unittest

from aiverse_brain.cadence import Trigger
from aiverse_brain.cli import main as cli_main
from aiverse_brain.controller import BrainController
from aiverse_brain.errors import DuplicateTrigger
from aiverse_brain.installation import initialize
from aiverse_brain.models import Scope


class RecoverStuckTrigger(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        initialize(self.root)
        self.trigger = Trigger("scheduled_orientation", Scope("operator"), "daily-2026-11-23")

    def tearDown(self):
        self.tmp.cleanup()

    def crash_after_claim(self, age_seconds=3600):
        # What a crash leaves behind: a claimed receipt that was never completed.
        ledger = BrainController(self.root).trigger_ledger
        path = ledger.claim(self.trigger)
        past = time.time() - age_seconds
        os.utime(path, (past, past))
        return ledger

    def recover(self, *extra):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = cli_main(["recover-trigger", self.root, "--key", self.trigger.idempotency_key, *extra])
        return rc, json.loads(out.getvalue())

    def test_duplicate_error_for_a_crashed_claim_names_the_recovery_command(self):
        self.crash_after_claim()
        with self.assertRaises(DuplicateTrigger) as caught:
            BrainController(self.root).run_trigger(self.trigger)
        self.assertIn("recover-trigger", str(caught.exception))

    def test_recover_command_frees_the_slot_so_the_run_can_happen(self):
        self.crash_after_claim()
        rc, data = self.recover()
        self.assertEqual(rc, 0, data)
        self.assertTrue(data["recovered"])
        BrainController(self.root).run_trigger(self.trigger)  # no DuplicateTrigger now
        self.assertEqual(BrainController(self.root).trigger_ledger.claim_status(self.trigger.idempotency_key), "completed")

    def test_completed_run_is_never_cleared(self):
        BrainController(self.root).run_trigger(self.trigger)
        rc, data = self.recover("--min-age-seconds", "0")
        self.assertNotEqual(rc, 0)
        self.assertFalse(data["recovered"])
        self.assertIn("completed", data["reason"])

    def test_young_claim_is_left_alone_because_a_run_may_still_be_active(self):
        self.crash_after_claim(age_seconds=0)
        rc, data = self.recover()
        self.assertNotEqual(rc, 0)
        self.assertEqual(data["status_before"], "claimed")
        self.assertIn("still be active", data["reason"])

    def test_unknown_key_reports_cleanly(self):
        rc, data = self.recover()
        self.assertNotEqual(rc, 0)
        self.assertIn("no receipt", data["reason"])


if __name__ == "__main__":
    unittest.main()
