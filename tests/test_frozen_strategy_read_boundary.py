import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiverse_brain.errors import ValidationError
from aiverse_brain.host_selection import select_host


class FrozenStrategyReadBoundaryTests(unittest.TestCase):
    def _compatible_os_root(self, root: Path, *, with_resolver: bool = True) -> Path:
        (root / "operator" / "context").mkdir(parents=True, exist_ok=True)
        (root / "workspaces").mkdir(parents=True, exist_ok=True)
        (root / "operator" / "context" / "CURRENT.md").write_text(
            "## Current priorities\n\n- FROZEN OS STRATEGY\n\n## Current state\n\n- operational fact\n",
            encoding="utf-8",
        )
        (root / "AI-VERSE.yaml").write_text(
            'schema_version: "2.0"\narchitecture: unified-workspace\n',
            encoding="utf-8",
        )
        if with_resolver:
            resolver = root / "scripts" / "current-context.mjs"
            resolver.parent.mkdir(parents=True, exist_ok=True)
            resolver.write_text("// fixture resolver; subprocess is mocked in unit tests\n", encoding="utf-8")
        return root

    def test_compatible_os_delegates_to_ownership_aware_resolver(self):
        with tempfile.TemporaryDirectory() as temp:
            root = self._compatible_os_root(Path(temp))
            resolved = {
                "schema_version": 1,
                "scope": "operator",
                "direction_owner": "brain",
                "strategy_status": "brain-canonical",
                "current_context": "Direction owner: brain\n\n## OS operational context\n\n## Current state\n\n- operational fact\n",
                "source": "operator/context/CURRENT.md",
                "direction_refs": ["brain:intent:goal-1"],
            }
            completed = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=json.dumps(resolved),
                stderr="",
            )

            with patch("aiverse_brain.local_host.shutil.which", return_value="/usr/bin/node"), patch(
                "aiverse_brain.local_host.subprocess.run", return_value=completed
            ) as run:
                selection = select_host(str(root), read_only_context=True)
                result = selection.host.read_context("operator")

            self.assertEqual(result["direction_owner"], "brain")
            self.assertEqual(result["context_resolver"], "ai-verse-os:scripts/current-context.mjs")
            self.assertNotIn("FROZEN OS STRATEGY", result["current_context"])
            self.assertIn("operational fact", result["current_context"])
            argv = run.call_args.args[0]
            self.assertEqual(
                Path(argv[1]).resolve(),
                (root / "scripts" / "current-context.mjs").resolve(),
            )
            self.assertEqual(argv[-2:], ["--scope", "operator"])

    def test_missing_os_resolver_fails_closed_instead_of_raw_read(self):
        with tempfile.TemporaryDirectory() as temp:
            root = self._compatible_os_root(Path(temp), with_resolver=False)
            selection = select_host(str(root), read_only_context=True)
            with self.assertRaisesRegex(ValidationError, "will not fall back to raw CURRENT.md"):
                selection.host.read_context("operator")

    def test_malformed_os_resolver_output_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = self._compatible_os_root(Path(temp))
            completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="not-json", stderr="")
            with patch("aiverse_brain.local_host.shutil.which", return_value="/usr/bin/node"), patch(
                "aiverse_brain.local_host.subprocess.run", return_value=completed
            ):
                selection = select_host(str(root), read_only_context=True)
                with self.assertRaisesRegex(ValidationError, "returned invalid JSON"):
                    selection.host.read_context("operator")

    def test_wrong_scope_from_os_resolver_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = self._compatible_os_root(Path(temp))
            completed = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=json.dumps({
                    "scope": "workspace:other",
                    "direction_owner": "brain",
                    "current_context": "filtered",
                    "source": None,
                }),
                stderr="",
            )
            with patch("aiverse_brain.local_host.shutil.which", return_value="/usr/bin/node"), patch(
                "aiverse_brain.local_host.subprocess.run", return_value=completed
            ):
                selection = select_host(str(root), read_only_context=True)
                with self.assertRaisesRegex(ValidationError, "wrong scope"):
                    selection.host.read_context("operator")

    def test_context_file_cannot_bypass_os_resolver(self):
        with tempfile.TemporaryDirectory() as temp:
            root = self._compatible_os_root(Path(temp))
            raw = root / "operator" / "context" / "CURRENT.md"
            with self.assertRaisesRegex(ValidationError, "cannot override"):
                select_host(
                    str(root),
                    read_only_context=True,
                    context_file=str(raw),
                )

    def test_standalone_explicit_context_file_still_works(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            current = root / "CURRENT.md"
            current.write_text("standalone explicit context", encoding="utf-8")
            selection = select_host(
                str(root),
                read_only_context=True,
                context_file=str(current),
            )
            self.assertEqual(
                selection.host.read_context("operator")["current_context"],
                "standalone explicit context",
            )


if __name__ == "__main__":
    unittest.main()
