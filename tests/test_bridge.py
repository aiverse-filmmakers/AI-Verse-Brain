import json
import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from aiverse_brain.action_boundary import ActionRequest, ApprovalGrant
from aiverse_brain.authority import AuthorityTier
from aiverse_brain.bridge import (
    BridgeConfig,
    BridgeConfigError,
    BridgeHostAdapter,
    BridgeProtocolError,
    BridgeReasonerAdapter,
    BridgeTimeout,
    JSONSubprocessBridge,
    adapter_doctor,
)
from aiverse_brain.errors import PermissionDenied
from aiverse_brain.installation import initialize
from aiverse_brain.models import Scope
from aiverse_brain.runtime import BrainRuntime


BRIDGE_SCRIPT = r'''
import json
import os
import sys

request = json.loads(sys.stdin.read())
operation = request.get("operation")
request_id = request.get("request_id")
protocol = request.get("protocol")
payload = request.get("payload") or {}

operations = [
    "reason", "read_context", "retrieve_history", "list_capabilities", "list_connections",
    "authorize_action", "request_action", "request_evaluation", "schedule_trigger", "cancel_trigger", "notify_user",
    "write_route", "echo_env"
]

if operation == "describe":
    result = {
        "adapter_id": "test-bridge",
        "protocol_version": "1.0",
        "operations": operations,
        "idempotency_supported": True,
        "metadata": {"kind": "synthetic"}
    }
elif operation == "reason":
    result = []
elif operation == "read_context":
    result = {"scope": payload.get("scope"), "current": "synthetic"}
elif operation == "retrieve_history":
    result = [{"ref": "history:1", "summary": "synthetic"}]
elif operation == "list_capabilities":
    result = [{"id": "cap:1"}]
elif operation == "list_connections":
    result = [{"id": "conn:1"}]
elif operation == "authorize_action":
    action = payload.get("request") or {}
    result = {
        "decision": "allow",
        "request_fingerprint": action.get("request_fingerprint"),
        "scope": action.get("scope"),
        "action_class": action.get("action_class"),
        "source": "test-bridge",
        "reason": "synthetic bridge permits action"
    }
elif operation == "request_action":
    action = payload.get("request") or {}
    result = {"status": "succeeded", "receipt_id": "bridge-receipt-1", "result": {"operation": action.get("operation")}}
elif operation == "request_evaluation":
    result = {"status": "recorded"}
elif operation == "schedule_trigger":
    result = {"trigger_id": "scheduled-1"}
elif operation == "cancel_trigger":
    result = None
elif operation == "notify_user":
    result = None
elif operation == "write_route":
    result = "host:write:1"
elif operation == "echo_env":
    result = {"value": os.environ.get(payload.get("name", ""))}
else:
    print(json.dumps({"protocol": protocol, "request_id": request_id, "ok": False, "error": {"code": "UNKNOWN", "message": "unknown operation"}}))
    raise SystemExit(0)

print(json.dumps({"protocol": protocol, "request_id": request_id, "ok": True, "result": result}))
'''


class BridgeTestCase(unittest.TestCase):
    def make_bridge(self, directory, script=BRIDGE_SCRIPT, **overrides):
        path = Path(directory) / "bridge.py"
        path.write_text(textwrap.dedent(script), encoding="utf-8")
        data = {
            "name": "test-adapter",
            "command": (sys.executable, str(path)),
            "timeout_seconds": 2.0,
            "max_input_bytes": 1024 * 1024,
            "max_output_bytes": 1024 * 1024,
            "max_stderr_bytes": 65536,
            "env_names": (),
            "model_id": "test-model",
        }
        data.update(overrides)
        return JSONSubprocessBridge(BridgeConfig(**data))


