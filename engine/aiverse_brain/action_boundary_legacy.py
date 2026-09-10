from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Dict, Mapping, Optional
from uuid import uuid4

from .action_snapshot import freeze_json, thaw_json
from .authority import AuthorityTier
from .errors import DuplicateAction, PermissionDenied, UncertainActionOutcome, ValidationError
from .models import Scope, utc_now
from .policy import ACTION_CLASSES, BrainPolicy
from .runtime_lock import RuntimeKeyLock
from .storage import StorageLayout


READ_ONLY_ACTIONS = {"read_local", "read_connected"}
SIDE_EFFECT_ACTIONS = set(ACTION_CLASSES) - READ_ONLY_ACTIONS


class ActionDisposition(str, Enum):
    DENIED = "denied"
    APPROVAL_REQUIRED = "approval_required"
    AUTHORIZED = "authorized"
    DUPLICATE_COMPLETED = "duplicate_completed"
    UNCERTAIN_BLOCKED = "uncertain_blocked"


@dataclass(frozen=True)
class ActionRequest:
    action_class: str
    scope: Scope
    operation: str
    parameters: Mapping[str, Any]
    idempotency_key: str
    in_scope: bool = True
    within_budget: bool = True
    reversible: bool = False
    reason: str = ""
    request_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if self.action_class not in ACTION_CLASSES:
            raise ValidationError(f"unknown action class: {self.action_class}")
        if not self.operation:
            raise ValidationError("action operation is required")
        if not isinstance(self.parameters, Mapping):
            raise ValidationError("action parameters must be an object")
        if not self.idempotency_key:
            raise ValidationError("idempotency_key is required for every action request")
        object.__setattr__(self, "parameters", freeze_json(self.parameters))

    @property
    def is_side_effect(self) -> bool:
        return self.action_class in SIDE_EFFECT_ACTIONS

    def fingerprint(self) -> str:
        data = {
            "action_class": self.action_class,
            "scope": self.scope.value,
            "operation": self.operation,
            "parameters": thaw_json(self.parameters),
            "idempotency_key": self.idempotency_key,
            "in_scope": self.in_scope,
            "within_budget": self.within_budget,
            "reversible": self.reversible,
            "reason": self.reason,
        }
        raw = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "action_class": self.action_class,
            "scope": self.scope.value,
            "operation": self.operation,
            "parameters": thaw_json(self.parameters),
            "idempotency_key": self.idempotency_key,
            "in_scope": self.in_scope,
            "within_budget": self.within_budget,
            "reversible": self.reversible,
            "reason": self.reason,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class ApprovalGrant:
    request_id: str
    idempotency_key: str
    scope: str
    action_class: str
    granted_by: str
    request_fingerprint: str = ""
    authority: AuthorityTier = AuthorityTier.EXPLICIT_USER
    expires_at: Optional[str] = None

    @classmethod
    def for_request(
        cls,
        request: ActionRequest,
        *,
        granted_by: str,
        authority: AuthorityTier = AuthorityTier.EXPLICIT_USER,
        expires_at: Optional[str] = None,
    ) -> "ApprovalGrant":
        return cls(
            request_id=request.request_id,
            idempotency_key=request.idempotency_key,
            scope=request.scope.value,
            action_class=request.action_class,
            granted_by=granted_by,
            request_fingerprint=request.fingerprint(),
            authority=authority,
            expires_at=expires_at,
        )

    def assert_valid_for(self, request: ActionRequest) -> None:
        if self.authority != AuthorityTier.EXPLICIT_USER:
            raise PermissionDenied("action approval must come from explicit user authority")
        if self.request_id != request.request_id or self.idempotency_key != request.idempotency_key:
            raise PermissionDenied("approval does not match action request")
        if self.scope != request.scope.value or self.action_class != request.action_class:
            raise PermissionDenied("approval scope/action class does not match request")
        if not self.request_fingerprint or self.request_fingerprint != request.fingerprint():
            raise PermissionDenied("approval fingerprint does not match the exact action request")
        if not self.granted_by:
            raise PermissionDenied("approval grant must identify the granting user")
        if self.expires_at:
            text = self.expires_at[:-1] + "+00:00" if self.expires_at.endswith("Z") else self.expires_at
            try:
                expires = datetime.fromisoformat(text)
                if expires.tzinfo is None:
                    raise ValueError("timezone required")
                expires = expires.astimezone(timezone.utc)
            except ValueError as exc:
                raise PermissionDenied("action approval has an invalid expiry timestamp") from exc
            if expires <= datetime.now(timezone.utc):
                raise PermissionDenied("action approval has expired")


