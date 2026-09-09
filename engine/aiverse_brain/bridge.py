from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from uuid import uuid4

from .errors import BrainError, ValidationError

BRIDGE_PROTOCOL = "ai-verse-brain-bridge/1.0"
BRIDGE_VERSION = "1.0"
_ALLOWED_TOP_LEVEL_RESPONSE = {"protocol", "request_id", "ok", "result", "error"}
_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_BASE_ENV_NAMES = {
    "PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "HOME", "USERPROFILE",
    "TMP", "TEMP", "TMPDIR", "LANG", "LC_ALL", "VIRTUAL_ENV",
}


class BridgeError(BrainError):
    pass


class BridgeConfigError(BridgeError):
    pass


class BridgeTimeout(BridgeError):
    pass


class BridgeProtocolError(BridgeError):
    pass


class BridgeProcessError(BridgeError):
    pass


class BridgeRemoteError(BridgeError):
    pass


@dataclass(frozen=True)
class BridgeConfig:
    name: str
    command: Tuple[str, ...]
    timeout_seconds: float = 60.0
    max_input_bytes: int = 2 * 1024 * 1024
    max_output_bytes: int = 2 * 1024 * 1024
    max_stderr_bytes: int = 64 * 1024
    env_names: Tuple[str, ...] = field(default_factory=tuple)
    model_id: Optional[str] = None
    cwd: Optional[str] = None

    def validate(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise BridgeConfigError("adapter name must be non-empty")
        if not isinstance(self.command, tuple) or not self.command:
            raise BridgeConfigError("adapter command must be a non-empty array")
        if len(self.command) > 64:
            raise BridgeConfigError("adapter command has too many arguments")
        for item in self.command:
            if not isinstance(item, str) or not item:
                raise BridgeConfigError("adapter command arguments must be non-empty strings")
            if "\x00" in item:
                raise BridgeConfigError("adapter command arguments may not contain NUL bytes")
        if not isinstance(self.timeout_seconds, (int, float)) or isinstance(self.timeout_seconds, bool):
            raise BridgeConfigError("timeout_seconds must be numeric")
        if not 0.1 <= float(self.timeout_seconds) <= 600:
            raise BridgeConfigError("timeout_seconds must be between 0.1 and 600")
        for name, value, minimum, maximum in (
            ("max_input_bytes", self.max_input_bytes, 1024, 16 * 1024 * 1024),
            ("max_output_bytes", self.max_output_bytes, 1024, 16 * 1024 * 1024),
            ("max_stderr_bytes", self.max_stderr_bytes, 1024, 1024 * 1024),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
                raise BridgeConfigError(f"{name} must be an integer between {minimum} and {maximum}")
        for env_name in self.env_names:
            if not isinstance(env_name, str) or not _ENV_NAME_RE.match(env_name):
                raise BridgeConfigError(f"invalid environment variable name: {env_name!r}")
        if self.model_id is not None and (not isinstance(self.model_id, str) or not self.model_id.strip()):
            raise BridgeConfigError("model_id must be a non-empty string when provided")
        if self.cwd is not None:
            if not isinstance(self.cwd, str) or not self.cwd.strip():
                raise BridgeConfigError("cwd must be a non-empty path when provided")
            cwd = Path(self.cwd).expanduser().resolve()
            if not cwd.is_dir():
                raise BridgeConfigError(f"adapter cwd does not exist or is not a directory: {cwd}")

    @classmethod
    def from_dict(cls, data: Dict[str, Any], *, base_dir: Optional[Path] = None) -> "BridgeConfig":
        if not isinstance(data, dict):
            raise BridgeConfigError("adapter config must be a JSON object")
        allowed = {
            "schema_version", "name", "transport", "command", "timeout_seconds",
            "max_input_bytes", "max_output_bytes", "max_stderr_bytes", "env_names",
            "model_id", "cwd",
        }
        extras = sorted(set(data) - allowed)
        if extras:
            raise BridgeConfigError("unknown adapter config fields: " + ", ".join(extras))
        if data.get("schema_version", "1.0") != "1.0":
            raise BridgeConfigError("unsupported adapter config schema_version")
        if data.get("transport", "json-subprocess") != "json-subprocess":
            raise BridgeConfigError("only json-subprocess transport is supported by this adapter")
        raw_command = data.get("command")
        if not isinstance(raw_command, list):
            raise BridgeConfigError("adapter command must be a JSON array, never a shell string")
        raw_env = data.get("env_names", [])
        if not isinstance(raw_env, list):
            raise BridgeConfigError("env_names must be an array of environment variable names")
        raw_cwd = data.get("cwd")
        if raw_cwd is not None and base_dir is not None:
            cwd_path = Path(str(raw_cwd)).expanduser()
            if not cwd_path.is_absolute():
                raw_cwd = str((base_dir / cwd_path).resolve())
        config = cls(
            name=str(data.get("name", "")),
            command=tuple(raw_command),
            timeout_seconds=data.get("timeout_seconds", 60.0),
            max_input_bytes=data.get("max_input_bytes", 2 * 1024 * 1024),
            max_output_bytes=data.get("max_output_bytes", 2 * 1024 * 1024),
            max_stderr_bytes=data.get("max_stderr_bytes", 64 * 1024),
            env_names=tuple(raw_env),
            model_id=data.get("model_id"),
            cwd=raw_cwd,
        )
        config.validate()
        return config

    @classmethod
    def load(cls, path: str) -> "BridgeConfig":
        config_path = Path(path).expanduser().resolve()
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise BridgeConfigError(f"cannot read adapter config {config_path}: {exc}") from exc
        return cls.from_dict(data, base_dir=config_path.parent)


@dataclass(frozen=True)
class BridgeDescription:
    adapter_id: str
    protocol_version: str
    operations: Tuple[str, ...]
    idempotency_supported: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_result(cls, result: Any) -> "BridgeDescription":
        if not isinstance(result, dict):
            raise BridgeProtocolError("describe result must be an object")
        adapter_id = result.get("adapter_id")
        protocol_version = result.get("protocol_version")
        operations = result.get("operations")
        if not isinstance(adapter_id, str) or not adapter_id.strip():
            raise BridgeProtocolError("describe.adapter_id must be non-empty")
        if protocol_version != BRIDGE_VERSION:
            raise BridgeProtocolError(
                f"bridge protocol version mismatch: adapter={protocol_version!r}, brain={BRIDGE_VERSION!r}"
            )
        if not isinstance(operations, list) or any(not isinstance(item, str) or not item for item in operations):
            raise BridgeProtocolError("describe.operations must be an array of non-empty strings")
        idempotency = result.get("idempotency_supported", False)
        if not isinstance(idempotency, bool):
            raise BridgeProtocolError("describe.idempotency_supported must be boolean")
        metadata = result.get("metadata", {})
        if not isinstance(metadata, dict):
            raise BridgeProtocolError("describe.metadata must be an object")
        return cls(adapter_id.strip(), protocol_version, tuple(sorted(set(operations))), idempotency, dict(metadata))


class _BoundedPipeReader(threading.Thread):
    def __init__(self, stream: Any, limit: int):
        super().__init__(daemon=True)
        self.stream = stream
        self.limit = limit
        self.data = bytearray()
        self.exceeded = threading.Event()
        self.error: Optional[BaseException] = None

    def run(self) -> None:
        try:
            while True:
                chunk = self.stream.read(4096)
                if not chunk:
                    break
                remaining = self.limit - len(self.data)
                if remaining <= 0:
                    self.exceeded.set()
                    break
                if len(chunk) > remaining:
                    self.data.extend(chunk[:remaining])
                    self.exceeded.set()
                    break
                self.data.extend(chunk)
        except BaseException as exc:  # pragma: no cover - defensive thread boundary
            self.error = exc
            self.exceeded.set()


class _PipeWriter(threading.Thread):
    def __init__(self, stream: Any, data: bytes):
        super().__init__(daemon=True)
        self.stream = stream
        self.data = data
        self.error: Optional[BaseException] = None

    def run(self) -> None:
        try:
            self.stream.write(self.data)
            self.stream.flush()
        except BrokenPipeError:
            pass
        except BaseException as exc:  # pragma: no cover - defensive thread boundary
            self.error = exc
        finally:
            try:
                self.stream.close()
            except Exception:
                pass


class JSONSubprocessBridge:
    """Bounded, shell-free JSON bridge to an explicitly configured adapter process."""

    def __init__(self, config: BridgeConfig):
        config.validate()
        self.config = config

    def _environment(self) -> Dict[str, str]:
        names = _BASE_ENV_NAMES | set(self.config.env_names)
        return {name: value for name, value in os.environ.items() if name in names}

    def _invoke_process(self, payload: bytes) -> Tuple[bytes, bytes, int]:
        if len(payload) > self.config.max_input_bytes:
            raise BridgeProtocolError(
                f"bridge request exceeds max_input_bytes ({len(payload)} > {self.config.max_input_bytes})"
            )
        try:
            process = subprocess.Popen(
                list(self.config.command),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.config.cwd,
                env=self._environment(),
                shell=False,
            )
        except OSError as exc:
            raise BridgeProcessError(f"cannot start adapter {self.config.name!r}: {exc}") from exc
        if process.stdin is None or process.stdout is None or process.stderr is None:
            process.kill()
            raise BridgeProcessError("adapter subprocess pipes were not created")

        stdout_reader = _BoundedPipeReader(process.stdout, self.config.max_output_bytes)
        stderr_reader = _BoundedPipeReader(process.stderr, self.config.max_stderr_bytes)
        writer = _PipeWriter(process.stdin, payload)
        stdout_reader.start()
        stderr_reader.start()
        writer.start()

        deadline = time.monotonic() + float(self.config.timeout_seconds)
        timed_out = False
        output_exceeded = False
        while process.poll() is None:
            if stdout_reader.exceeded.is_set() or stderr_reader.exceeded.is_set():
                output_exceeded = True
                process.kill()
                break
            if time.monotonic() >= deadline:
                timed_out = True
                process.kill()
                break
            time.sleep(0.01)
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:  # pragma: no cover - kill should be immediate
            process.kill()
            process.wait()
        writer.join(timeout=1)
        stdout_reader.join(timeout=1)
        stderr_reader.join(timeout=1)

        if timed_out:
            raise BridgeTimeout(
                f"adapter {self.config.name!r} exceeded timeout of {self.config.timeout_seconds}s"
            )
        if output_exceeded or stdout_reader.exceeded.is_set() or stderr_reader.exceeded.is_set():
            raise BridgeProtocolError("adapter output exceeded configured byte limit")
        if stdout_reader.error or stderr_reader.error:
            raise BridgeProcessError("failed while reading adapter output")
        if writer.error and process.returncode == 0:
            raise BridgeProcessError(f"failed while writing adapter input: {writer.error}")
        return bytes(stdout_reader.data), bytes(stderr_reader.data), int(process.returncode or 0)

    def call(self, operation: str, payload: Optional[Dict[str, Any]] = None) -> Any:
        if not isinstance(operation, str) or not operation.strip():
            raise BridgeProtocolError("bridge operation must be non-empty")
        if payload is None:
            payload = {}
        if not isinstance(payload, dict):
            raise BridgeProtocolError("bridge payload must be an object")
        request_id = str(uuid4())
        envelope = {
            "protocol": BRIDGE_PROTOCOL,
            "request_id": request_id,
            "operation": operation.strip(),
            "payload": payload,
        }
        raw_request = (json.dumps(envelope, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        stdout, stderr, returncode = self._invoke_process(raw_request)
        stderr_text = stderr.decode("utf-8", errors="replace").strip()
        if returncode != 0:
            suffix = f": {stderr_text}" if stderr_text else ""
            raise BridgeProcessError(f"adapter exited with status {returncode}{suffix}")
        try:
            response = json.loads(stdout.decode("utf-8"))
        except Exception as exc:
            raise BridgeProtocolError("adapter stdout is not one valid JSON response object") from exc
        if not isinstance(response, dict):
            raise BridgeProtocolError("adapter response must be an object")
        extras = sorted(set(response) - _ALLOWED_TOP_LEVEL_RESPONSE)
        if extras:
            raise BridgeProtocolError("adapter response contains unknown top-level fields: " + ", ".join(extras))
        if response.get("protocol") != BRIDGE_PROTOCOL:
            raise BridgeProtocolError("adapter response protocol mismatch")
        if response.get("request_id") != request_id:
            raise BridgeProtocolError("adapter response request_id mismatch")
        if not isinstance(response.get("ok"), bool):
            raise BridgeProtocolError("adapter response ok must be boolean")
        if response["ok"]:
            if "result" not in response:
                raise BridgeProtocolError("successful adapter response requires result")
            return response["result"]
        error = response.get("error")
        if isinstance(error, dict):
            message = str(error.get("message", "adapter returned an error"))
            code = error.get("code")
            if code:
                message = f"{code}: {message}"
        else:
            message = str(error or "adapter returned an error")
        raise BridgeRemoteError(message)

    def describe(self) -> BridgeDescription:
        return BridgeDescription.from_result(self.call("describe", {}))


class BridgeReasonerAdapter:
    def __init__(self, bridge: JSONSubprocessBridge):
        self.bridge = bridge
        self.model_id = bridge.config.model_id or bridge.config.name

    def reason(self, request: Dict[str, Any], context: Dict[str, Any]) -> Any:
        if not isinstance(request, dict) or not isinstance(context, dict):
            raise ValidationError("reason request/context must be objects")
        return self.bridge.call("reason", {"request": request, "context": context})


class BridgeHostAdapter:
    """HostAdapter implementation over the same bounded bridge protocol.

    This adapter delegates host operations only. Brain's deterministic policy still
    decides which action requests may reach request_action.
    """

    def __init__(self, bridge: JSONSubprocessBridge):
        self.bridge = bridge
        self._description: Optional[BridgeDescription] = None

    @property
    def description(self) -> BridgeDescription:
        if self._description is None:
            self._description = self.bridge.describe()
        return self._description

    @property
    def idempotency_supported(self) -> bool:
        return self.description.idempotency_supported

    def _require_operation(self, operation: str) -> None:
        if operation not in self.description.operations:
            raise BridgeProtocolError(f"adapter does not advertise required operation: {operation}")

    def _call(self, operation: str, payload: Dict[str, Any]) -> Any:
        self._require_operation(operation)
        return self.bridge.call(operation, payload)

    @staticmethod
    def _object(result: Any, operation: str) -> Dict[str, Any]:
        if not isinstance(result, dict):
            raise BridgeProtocolError(f"{operation} result must be an object")
        return dict(result)

    @staticmethod
    def _objects(result: Any, operation: str) -> List[Dict[str, Any]]:
        if not isinstance(result, list) or any(not isinstance(item, dict) for item in result):
            raise BridgeProtocolError(f"{operation} result must be an array of objects")
        return [dict(item) for item in result]

    def read_context(self, scope: str) -> Dict[str, Any]:
        return self._object(self._call("read_context", {"scope": scope}), "read_context")

    def retrieve_history(self, query: str, scope: str) -> Iterable[Dict[str, Any]]:
        return self._objects(self._call("retrieve_history", {"query": query, "scope": scope}), "retrieve_history")

    def list_capabilities(self, scope: str) -> Iterable[Dict[str, Any]]:
        return self._objects(self._call("list_capabilities", {"scope": scope}), "list_capabilities")

    def list_connections(self, scope: str) -> Iterable[Dict[str, Any]]:
        return self._objects(self._call("list_connections", {"scope": scope}), "list_connections")

    def request_action(self, request: Dict[str, Any]) -> Dict[str, Any]:
        return self._object(self._call("request_action", {"request": request}), "request_action")

    def request_evaluation(self, request: Dict[str, Any]) -> Dict[str, Any]:
        return self._object(self._call("request_evaluation", {"request": request}), "request_evaluation")

    def schedule_trigger(self, trigger: Dict[str, Any]) -> Dict[str, Any]:
        return self._object(self._call("schedule_trigger", {"trigger": trigger}), "schedule_trigger")

    def cancel_trigger(self, trigger_id: str) -> None:
        self._call("cancel_trigger", {"trigger_id": trigger_id})

    def notify_user(self, notification: Dict[str, Any]) -> None:
        self._call("notify_user", {"notification": notification})

    def write_route(self, classification: str, payload: Dict[str, Any], scope: str) -> Optional[str]:
        result = self._call(
            "write_route",
            {"classification": classification, "payload": payload, "scope": scope},
        )
        if result is None:
            return None
        if not isinstance(result, str):
            raise BridgeProtocolError("write_route result must be a string or null")
        return result


def adapter_doctor(config: BridgeConfig) -> Dict[str, Any]:
    bridge = JSONSubprocessBridge(config)
    description = bridge.describe()
    return {
        "ok": True,
        "name": config.name,
        "adapter_id": description.adapter_id,
        "protocol_version": description.protocol_version,
        "operations": list(description.operations),
        "idempotency_supported": description.idempotency_supported,
        "model_id": config.model_id or config.name,
        "transport": "json-subprocess",
        "credential_values_stored": False,
        "env_names": list(config.env_names),
        "metadata": dict(description.metadata),
    }
