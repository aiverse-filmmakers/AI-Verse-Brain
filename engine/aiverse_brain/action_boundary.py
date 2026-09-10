from __future__ import annotations

"""Brain action boundary with mandatory host/OS permission intersection.

The mature replay/receipt implementation is preserved in
``action_boundary_legacy``.  This module keeps the public import path stable and
adds an independent host permission gate around every new action dispatch.
"""

from typing import Any, Optional

from .action_boundary_legacy import *  # noqa: F401,F403
from .action_boundary_legacy import ActionExecutor as _CoreActionExecutor
from .action_boundary_legacy import ApprovalGrant, ActionOutcome, ActionRequest
from .errors import PermissionDenied, ValidationError
from .host_permission import HostPermissionDecision, permission_request


class _PermissionRecheckingHost:
    """Re-check host permission immediately before the real side effect call."""

    def __init__(
        self,
        executor: "ActionExecutor",
        host: Any,
        request: ActionRequest,
        approval: Optional[ApprovalGrant],
    ) -> None:
        self._executor = executor
        self._host = host
        self._request = request
        self._approval = approval

    def request_action(self, payload):
        try:
            self._executor._require_host_permission(self._request, self._host, self._approval)
        except PermissionDenied as exc:
            # No external action has been dispatched yet.  Return an explicit safe
            # failure so the core ledger records effect_occurred=false rather than
            # misclassifying a permission revocation as an uncertain side effect.
            return {
                "status": "failed",
                "effect_occurred": False,
                "result": {
                    "permission_denied": True,
                    "reason": str(exc),
                },
            }
        return self._host.request_action(payload)


class ActionExecutor(_CoreActionExecutor):
    """Execute only when both Brain and the selected host permit the exact action.

    The host decision is restrictive only: ``allow`` cannot override Brain,
    ``approval_required`` adds an exact-user-approval requirement, and ``deny``
    blocks execution.  Malformed, missing, stale, or failing host permission
    checks fail closed.
    """

    @staticmethod
    def _require_host_permission(
        request: ActionRequest,
        host: Any,
        approval: Optional[ApprovalGrant],
    ) -> HostPermissionDecision:
        authorize = getattr(host, "authorize_action", None)
        if not callable(authorize):
            raise PermissionDenied("selected host does not provide an action permission decision")

        try:
            raw = authorize(permission_request(request))
        except PermissionDenied:
            raise
        except Exception as exc:
            raise PermissionDenied("host action permission check failed closed") from exc

        try:
            decision = HostPermissionDecision.from_result(
                raw,
                expected_fingerprint=request.fingerprint(),
                expected_scope=request.scope.value,
                expected_action_class=request.action_class,
            )
        except PermissionDenied:
            raise
        except (ValidationError, TypeError, ValueError) as exc:
            raise PermissionDenied("host returned an invalid action permission decision") from exc

        if decision.decision == "deny":
            raise PermissionDenied(f"host permission denied action: {decision.reason}")
        if decision.decision == "approval_required":
            if approval is None:
                raise PermissionDenied(f"host permission requires explicit approval: {decision.reason}")
            approval.assert_valid_for(request)
        return decision

    def execute(
        self,
        request: ActionRequest,
        host: Any,
        *,
        approval: Optional[ApprovalGrant] = None,
        host_idempotency_supported: bool = False,
    ) -> ActionOutcome:
        # Host permission is checked before the core can create a claimed dispatch
        # record, then checked again by the proxy at the exact request_action edge.
        # Brain's own ActionGate still runs unchanged inside the core executor, so
        # neither layer can make the other more permissive.
        self._require_host_permission(request, host, approval)
        checked_host = _PermissionRecheckingHost(self, host, request, approval)
        return super().execute(
            request,
            checked_host,
            approval=approval,
            host_idempotency_supported=host_idempotency_supported,
        )