@dataclass(frozen=True)
class ActionAuthorization:
    disposition: ActionDisposition
    reason: str
    automatic_retry_allowed: bool = False

    @property
    def authorized(self) -> bool:
        return self.disposition == ActionDisposition.AUTHORIZED


@dataclass(frozen=True)
class ActionOutcome:
    status: str
    receipt_id: Optional[str]
    result: Dict[str, Any]
    duplicate: bool = False


class ActionGate:
    def __init__(self, policy: BrainPolicy):
        self.policy = policy

    def authorize(
        self,
        request: ActionRequest,
        *,
        approval: Optional[ApprovalGrant] = None,
        host_idempotency_supported: bool = False,
    ) -> ActionAuthorization:
        # A supplied grant is security-sensitive input. Validate it on every route,
        # even when policy would otherwise authorize, deny, or take an exception path.
        if approval is not None:
            approval.assert_valid_for(request)

        decision = self.policy.action_decision(request.action_class)
        if decision == "deny":
            return ActionAuthorization(ActionDisposition.DENIED, "action class denied by policy")

        if decision == "ask_every_time":
            if approval is None:
                return ActionAuthorization(ActionDisposition.APPROVAL_REQUIRED, "explicit approval required")
        elif decision == "allow_within_scope" and not request.in_scope:
            return ActionAuthorization(ActionDisposition.DENIED, "action is outside authorized scope")
        elif decision == "allow_within_budget" and not request.within_budget:
            return ActionAuthorization(ActionDisposition.DENIED, "action exceeds authorized budget")
        elif decision == "allow_if_reversible" and not request.reversible:
            return ActionAuthorization(ActionDisposition.DENIED, "action is not reversible")

        if request.is_side_effect and not host_idempotency_supported and approval is None:
            return ActionAuthorization(
                ActionDisposition.APPROVAL_REQUIRED,
                "autonomous side effect requires host idempotency support or explicit approval",
            )

        return ActionAuthorization(
            ActionDisposition.AUTHORIZED,
            "authorized by policy/approval",
            automatic_retry_allowed=(not request.is_side_effect or host_idempotency_supported),
        )


class ActionLedger:
    """Durable receipt references for side effects; disposable coordination receipts for reads."""

    def __init__(self, layout: StorageLayout):
        self.layout = layout
        self.lock = RuntimeKeyLock(layout.runtime_dir, namespace="actions", ttl_seconds=3600)

    def _directory(self, request: ActionRequest) -> Path:
        if request.is_side_effect:
            directory = self.layout.state_root(request.scope) / "action-receipts"
        else:
            directory = self.layout.runtime_dir / "read-action-receipts"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def _path(self, request: ActionRequest) -> Path:
        digest = hashlib.sha256(request.idempotency_key.encode("utf-8")).hexdigest()
        return self._directory(request) / f"{digest}.json"

    def read(self, request: ActionRequest) -> Optional[Dict[str, Any]]:
        path = self._path(request)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def write(self, request: ActionRequest, data: Dict[str, Any]) -> None:
        directory = self._directory(request)
        path = self._path(request)
        fd, temp_name = tempfile.mkstemp(prefix=".action.", suffix=".tmp", dir=str(directory))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)