class BridgeConfigTests(BridgeTestCase):
    def test_shell_string_command_is_rejected(self):
        with self.assertRaises(BridgeConfigError):
            BridgeConfig.from_dict({
                "schema_version": "1.0",
                "name": "bad",
                "transport": "json-subprocess",
                "command": "python bridge.py && rm -rf something",
            })

    def test_unknown_config_fields_are_rejected(self):
        with self.assertRaises(BridgeConfigError):
            BridgeConfig.from_dict({
                "schema_version": "1.0",
                "name": "bad",
                "transport": "json-subprocess",
                "command": ["python", "bridge.py"],
                "api_key": "must-not-be-stored",
            })

    def test_common_credential_command_flags_are_rejected(self):
        with self.assertRaises(BridgeConfigError):
            BridgeConfig.from_dict({
                "schema_version": "1.0",
                "name": "bad-secret-arg",
                "transport": "json-subprocess",
                "command": ["provider-cli", "--api-key=plaintext-secret"],
            })

    def test_duplicate_env_names_are_rejected(self):
        with self.assertRaises(BridgeConfigError):
            BridgeConfig(
                name="bad-env",
                command=(sys.executable, "bridge.py"),
                env_names=("API_KEY", "API_KEY"),
            ).validate()

    def test_duplicate_json_config_keys_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "adapter.json"
            path.write_text(
                '{"name":"first","name":"second","transport":"json-subprocess","command":["python","x.py"]}',
                encoding="utf-8",
            )
            with self.assertRaises(BridgeConfigError):
                BridgeConfig.load(str(path))


class BridgeProtocolTests(BridgeTestCase):
    def test_handshake_and_host_operations(self):
        with tempfile.TemporaryDirectory() as temp:
            bridge = self.make_bridge(temp)
            description = bridge.describe()
            self.assertEqual(description.adapter_id, "test-bridge")
            self.assertTrue(description.idempotency_supported)
            host = BridgeHostAdapter(bridge)
            self.assertEqual(host.read_context("operator")["scope"], "operator")
            self.assertEqual(list(host.retrieve_history("x", "operator"))[0]["ref"], "history:1")
            self.assertEqual(list(host.list_capabilities("operator"))[0]["id"], "cap:1")
            permission = host.authorize_action({
                "request_fingerprint": "a" * 64,
                "scope": "operator",
                "action_class": "read_local",
            })
            self.assertEqual(permission["decision"], "allow")
            self.assertEqual(permission["request_fingerprint"], "a" * 64)
            self.assertEqual(host.write_route("memory", {"x": 1}, "operator"), "host:write:1")

    def test_reasoner_uses_same_untrusted_bridge_boundary(self):
        with tempfile.TemporaryDirectory() as temp:
            reasoner = BridgeReasonerAdapter(self.make_bridge(temp))
            self.assertEqual(reasoner.model_id, "test-model")
            self.assertEqual(reasoner.reason({"purpose": "orient"}, {"scope": "operator"}), [])

    def test_reasoner_requires_advertised_reason_operation(self):
        script = r'''
import json, sys
request = json.loads(sys.stdin.read())
result = {"adapter_id": "limited", "protocol_version": "1.0", "operations": ["read_context"], "idempotency_supported": False}
print(json.dumps({"protocol": request["protocol"], "request_id": request["request_id"], "ok": True, "result": result}))
'''
        with tempfile.TemporaryDirectory() as temp:
            reasoner = BridgeReasonerAdapter(self.make_bridge(temp, script=script))
            with self.assertRaises(BridgeProtocolError):
                reasoner.reason({}, {})

    def test_parent_environment_is_filtered_unless_name_is_explicitly_allowed(self):
        with tempfile.TemporaryDirectory() as temp:
            key = "AI_VERSE_BRAIN_TEST_SECRET"
            old = os.environ.get(key)
            os.environ[key] = "super-secret-value"
            try:
                bridge = self.make_bridge(temp)
                self.assertIsNone(bridge.call("echo_env", {"name": key})["value"])
                bridge_allowed = self.make_bridge(temp, env_names=(key,))
                self.assertEqual(bridge_allowed.call("echo_env", {"name": key})["value"], "super-secret-value")
            finally:
                if old is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = old

    def test_timeout_kills_adapter(self):
        script = r'''
import json, sys, time
request = json.loads(sys.stdin.read())
time.sleep(2)
print(json.dumps({"protocol": request["protocol"], "request_id": request["request_id"], "ok": True, "result": {}}))
'''
        with tempfile.TemporaryDirectory() as temp:
            bridge = self.make_bridge(temp, script=script, timeout_seconds=0.15)
            with self.assertRaises(BridgeTimeout):
                bridge.call("describe", {})

    def test_output_limit_is_enforced(self):
        script = r'''
import json, sys
json.loads(sys.stdin.read())
sys.stdout.write("x" * 100000)
sys.stdout.flush()
'''
        with tempfile.TemporaryDirectory() as temp:
            bridge = self.make_bridge(temp, script=script, max_output_bytes=1024)
            with self.assertRaises(BridgeProtocolError):
                bridge.call("describe", {})

    def test_mismatched_request_id_is_rejected(self):
        script = r'''
import json, sys
request = json.loads(sys.stdin.read())
print(json.dumps({"protocol": request["protocol"], "request_id": "wrong", "ok": True, "result": {}}))
'''
        with tempfile.TemporaryDirectory() as temp:
            bridge = self.make_bridge(temp, script=script)
            with self.assertRaises(BridgeProtocolError):
                bridge.call("describe", {})

    def test_duplicate_response_keys_are_rejected(self):
        script = r'''
import json, sys
request = json.loads(sys.stdin.read())
print('{"protocol":"%s","request_id":"%s","ok":true,"ok":false,"result":{}}' % (request["protocol"], request["request_id"]))
'''
        with tempfile.TemporaryDirectory() as temp:
            bridge = self.make_bridge(temp, script=script)
            with self.assertRaises(BridgeProtocolError):
                bridge.call("describe", {})

    def test_host_refuses_unadvertised_operation(self):
        script = r'''
import json, sys
request = json.loads(sys.stdin.read())
result = {"adapter_id": "limited", "protocol_version": "1.0", "operations": ["read_context"], "idempotency_supported": False}
print(json.dumps({"protocol": request["protocol"], "request_id": request["request_id"], "ok": True, "result": result}))
'''
        with tempfile.TemporaryDirectory() as temp:
            host = BridgeHostAdapter(self.make_bridge(temp, script=script))
            with self.assertRaises(BridgeProtocolError):
                host.request_action({"x": 1})
            with self.assertRaises(BridgeProtocolError):
                host.authorize_action({"request_fingerprint": "a" * 64, "scope": "operator", "action_class": "read_local"})

    def test_adapter_doctor_reports_no_stored_credential_values(self):
        with tempfile.TemporaryDirectory() as temp:
            bridge = self.make_bridge(temp, env_names=("SOME_PROVIDER_TOKEN",))
            report = adapter_doctor(bridge.config)
            self.assertTrue(report["ok"])
            self.assertFalse(report["credential_values_stored"])
            self.assertEqual(report["env_names"], ["SOME_PROVIDER_TOKEN"])


