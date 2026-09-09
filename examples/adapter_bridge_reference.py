#!/usr/bin/env python3
"""Minimal AI-Verse Brain bridge example.

This intentionally performs no external side effects. Replace the read/reason
implementations in a host-specific wrapper rather than giving the model direct
Brain write access.
"""

import json
import sys

PROTOCOL = "ai-verse-brain-bridge/1.0"
OPERATIONS = [
    "reason",
    "read_context",
    "retrieve_history",
    "list_capabilities",
    "list_connections",
]


def respond(request, result=None, error=None):
    payload = {
        "protocol": PROTOCOL,
        "request_id": request.get("request_id"),
        "ok": error is None,
    }
    if error is None:
        payload["result"] = result
    else:
        payload["error"] = {"code": "REFERENCE_ERROR", "message": error}
    print(json.dumps(payload, ensure_ascii=False))


def main():
    request = json.loads(sys.stdin.read())
    if request.get("protocol") != PROTOCOL:
        respond(request, error="protocol mismatch")
        return 2
    operation = request.get("operation")
    payload = request.get("payload") or {}

    if operation == "describe":
        respond(request, {
            "adapter_id": "reference-bridge",
            "protocol_version": "1.0",
            "operations": OPERATIONS,
            "idempotency_supported": False,
            "metadata": {"example": True, "side_effects": False},
        })
        return 0
    if operation == "reason":
        # A real wrapper would call its model/runtime and return proposal-shaped
        # data. Returning an empty list is a safe no-op reference behavior.
        respond(request, [])
        return 0
    if operation == "read_context":
        respond(request, {"scope": payload.get("scope"), "reference_adapter": True})
        return 0
    if operation in {"retrieve_history", "list_capabilities", "list_connections"}:
        respond(request, [])
        return 0

    respond(request, error="operation is not implemented by the reference bridge")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
