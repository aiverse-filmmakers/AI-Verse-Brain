import json
import sys
import tempfile
import unittest
from pathlib import Path

from aiverse_brain.bridge import BridgeProcessError
from aiverse_brain.cadence_hooks import render_cadence_hooks
from aiverse_brain.cli import build_parser
from aiverse_brain.errors import ValidationError
from aiverse_brain.host_selection import (
    REQUIRED_HOST_READ_OPERATIONS,
    select_host,
    validate_host_selection_options,
)


class HostSelectionTests(unittest.TestCase):
    def _adapter_config(self, root: Path, operations=None) -> Path:
        ops = list(operations or REQUIRED_HOST_READ_OPERATIONS)
        script = root / "fixture_host.py"
        script.write_text(
            "import json, sys\n"
            f"OPERATIONS = {ops!r}\n"
            "request = json.loads(sys.stdin.read())\n"
            "operation = request['operation']\n"
            "if operation == 'describe':\n"
            "    result = {\n"
            "        'adapter_id': 'fixture-host',\n"
            "        'protocol_version': '1.0',\n"
            "        'operations': OPERATIONS,\n"
            "        'idempotency_supported': True,\n"
            "        'metadata': {'fixture': True},\n"
            "    }\n"
            "elif operation == 'read_context':\n"
            "    result = {'scope': request['payload']['scope'], 'current_context': 'live'}\n"
            "elif operation == 'retrieve_history':\n"
            "    result = [{'source': 'fixture-history'}]\n"
            "elif operation == 'list_capabilities':\n"
            "    result = [{'id': 'fixture-capability'}]\n"
            "elif operation == 'list_connections':\n"
            "    result = [{'id': 'fixture-connection'}]\n"
            "else:\n"
            "    result = None\n"
            "response = {\n"
            "    'protocol': 'ai-verse-brain-bridge/1.0',\n"
            "    'request_id': request['request_id'],\n"
            "    'ok': True,\n"
            "    'result': result,\n"
            "}\n"
            "sys.stdout.write(json.dumps(response))\n",
            encoding="utf-8",
        )
        config = root / "host.json"
        config.write_text(
            json.dumps({
                "schema_version": "1.0",
                "name": "fixture-host-config",
                "transport": "json-subprocess",
                "command": [sys.executable, str(script)],
            }),
            encoding="utf-8",
        )
        return config

    def test_real_bridge_host_is_live_selected_and_exposes_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = self._adapter_config(root)
            selection = select_host(str(root), host_adapter_config=str(config))
            self.assertTrue(selection.real_host)
            self.assertEqual(selection.mode, "bridge-host")
            self.assertEqual(selection.adapter_id, "fixture-host")
            self.assertEqual(selection.config_name, "fixture-host-config")
            self.assertEqual(set(REQUIRED_HOST_READ_OPERATIONS), set(selection.operations))
            self.assertEqual(selection.host.read_context("operator")["current_context"], "live")
            self.assertEqual(list(selection.host.retrieve_history("reflection", "operator"))[0]["source"], "fixture-history")
            self.assertEqual(list(selection.host.list_capabilities("operator"))[0]["id"], "fixture-capability")
            self.assertEqual(list(selection.host.list_connections("operator"))[0]["id"], "fixture-connection")

    def test_incomplete_real_host_is_rejected_before_runtime(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = self._adapter_config(root, operations=["read_context", "retrieve_history", "list_capabilities"])
            with self.assertRaisesRegex(ValidationError, "list_connections"):
                select_host(str(root), host_adapter_config=str(config))

    def test_unavailable_requested_host_never_falls_back(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / "missing-host.json"
            config.write_text(
                json.dumps({
                    "schema_version": "1.0",
                    "name": "missing-host",
                    "transport": "json-subprocess",
                    "command": [str(root / "definitely-not-an-executable")],
                }),
                encoding="utf-8",
            )
            with self.assertRaises(BridgeProcessError):
                select_host(str(root), host_adapter_config=str(config))

    def test_read_only_context_requires_explicit_selection(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            current = root / "CURRENT.md"
            current.write_text("explicit read only", encoding="utf-8")
            selection = select_host(str(root), read_only_context=True, context_file=str(current))
            self.assertFalse(selection.real_host)
            self.assertEqual(selection.mode, "read-only-context")
            self.assertEqual(selection.host.read_context("operator")["current_context"], "explicit read only")

    def test_exactly_one_host_mode_is_required(self):
        with self.assertRaises(ValidationError):
            validate_host_selection_options(host_adapter_config=None, read_only_context=False)
        with self.assertRaises(ValidationError):
            validate_host_selection_options(host_adapter_config="host.json", read_only_context=True)

    def test_context_file_cannot_override_real_host(self):
        with self.assertRaises(ValidationError):
            validate_host_selection_options(
                host_adapter_config="host.json",
                read_only_context=False,
                context_file="CURRENT.md",
            )

    def test_run_tick_parser_has_no_implicit_host_default(self):
        parser = build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["run-tick", ".", "--vendor", "claude"])
        parsed = parser.parse_args(["run-tick", ".", "--vendor", "claude", "--read-only-context"])
        self.assertTrue(parsed.read_only_context)
        self.assertIsNone(parsed.host_adapter)

    def test_cadence_hooks_preserve_explicit_host_choice(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            hooks = render_cadence_hooks(str(root), vendor="claude", proactivity=2, read_only_context=True)
            self.assertGreaterEqual(len(hooks), 1)
            for hook in hooks:
                self.assertEqual(hook["host_mode"], "read-only-context")
                self.assertIn("--read-only-context", hook["argv"])

            config = self._adapter_config(root)
            bridge_hooks = render_cadence_hooks(
                str(root),
                vendor="codex",
                proactivity=2,
                host_adapter_config=str(config),
            )
            expected_path = str(config.resolve())
            for hook in bridge_hooks:
                self.assertEqual(hook["host_mode"], "bridge-host")
                index = hook["argv"].index("--host-adapter")
                self.assertEqual(hook["argv"][index + 1], expected_path)


if __name__ == "__main__":
    unittest.main()
