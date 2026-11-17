from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_release_record.py"
spec = importlib.util.spec_from_file_location("check_release_record", SCRIPT)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)

DISPLAY = "0.1.0-beta.3.dev3"


def git(repo, *args):
    out = subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        check=True, capture_output=True, text=True,
    )
    return out.stdout.strip()


def write(repo, rel, text):
    path = Path(repo) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def record(revision, version=DISPLAY, ci="1", acceptance="2"):
    return {
        "schema_version": guard.SCHEMA,
        "version": version,
        "revision": revision,
        "release_status": "accepted",
        "evidence": {"ci": [{"run_id": ci}], "acceptance": [{"run_id": acceptance}]},
    }


class ReleaseRecordGuardTests(unittest.TestCase):
    def make_repo(self, code_version=DISPLAY):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        repo = Path(tmp.name)
        git(repo, "init", "-q")
        pep = guard.to_pep440(code_version)
        write(repo, "engine/aiverse_brain/_version.py",
              f'__version__ = "{pep}"\nDISPLAY_VERSION = "{code_version}"\n')
        write(repo, "BRAIN.yaml", f'version: "{code_version}"\n')
        write(repo, "README.md", f"Status {code_version}\n")
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "code")
        return repo, git(repo, "rev-parse", "HEAD")

    def put_record(self, repo, data):
        write(repo, guard.RECORD_PATH, json.dumps(data))

    def test_matching_record_passes(self):
        repo, sha = self.make_repo()
        self.put_record(repo, record(sha))
        self.assertEqual(guard.check(repo), ([], []))

    def test_version_mismatch_at_accepted_commit_fails(self):
        repo, sha = self.make_repo(code_version="0.1.0-beta.3.dev0")
        self.put_record(repo, record(sha))
        problems, _ = guard.check(repo)
        self.assertTrue(any("_version.py" in p for p in problems))
        self.assertTrue(any("BRAIN.yaml" in p for p in problems))

    def test_reads_code_at_accepted_commit_not_head(self):
        repo, sha = self.make_repo(code_version="0.1.0-beta.3.dev0")
        write(repo, "engine/aiverse_brain/_version.py",
              f'__version__ = "{guard.to_pep440(DISPLAY)}"\nDISPLAY_VERSION = "{DISPLAY}"\n')
        write(repo, "BRAIN.yaml", f'version: "{DISPLAY}"\n')
        write(repo, "README.md", DISPLAY + "\n")
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "later fix")
        self.put_record(repo, record(sha))
        problems, _ = guard.check(repo)
        self.assertTrue(problems)

    def test_missing_commit_fails(self):
        repo, _ = self.make_repo()
        self.put_record(repo, record("a" * 40))
        problems, _ = guard.check(repo)
        self.assertTrue(any("does not exist" in p for p in problems))

    def test_duplicate_run_id_fails(self):
        repo, sha = self.make_repo()
        self.put_record(repo, record(sha, ci="7", acceptance="7"))
        problems, _ = guard.check(repo)
        self.assertTrue(any("listed twice" in p for p in problems))

    def test_malformed_record_fails(self):
        repo, _ = self.make_repo()
        write(repo, guard.RECORD_PATH, "{not json")
        problems, _ = guard.check(repo)
        self.assertTrue(any("cannot be read" in p for p in problems))

    def test_missing_record_fails(self):
        repo, _ = self.make_repo()
        problems, _ = guard.check(repo)
        self.assertTrue(problems)

    def test_stale_warns_but_does_not_fail(self):
        repo, sha = self.make_repo()
        self.put_record(repo, record(sha))
        git(repo, "add", "-A")
        for i in range(guard.STALE_AFTER_COMMITS + 1):
            git(repo, "commit", "-q", "--allow-empty", "-m", f"c{i}")
        problems, warnings = guard.check(repo)
        self.assertEqual(problems, [])
        self.assertEqual(len(warnings), 1)

    def test_not_stale_at_limit(self):
        repo, sha = self.make_repo()
        self.put_record(repo, record(sha))
        for i in range(guard.STALE_AFTER_COMMITS):
            git(repo, "commit", "-q", "--allow-empty", "-m", f"c{i}")
        self.assertEqual(guard.check(repo)[1], [])

    def test_version_form_conversion(self):
        self.assertEqual(guard.to_pep440("0.1.0-beta.3.dev3"), "0.1.0b3.dev3")
        self.assertEqual(guard.to_pep440("1.2.3"), "1.2.3")
        self.assertIsNone(guard.to_pep440("nonsense"))


if __name__ == "__main__":
    unittest.main()
