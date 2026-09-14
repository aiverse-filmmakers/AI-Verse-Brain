from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from aiverse_brain.local_host import ReadOnlyContextHost
from aiverse_brain.models import Scope


class CurrentContextUtf8Tests(unittest.TestCase):
    def test_os_context_resolver_is_always_decoded_as_utf8(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            resolver = root / "scripts" / "current-context.mjs"
            resolver.parent.mkdir(parents=True)
            resolver.write_text("// fixture\n", encoding="utf-8")

            host = ReadOnlyContextHost.__new__(ReadOnlyContextHost)
            host.root = root
            host.context_file = None
            host.max_bytes = 262144

            payload = {
                "scope": "workspace:alpha",
                "direction_owner": "brain",
                "current_context": "Direcție: continuă",
                "source": "fixture",
            }
            completed = subprocess.CompletedProcess(
                args=["node"], returncode=0, stdout=json.dumps(payload, ensure_ascii=False), stderr=""
            )

            with patch("aiverse_brain.local_host.shutil.which", return_value="node"), patch(
                "aiverse_brain.local_host.subprocess.run", return_value=completed
            ) as run:
                result = host._read_ai_verse_os_context(Scope("workspace:alpha"))

            self.assertEqual(result["current_context"], "Direcție: continuă")
            self.assertEqual(run.call_args.kwargs["encoding"], "utf-8")
            self.assertTrue(run.call_args.kwargs["text"])
            self.assertFalse(run.call_args.kwargs["check"])


if __name__ == "__main__":
    unittest.main()
