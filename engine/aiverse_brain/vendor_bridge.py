from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .bridge import BRIDGE_PROTOCOL, BRIDGE_VERSION

SUPPORTED_VENDORS = {"claude", "codex", "hermes"}


class VendorBridgeError(RuntimeError):
    pass


@dataclass(frozen=True)
class VendorOptions:
    vendor: str
    binary: Optional[str] = None
    model: Optional[str] = None
    provider: Optional[str] = None
    timeout_seconds: float = 120.0

    def validate(self) -> None:
        if self.vendor not in SUPPORTED_VENDORS:
            raise VendorBridgeError(f"unsupported vendor: {self.vendor!r}")
        if not isinstance(self.timeout_seconds, (int, float)) or isinstance(self.timeout_seconds, bool):
            raise VendorBridgeError("timeout_seconds must be numeric")
        if not 1 <= float(self.timeout_seconds) <= 600:
            raise VendorBridgeError("timeout_seconds must be between 1 and 600")
        for name, value in (("binary", self.binary), ("model", self.model), ("provider", self.provider)):
            if value is not None and (not isinstance(value, str) or not value.strip() or "\x00" in value):
                raise VendorBridgeError(f"{name} must be a non-empty NUL-free string")
        if self.provider is not None and self.vendor != "hermes":
            raise VendorBridgeError("--provider is supported only for Hermes")


def _binary(options: VendorOptions) -> str:
    return options.binary or options.vendor


def build_vendor_command(options: VendorOptions) -> List[str]:
    options.validate()
    binary = _binary(options)
    if options.vendor == "claude":
        command = [
            binary,
            "-p",
            "--output-format",
            "stream-json",
            "--verbose",
            "--permission-mode",
            "plan",
            "--no-session-persistence",
        ]
        if options.model:
            command.extend(["--model", options.model])
        return command
    if options.vendor == "codex":
        command = [
            binary,
            "exec",
            "--ephemeral",
            "--ignore-user-config",
            "--ignore-rules",
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
        ]
        if options.model:
            command.extend(["--model", options.model])
        command.append("-")
        return command

    command = [
        binary,
        "chat",
        "--oneshot",
        "--quiet",
        "--safe-mode",
        "--toolsets",
        "safe",
        "--query-file",
        "-",
        "--max-turns",
        "1",
        "--source",
        "tool",
    ]
    if options.provider:
        command.extend(["--provider", options.provider])
    if options.model:
        command.extend(["--model", options.model])
    return command


