import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from aiverse_brain.adoption import apply_standalone_adoption, plan_standalone_adoption
from aiverse_brain.errors import ScopeError, ValidationError
from aiverse_brain.installation import initialize, plan_init, read_installation_marker
from aiverse_brain.integration import HostMode, inspect_host, native_path_contract
from aiverse_brain.models import Scope
from aiverse_brain.runtime_lock import RuntimeKeyLock
from aiverse_brain.storage import StorageLayout


def _make_dir_link(target: Path, link: Path) -> None:
    if os.name == "nt":
        completed = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"cannot create Windows junction: {completed.stderr or completed.stdout}")
    else:
        os.symlink(str(target), str(link), target_is_directory=True)


def _remove_path(path: Path) -> None:
    if not os.path.lexists(path):
        return
    if path.is_symlink():
        path.unlink()
        return
    if os.name == "nt":
        # A Windows directory junction must be removed as a directory entry, not
        # recursively traversed into its target.
        try:
            path.rmdir()
            return
        except OSError:
            pass
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def _replace_with_dir_link(path: Path, target: Path) -> None:
    _remove_path(path)
    _make_dir_link(target, path)


def _native_root(root: Path) -> None:
    (root / "AI-VERSE.yaml").write_text(
        'schema_version: "2.0"\narchitecture: unified-workspace\n', encoding="utf-8"
    )
    (root / "operator").mkdir()
    (root / "workspaces").mkdir()