class BridgeActionBoundaryTests(BridgeTestCase):
    def test_bridge_host_still_requires_brain_action_approval(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "brain-root"
            root.mkdir()
            initialize(str(root))
            bridge_dir = Path(temp) / "bridge"
            bridge_dir.mkdir()
            bridge = self.make_bridge(str(bridge_dir))
            host = BridgeHostAdapter(bridge)
            runtime = BrainRuntime(str(root))
            request = ActionRequest(
                action_class="send_message",
                scope=Scope("operator"),
                operation="send",
                parameters={"to": "example", "text": "hello"},
                idempotency_key="bridge-send-1",
                in_scope=True,
                within_budget=True,
                reversible=False,
            )
            with self.assertRaises(PermissionDenied):
                runtime.execute_action(
                    request,
                    host=host,
                    host_idempotency_supported=host.idempotency_supported,
                )
            approval = ApprovalGrant.for_request(
                request,
                granted_by="user",
                authority=AuthorityTier.EXPLICIT_USER,
            )
            outcome = runtime.execute_action(
                request,
                host=host,
                approval=approval,
                host_idempotency_supported=host.idempotency_supported,
            )
            self.assertEqual(outcome.status, "succeeded")
            self.assertEqual(outcome.receipt_id, "bridge-receipt-1")


if __name__ == "__main__":
    unittest.main()