def build_reasoning_prompt(payload: Dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        raise VendorBridgeError("reason payload must be an object")
    request = payload.get("request")
    context = payload.get("context")
    if not isinstance(request, dict) or not isinstance(context, dict):
        raise VendorBridgeError("reason payload requires request and context objects")
    output_contract = request.get("output_contract") or {}
    proposal_kinds = output_contract.get("proposal_kinds") or []
    if not isinstance(proposal_kinds, list) or any(not isinstance(item, str) for item in proposal_kinds):
        raise VendorBridgeError("request output_contract.proposal_kinds must be an array of strings")
    allowed = ", ".join(proposal_kinds) if proposal_kinds else "(none)"
    envelope = json.dumps(
        {"request": request, "context": context},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return (
        "You are a reasoning adapter for AI-Verse Brain. You are NOT the authority or executor.\n"
        "Analyze only the supplied request/context and return proposal-shaped data for deterministic validation.\n"
        "Do not change user goals, permissions, privacy rules, risk tolerance, or success definitions.\n"
        "Do not perform or request external side effects. Read-only inspection is acceptable only where the CLI sandbox allows it.\n"
        f"Allowed proposal_kind values for this request: {allowed}.\n"
        "Return ONLY valid JSON in this exact outer shape: "
        '{"proposals":[{"proposal_kind":"...","payload":{},"confidence":0.0,"rationale":"..."}]}.\n'
        "Each proposal may contain only proposal_kind, payload, confidence, rationale. "
        "confidence must be a number from 0 to 1. No markdown fences or prose outside JSON.\n"
        "INPUT_JSON:\n" + envelope
    )


def _loads_strict(text: str) -> Any:
    def reject_duplicates(pairs: List[Tuple[str, Any]]) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise VendorBridgeError(f"duplicate JSON key in model output: {key}")
            result[key] = value
        return result

    return json.loads(text, object_pairs_hook=reject_duplicates)


def parse_model_json(text: str) -> Any:
    if not isinstance(text, str) or not text.strip():
        raise VendorBridgeError("vendor returned empty model output")
    candidate = text.strip()
    if candidate.startswith("```") and candidate.endswith("```"):
        lines = candidate.splitlines()
        if len(lines) >= 3:
            candidate = "\n".join(lines[1:-1]).strip()
    try:
        value = _loads_strict(candidate)
    except Exception:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start < 0 or end <= start:
            raise VendorBridgeError("vendor output does not contain a JSON object")
        value = _loads_strict(candidate[start : end + 1])
    if not isinstance(value, (dict, list)):
        raise VendorBridgeError("vendor model output must decode to an object or array")
    return value


def _claude_text(stdout: str) -> str:
    final_result = ""
    assistant_text: List[str] = []
    for raw in stdout.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "result" and isinstance(event.get("result"), str) and event["result"].strip():
            final_result = event["result"].strip()
        if event.get("type") == "assistant":
            message = event.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
                            assistant_text.append(block["text"])
    if final_result:
        return final_result
    if assistant_text:
        return assistant_text[-1]
    raise VendorBridgeError("Claude produced no usable assistant text")


def extract_vendor_result(vendor: str, stdout: str) -> Any:
    if vendor == "claude":
        return parse_model_json(_claude_text(stdout))
    return parse_model_json(stdout)


def invoke_vendor(options: VendorOptions, payload: Dict[str, Any]) -> Any:
    command = build_vendor_command(options)
    binary = command[0]
    if shutil.which(binary) is None and not ("/" in binary or "\\" in binary):
        raise VendorBridgeError(f"{options.vendor} CLI not found on PATH: {binary}")
    prompt = build_reasoning_prompt(payload)
    try:
        completed = subprocess.run(
            command,
            input=prompt,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            timeout=float(options.timeout_seconds),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise VendorBridgeError(
            f"{options.vendor} reasoning call exceeded {options.timeout_seconds}s"
        ) from exc
    except OSError as exc:
        raise VendorBridgeError(f"cannot start {options.vendor} CLI: {exc}") from exc

    if completed.returncode != 0:
        detail = (completed.stderr or "").strip()
        if len(detail) > 2000:
            detail = detail[-2000:]
        suffix = f": {detail}" if detail else ""
        raise VendorBridgeError(f"{options.vendor} CLI exited with {completed.returncode}{suffix}")
    return extract_vendor_result(options.vendor, completed.stdout or "")


def _response(request_id: Any, *, ok: bool, result: Any = None, error: Optional[str] = None) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "protocol": BRIDGE_PROTOCOL,
        "request_id": request_id,
        "ok": ok,
    }
    if ok:
        data["result"] = result
    else:
        data["error"] = {"code": "vendor_bridge_error", "message": error or "vendor bridge error"}
    return data


def handle_envelope(envelope: Any, options: VendorOptions) -> Dict[str, Any]:
    if not isinstance(envelope, dict):
        return _response(None, ok=False, error="bridge request must be an object")
    request_id = envelope.get("request_id")
    try:
        options.validate()
        if envelope.get("protocol") != BRIDGE_PROTOCOL:
            raise VendorBridgeError("bridge protocol mismatch")
        operation = envelope.get("operation")
        payload = envelope.get("payload") or {}
        if operation == "describe":
            binary = _binary(options)
            available = shutil.which(binary) is not None or "/" in binary or "\\" in binary
            if not available:
                raise VendorBridgeError(f"{options.vendor} CLI not found on PATH: {binary}")
            return _response(
                request_id,
                ok=True,
                result={
                    "adapter_id": f"ai-verse-brain-{options.vendor}-reasoner",
                    "protocol_version": BRIDGE_VERSION,
                    "operations": ["reason"],
                    "idempotency_supported": False,
                    "metadata": {
                        "vendor": options.vendor,
                        "mode": "reasoner-only",
                        "mutation_authority": False,
                    },
                },
            )
        if operation == "reason":
            return _response(request_id, ok=True, result=invoke_vendor(options, payload))
        raise VendorBridgeError(f"unsupported vendor bridge operation: {operation!r}")
    except Exception as exc:
        return _response(request_id, ok=False, error=str(exc))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai-verse-brain-vendor-bridge")
    parser.add_argument("--vendor", choices=sorted(SUPPORTED_VENDORS), required=True)
    parser.add_argument("--binary")
    parser.add_argument("--model")
    parser.add_argument("--provider")
    parser.add_argument("--timeout", type=float, default=120.0)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    options = VendorOptions(
        vendor=args.vendor,
        binary=args.binary,
        model=args.model,
        provider=args.provider,
        timeout_seconds=args.timeout,
    )
    try:
        raw = sys.stdin.read()
        envelope = _loads_strict(raw)
        response = handle_envelope(envelope, options)
    except Exception as exc:
        response = _response(None, ok=False, error=str(exc))
    sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()
    return 0 if response.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