class NativePathContainmentTests(unittest.TestCase):
    def test_operator_parent_symlink_or_junction_makes_native_host_incompatible(self):
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as outside:
            root = Path(temp)
            external = Path(outside)
            sentinel = external / "sentinel.txt"
            sentinel.write_text("keep", encoding="utf-8")
            _native_root(root)
            _replace_with_dir_link(root / "operator", external)

            report = inspect_host(str(root))
            self.assertEqual(report.mode, HostMode.INCOMPATIBLE_AI_VERSE)
            self.assertFalse(report.compatible)
            self.assertTrue(any("unsafe AI-Verse native path layout" in item for item in report.warnings))
            plan = plan_init(str(root))
            self.assertFalse(plan.safe_to_apply)
            with self.assertRaises(ValidationError):
                initialize(str(root))
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")
            self.assertFalse((external / "brain").exists())

    def test_workspaces_parent_symlink_or_junction_makes_native_host_incompatible(self):
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as outside:
            root = Path(temp)
            external = Path(outside)
            sentinel = external / "sentinel.txt"
            sentinel.write_text("keep", encoding="utf-8")
            _native_root(root)
            _replace_with_dir_link(root / "workspaces", external)

            report = inspect_host(str(root))
            self.assertEqual(report.mode, HostMode.INCOMPATIBLE_AI_VERSE)
            self.assertFalse(plan_init(str(root)).safe_to_apply)
            with self.assertRaises(ValidationError):
                initialize(str(root))
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")

    def test_workspace_symlink_or_junction_cannot_escape_state_scope(self):
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as outside:
            root = Path(temp)
            external = Path(outside)
            (external / "sentinel.txt").write_text("keep", encoding="utf-8")
            _native_root(root)
            _make_dir_link(external, root / "workspaces" / "alpha")

            layout = StorageLayout.detect(root)
            with self.assertRaises(ScopeError):
                layout.state_root(Scope("workspace:alpha"))
            with self.assertRaises((ScopeError, ValidationError)):
                native_path_contract(str(root), "workspace:alpha")
            self.assertEqual((external / "sentinel.txt").read_text(encoding="utf-8"), "keep")
            self.assertFalse((external / "brain").exists())

    def test_operator_brain_symlink_or_junction_blocks_initialization_and_marker_write(self):
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as outside:
            root = Path(temp)
            external = Path(outside)
            sentinel = external / "sentinel.txt"
            sentinel.write_text("keep", encoding="utf-8")
            _native_root(root)
            _make_dir_link(external, root / "operator" / "brain")

            plan = plan_init(str(root))
            self.assertFalse(plan.safe_to_apply)
            with self.assertRaises(ValidationError):
                initialize(str(root))
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")
            self.assertFalse((external / "installation.json").exists())

    def test_runtime_parent_symlink_or_junction_blocks_initialization(self):
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as outside:
            root = Path(temp)
            external = Path(outside)
            sentinel = external / "sentinel.txt"
            sentinel.write_text("keep", encoding="utf-8")
            _native_root(root)
            _make_dir_link(external, root / "runtime")

            plan = plan_init(str(root))
            self.assertFalse(plan.safe_to_apply)
            with self.assertRaises(ValidationError):
                initialize(str(root))
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")
            self.assertFalse((external / "ai-verse-brain").exists())

    def test_runtime_brain_symlink_or_junction_blocks_initialization(self):
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as outside:
            root = Path(temp)
            external = Path(outside)
            sentinel = external / "sentinel.txt"
            sentinel.write_text("keep", encoding="utf-8")
            _native_root(root)
            (root / "runtime").mkdir()
            _make_dir_link(external, root / "runtime" / "ai-verse-brain")

            plan = plan_init(str(root))
            self.assertFalse(plan.safe_to_apply)
            with self.assertRaises(ValidationError):
                initialize(str(root))
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")

    def test_runtime_lock_rechecks_nested_lock_parent_before_mutation(self):
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as outside:
            root = Path(temp)
            external = Path(outside)
            sentinel = external / "sentinel.txt"
            sentinel.write_text("keep", encoding="utf-8")
            _native_root(root)
            initialize(str(root))
            runtime = root / "runtime" / "ai-verse-brain"
            _make_dir_link(external, runtime / "locks")

            lock = RuntimeKeyLock(runtime, namespace="goal")
            with self.assertRaises(ValidationError):
                with lock.acquire("operator|goal"):
                    self.fail("unsafe runtime lock unexpectedly acquired")
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")
            self.assertFalse((external / "goal").exists())

    @unittest.skipIf(os.name == "nt", "ordinary file symlink creation is not reliably available on Windows runners")
    def test_native_installation_marker_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as outside:
            root = Path(temp)
            external = Path(outside)
            _native_root(root)
            initialize(str(root))
            marker = root / "operator" / "brain" / "installation.json"
            external_marker = external / "installation.json"
            external_marker.write_text(marker.read_text(encoding="utf-8"), encoding="utf-8")
            marker.unlink()
            os.symlink(str(external_marker), str(marker))

            with self.assertRaises(ValidationError):
                read_installation_marker(str(root))
            plan = plan_init(str(root))
            self.assertFalse(plan.safe_to_apply)
            self.assertTrue(external_marker.is_file())

    def test_adoption_refuses_redirected_operator_destination_without_retiring_source(self):
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as outside:
            root = Path(temp)
            external = Path(outside)
            sentinel = external / "sentinel.txt"
            sentinel.write_text("keep", encoding="utf-8")

            initialize(str(root))
            source_marker = root / ".ai-verse-brain" / "installation.json"
            self.assertTrue(source_marker.is_file())
            _native_root(root)
            _make_dir_link(external, root / "operator" / "brain")

            plan = plan_standalone_adoption(str(root))
            self.assertTrue(plan.needed)
            self.assertFalse(plan.safe_to_apply)
            with self.assertRaises(ValidationError):
                apply_standalone_adoption(str(root))
            self.assertTrue(source_marker.is_file())
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")
            self.assertFalse((external / "installation.json").exists())

    def test_adoption_refuses_redirected_transaction_parent(self):
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as outside:
            root = Path(temp)
            external = Path(outside)
            sentinel = external / "sentinel.txt"
            sentinel.write_text("keep", encoding="utf-8")

            initialize(str(root))
            source_marker = root / ".ai-verse-brain" / "installation.json"
            _native_root(root)
            (root / ".aiverse").mkdir()
            _make_dir_link(external, root / ".aiverse" / "brain-adoption")

            plan = plan_standalone_adoption(str(root))
            self.assertTrue(plan.needed)
            self.assertFalse(plan.safe_to_apply)
            with self.assertRaises(ValidationError):
                apply_standalone_adoption(str(root))
            self.assertTrue(source_marker.is_file())
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")
            self.assertFalse((external / "transaction.json").exists())


if __name__ == "__main__":
    unittest.main()