class ActionExecutor:
    def __init__(self, root: Path, policy: BrainPolicy):
        self.layout = StorageLayout.detect(Path(root))
        self.gate = ActionGate(policy)
        self.ledger = ActionLedger(self.layout)

    @staticmethod
    def _minimal_response(response: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "status": response.get("status"),
            "receipt_id": response.get("receipt_id"),
            "effect_occurred": response.get("effect_occurred"),
        }

    @staticmethod
    def _outcome_from_record(record: Dict[str, Any], *, duplicate: bool) -> ActionOutcome:
        response = dict(record.get("response", {}))
        return ActionOutcome(
            status=str(response.get("status", record.get("ledger_status", "unknown"))),
            receipt_id=response.get("receipt_id"),
            result={},
            duplicate=duplicate,
        )

    @staticmethod
    def _assert_dispatch_binding(
        request: ActionRequest,
        *,
        expected_fingerprint: str,
        approval: Optional[ApprovalGrant],
    ) -> None:
        if request.fingerprint() != expected_fingerprint:
            raise PermissionDenied("action request changed after authorization")
        if approval is not None:
            approval.assert_valid_for(request)

    def execute(
        self,
        request: ActionRequest,
        host: Any,
        *,
        approval: Optional[ApprovalGrant] = None,
        host_idempotency_supported: bool = False,
    ) -> ActionOutcome:
        fingerprint = request.fingerprint()
        # Validate supplied approval before duplicate/exception handling so a stale or
        # unrelated grant can never be used as harmless-looking bypass input.
        if approval is not None:
            approval.assert_valid_for(request)

        with self.ledger.lock.acquire(request.idempotency_key):
            previous = self.ledger.read(request)
            if previous:
                if previous.get("request_fingerprint") != fingerprint:
                    raise DuplicateAction("idempotency key reused for a different action request")
                state = previous.get("ledger_status")
                if state == "completed":
                    return self._outcome_from_record(previous, duplicate=True)
                if state in {"claimed", "uncertain"}:
                    raise UncertainActionOutcome("previous action outcome is in-flight or uncertain; reconcile before retry")
                if state == "failed" and not previous.get("safe_to_retry", False):
                    raise UncertainActionOutcome("previous failed action is not safe to retry automatically")

            authorization = self.gate.authorize(
                request,
                approval=approval,
                host_idempotency_supported=host_idempotency_supported,
            )
            if not authorization.authorized:
                raise PermissionDenied(f"{authorization.disposition.value}: {authorization.reason}")

            self.ledger.write(request, {
                "ledger_status": "claimed",
                "request_id": request.request_id,
                "request_fingerprint": fingerprint,
                "action_class": request.action_class,
                "scope": request.scope.value,
                "operation": request.operation,
                "claimed_at": utc_now(),
            })

            try:
                # Final time-of-check/time-of-use binding immediately before dispatch.
                self._assert_dispatch_binding(
                    request,
                    expected_fingerprint=fingerprint,
                    approval=approval,
                )
            except PermissionDenied:
                self.ledger.write(request, {
                    "ledger_status": "failed",
                    "request_id": request.request_id,
                    "request_fingerprint": fingerprint,
                    "safe_to_retry": True,
                    "effect_occurred": False,
                    "recorded_at": utc_now(),
                })
                raise

            try:
                response = host.request_action(request.to_dict())
            except Exception as exc:
                if request.is_side_effect:
                    self.ledger.write(request, {
                        "ledger_status": "uncertain",
                        "request_id": request.request_id,
                        "request_fingerprint": fingerprint,
                        "action_class": request.action_class,
                        "scope": request.scope.value,
                        "operation": request.operation,
                        "error_type": type(exc).__name__,
                        "recorded_at": utc_now(),
                    })
                    raise UncertainActionOutcome("host raised after side-effect dispatch; automatic retry is forbidden") from exc
                self.ledger.write(request, {
                    "ledger_status": "failed",
                    "request_id": request.request_id,
                    "request_fingerprint": fingerprint,
                    "safe_to_retry": True,
                    "error_type": type(exc).__name__,
                    "recorded_at": utc_now(),
                })
                raise

            if not isinstance(response, dict):
                self.ledger.write(request, {
                    "ledger_status": "uncertain" if request.is_side_effect else "failed",
                    "request_id": request.request_id,
                    "request_fingerprint": fingerprint,
                    "safe_to_retry": not request.is_side_effect,
                    "recorded_at": utc_now(),
                })
                if request.is_side_effect:
                    raise UncertainActionOutcome("invalid host response after side-effect dispatch; reconcile before retry")
                raise ValidationError("host action response must be an object")

            status = response.get("status")
            if status not in {"succeeded", "failed", "uncertain"}:
                self.ledger.write(request, {
                    "ledger_status": "uncertain" if request.is_side_effect else "failed",
                    "request_id": request.request_id,
                    "request_fingerprint": fingerprint,
                    "safe_to_retry": not request.is_side_effect,
                    "recorded_at": utc_now(),
                })
                if request.is_side_effect:
                    raise UncertainActionOutcome("invalid host status after side-effect dispatch; reconcile before retry")
                raise ValidationError("host action response status must be succeeded, failed, or uncertain")

            minimal = self._minimal_response(response)
            if status == "uncertain":
                self.ledger.write(request, {
                    "ledger_status": "uncertain",
                    "request_id": request.request_id,
                    "request_fingerprint": fingerprint,
                    "response": minimal,
                    "recorded_at": utc_now(),
                })
                raise UncertainActionOutcome("host reported uncertain action outcome; reconcile before retry")

            if status == "succeeded" and request.is_side_effect and not response.get("receipt_id"):
                self.ledger.write(request, {
                    "ledger_status": "uncertain",
                    "request_id": request.request_id,
                    "request_fingerprint": fingerprint,
                    "response": minimal,
                    "recorded_at": utc_now(),
                })
                raise UncertainActionOutcome("successful side effect lacks host receipt; cannot prove replay safety")

            if status == "failed":
                safe_to_retry = bool(response.get("effect_occurred") is False) or not request.is_side_effect or host_idempotency_supported
                self.ledger.write(request, {
                    "ledger_status": "failed",
                    "request_id": request.request_id,
                    "request_fingerprint": fingerprint,
                    "safe_to_retry": safe_to_retry,
                    "response": minimal,
                    "recorded_at": utc_now(),
                })
                return ActionOutcome("failed", response.get("receipt_id"), dict(response.get("result", {})))

            self.ledger.write(request, {
                "ledger_status": "completed",
                "request_id": request.request_id,
                "request_fingerprint": fingerprint,
                "response": minimal,
                "recorded_at": utc_now(),
            })
            return ActionOutcome("succeeded", response.get("receipt_id"), dict(response.get("result", {})))

    def reconcile(
        self,
        request: ActionRequest,
        *,
        status: str,
        receipt_id: Optional[str],
        effect_occurred: Optional[bool] = None,
        source: AuthorityTier,
    ) -> ActionOutcome:
        if source > AuthorityTier.VERIFIED_EVIDENCE:
            raise PermissionDenied("reconciliation requires verified evidence or stronger authority")
        if status not in {"succeeded", "failed"}:
            raise ValidationError("reconciliation status must be succeeded or failed")
        if status == "succeeded" and not receipt_id:
            raise ValidationError("successful reconciliation requires a receipt_id")
        fingerprint = request.fingerprint()
        with self.ledger.lock.acquire(request.idempotency_key):
            previous = self.ledger.read(request)
            if not previous:
                raise ValidationError("cannot reconcile an action with no prior ledger record")
            if previous.get("request_fingerprint") != fingerprint:
                raise DuplicateAction("reconciliation request does not match original action fingerprint")
            if previous.get("ledger_status") == "completed":
                return self._outcome_from_record(previous, duplicate=True)
            if status == "failed" and effect_occurred is not False:
                self.ledger.write(request, {
                    "ledger_status": "uncertain",
                    "request_id": request.request_id,
                    "request_fingerprint": fingerprint,
                    "response": {"status": "failed", "receipt_id": receipt_id, "effect_occurred": effect_occurred},
                    "recorded_at": utc_now(),
                })
                raise UncertainActionOutcome("failed reconciliation did not prove that no side effect occurred")
            ledger_status = "completed" if status == "succeeded" else "failed"
            self.ledger.write(request, {
                "ledger_status": ledger_status,
                "request_id": request.request_id,
                "request_fingerprint": fingerprint,
                "safe_to_retry": bool(status == "failed" and effect_occurred is False),
                "response": {"status": status, "receipt_id": receipt_id, "effect_occurred": effect_occurred},
                "reconciled_at": utc_now(),
                "reconciliation_authority": source.name,
            })
            return ActionOutcome(status, receipt_id, {})
