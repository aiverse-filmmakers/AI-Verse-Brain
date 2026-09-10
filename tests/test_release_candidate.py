import json
import sys
import tempfile
import unittest
from pathlib import Path

from aiverse_brain.cadence_hooks import render_cadence_hooks
from aiverse_brain.installation import initialize
from aiverse_brain.local_host import ReadOnlyContextHost
from aiverse_brain.migration import apply_migration, plan_migration
from aiverse_brain.vendor import vendor_bridge_config
from aiverse_brain.vendor_bridge import (
    VendorBridgeError,
    VendorOptions,
    build_reasoning_prompt,
    build_vendor_command,
    extract_vendor_result,
    handle_envelope,
    parse_model_json,
)


class VendorReasonerTests(unittest.TestCase):
    def test_claude_wrapper_is_noninteractive_plan_mode(self):
        command = build_vendor_command(VendorOptions("claude", binary="claude-test", model="model-x"))
        self.assertEqual(command[0], "claude-test")
        self.assertIn("-p", command)
        self.assertIn("stream-json", command)
        self.assertIn("--permission-mode", command)
        self.assertIn("plan", command)
        self.assertIn("--no-session-persistence", command)
        self.assertNotIn("--dangerously-skip-permissions", command)

    def test_codex_wrapper_is_ephemeral_read_only(self):
        command = build_vendor_command(VendorOptions("codex", binary="codex-test"))
        self.assertEqual(command[:2], ["codex-test", "exec"])
        self.assertIn("--ephemeral", command)
        self.assertIn("--ignore-user-config", command)
        self.assertIn("--ignore-rules", command)
        self.assertIn("read-only", command)
        self.assertEqual(command[-1], "-")
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", command)

    def test_hermes_wrapper_is_oneshot_safe_toolset(self):
        command = build_vendor_command(VendorOptions("hermes", binary="hermes-test", provider="openrouter"))
        self.assertEqual(command[:2], ["hermes-test", "chat"])
        self.assertIn("--oneshot", command)
        self.assertIn("--safe-mode", command)
        toolset_index = command.index("--toolsets")
        self.assertEqual(command[toolset_index + 1], "safe")
        self.assertIn("--query-file", command)
        self.assertIn("-", command)
        self.assertIn("--max-turns", command)

    def test_provider_is_hermes_only(self):
        with self.assertRaises(VendorBridgeError):
            build_vendor_command(VendorOptions("claude", provider="x"))

    def test_reasoning_prompt_preserves_authority_boundary(self):
        prompt = build_reasoning_prompt({
            "request": {"output_contract": {"proposal_kinds": ["gap"]}},
            "context": {"current": "example"},
        })
        self.assertIn("NOT the authority or executor", prompt)
        self.assertIn("Do not change user goals, permissions", prompt)
        self.assertIn("Do not perform or request external side effects", prompt)
        self.assertIn('"proposals"', prompt)

    def test_duplicate_model_json_keys_are_rejected(self):
        with self.assertRaises(VendorBridgeError):
            parse_model_json('{"proposals":[],"proposals":[]}')

    def test_claude_stream_falls_back_to_assistant_text(self):
        stdout = "\n".join([
            json.dumps({
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": '{"proposals":[]}'}]},
            }),
            json.dumps({"type": "result", "result": ""}),
        ])
        self.assertEqual(extract_vendor_result("claude", stdout), {"proposals": []})

    def test_vendor_describe_is_reasoner_only(self):
        response = handle_envelope(
            {"protocol": "ai-verse-brain-bridge/1.0", "request_id": "r1", "operation": "describe", "payload": {}},
            VendorOptions("claude", binary=sys.executable),
        )
        self.assertTrue(response["ok"])
        self.assertEqual(response["result"]["operations"], ["reason"])
        self.assertFalse(response["result"]["metadata"]["mutation_authority"])

    def test_builtin_vendor_config_uses_hardened_bridge(self):
        config = vendor_bridge_config("claude", binary=sys.executable, cwd=str(Path.cwd()))
        self.assertEqual(config.command[0], sys.executable)
        self.assertIn("aiverse_brain.vendor_bridge", config.command)
        self.assertEqual(config.model_id, "claude:cli")
        config.validate()


class ReleaseHostCadenceMigrationTests(unittest.TestCase):
    def test_read_only_context_host_reads_current_without_write_authority(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            current = root / "CURRENT.md"
            current.write_text("current state", encoding="utf-8")
            host = ReadOnlyContextHost(str(root))
            result = host.read_context("operator")
            self.assertEqual(result["current_context"], "current state")
            self.assertTrue(result["read_only"])
            self.assertEqual(list(host.retrieve_history("x", "operator")), [])
            with self.assertRaises(Exception):
                host.request_action({})

    def test_cadence_hooks_do_not_claim_scheduler_ownership(self):
        hooks = render_cadence_hooks("/tmp/brain", vendor="claude", proactivity=2, read_only_context=True)
        self.assertGreaterEqual(len(hooks), 4)
        for hook in hooks:
            self.assertFalse(hook["scheduler_owned_by_brain"])
            self.assertIn("run-tick", hook["argv"])
            self.assertIn("--vendor", hook["argv"])
            self.assertIn("--read-only-context", hook["argv"])

    def test_package_metadata_migration_is_explicit_and_safe(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            initialize(str(root))
            marker = root / ".ai-verse-brain" / "installation.json"
            data = json.loads(marker.read_text(encoding="utf-8"))
            data["package_version"] = "0.1.0a7"
            marker.write_text(json.dumps(data), encoding="utf-8")
            plan = plan_migration(str(root))
            self.assertTrue(plan.safe_to_apply)
            self.assertTrue(plan.needed)
            apply_migration(str(root))
            updated = json.loads(marker.read_text(encoding="utf-8"))
            self.assertEqual(updated["package_version"], "0.1.0b1")

    def test_unknown_older_state_schema_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            initialize(str(root))
            marker = root / ".ai-verse-brain" / "installation.json"
            data = json.loads(marker.read_text(encoding="utf-8"))
            data["state_schema_version"] = "0.9"
            marker.write_text(json.dumps(data), encoding="utf-8")
            plan = plan_migration(str(root))
            self.assertFalse(plan.safe_to_apply)
            self.assertTrue(plan.blockers)
            with self.assertRaises(Exception):
                apply_migration(str(root))


if __name__ == "__main__":
    unittest.main()
