from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional

from .action_boundary import ActionExecutor, ActionOutcome, ActionRequest, ApprovalGrant
from .cadence import Trigger
from .controller import BrainController
from .errors import CognitionContractError
from .orchestrator import TickPlan, TickPlanner
from .policy import BrainPolicy
from .proposal_apply import AppliedProposal, ProposalApplier
from .ranking import NotificationClass
from .reasoner import ContextAssembler, ReasonerAdapter, parse_reasoner_output


@dataclass(frozen=True)
class RuntimeErrorRecord:
    stage: str
    request_id: str
    error_type: str
    message: str
    proposal_index: Optional[int] = None


@dataclass(frozen=True)
class SurfaceItem:
    object_ref: str
    proposal_kind: str
    notification: str
    reason: str
    attention_fingerprint: str


@dataclass
class TickRunResult:
    trigger_type: str
    scope: str
    plan: TickPlan
    applied: List[AppliedProposal] = field(default_factory=list)
    surface_items: List[SurfaceItem] = field(default_factory=list)
    errors: List[RuntimeErrorRecord] = field(default_factory=list)
    reasoner_calls: int = 0

    @property
    def ok(self) -> bool:
        return not self.errors


class BrainRuntime:
    """Runtime-neutral orchestration around the deterministic Brain core.

    Models propose. ProposalApplier gates/persists. Attention decides whether an
    item may be surfaced. This class never calls host.notify_user automatically
    and never converts model output directly into an external action.
    """

    def __init__(self, root: str, policy: Optional[BrainPolicy] = None):
        self.controller = BrainController(root, policy=policy)
        self.policy = self.controller.policy
        self.planner = TickPlanner(self.controller)
        self.applier = ProposalApplier(self.controller)
        self.action_executor = ActionExecutor(self.controller.layout.root, self.policy)

    def _refresh_policy(self, scope: str) -> BrainPolicy:
        self.policy = self.controller.refresh_policy(scope)
        self.action_executor.gate.policy = self.policy
        return self.policy

    @staticmethod
    def _reasoner_id(reasoner: ReasonerAdapter) -> str:
        value = getattr(reasoner, "model_id", "")
        if not isinstance(value, str) or not value.strip():
            raise CognitionContractError("reasoner adapter must expose a non-empty model_id")
        return value.strip()

    def _surface(
        self,
        applied: AppliedProposal,
        *,
        trigger: Trigger,
        session_id: Optional[str],
    ) -> Optional[SurfaceItem]:
        if applied.notification in {NotificationClass.STORE, NotificationClass.DROP}:
            return None
        fingerprint = applied.attention_fingerprint or applied.object_ref
        decision = self.controller.attention.claim_notification(
            scope=trigger.scope.value,
            fingerprint=fingerprint,
            notification=applied.notification,
            policy=self.policy.attention,
            proactivity=self.policy.proactivity,
            session_id=session_id,
            unsolicited=trigger.trigger_type != "explicit",
        )
        if not decision.allowed:
            return None
        return SurfaceItem(
            object_ref=applied.object_ref,
            proposal_kind=applied.proposal_kind,
            notification=decision.notification.value,
            reason=decision.reason,
            attention_fingerprint=fingerprint,
        )

    def run_tick(
        self,
        trigger: Trigger,
        *,
        host: Any,
        reasoner: ReasonerAdapter,
        session_id: Optional[str] = None,
    ) -> TickRunResult:
        """Run one bounded cognition/application tick.

        The trigger is claimed before orientation and completed only after the
        entire bounded tick finishes. Model/application errors are captured as
        results, so one bad proposal does not turn into an automatic replay path.
        A process crash leaves a claimed receipt for explicit stale-claim recovery.
        """

        self._refresh_policy(trigger.scope.value)
        model_id = self._reasoner_id(reasoner)
        self.controller.trigger_ledger.claim(trigger)
        try:
            plan = self.planner.plan_unclaimed(trigger)
            result = TickRunResult(
                trigger_type=trigger.trigger_type,
                scope=trigger.scope.value,
                plan=plan,
            )
            assembler = ContextAssembler(self.controller, host)

            for request in plan.cognition_requests:
                permitted = list(request.output_contract.get("proposal_kinds") or [])
                if not permitted:
                    continue
                try:
                    context = assembler.build(request)
                    raw = reasoner.reason(request.to_dict(), context.to_dict())
                    result.reasoner_calls += 1
                    proposals = parse_reasoner_output(request, raw, source_model=model_id)
                except Exception as exc:
                    result.errors.append(RuntimeErrorRecord(
                        stage="reasoner",
                        request_id=request.request_id,
                        error_type=type(exc).__name__,
                        message=str(exc),
                    ))
                    continue

                for index, proposal in enumerate(proposals):
                    try:
                        applied = self.applier.apply(request, proposal)
                        result.applied.append(applied)
                        surface = self._surface(applied, trigger=trigger, session_id=session_id)
                        if surface is not None:
                            result.surface_items.append(surface)
                    except Exception as exc:
                        result.errors.append(RuntimeErrorRecord(
                            stage="proposal_application",
                            request_id=request.request_id,
                            proposal_index=index,
                            error_type=type(exc).__name__,
                            message=str(exc),
                        ))
            self.controller.trigger_ledger.complete(trigger)
            return result
        except Exception:
            raise

    def execute_action(
        self,
        request: ActionRequest,
        *,
        host: Any,
        approval: Optional[ApprovalGrant] = None,
        host_idempotency_supported: bool = False,
    ) -> ActionOutcome:
        """Explicit action path. No cognition proposal can call this implicitly."""

        self._refresh_policy(request.scope.value)
        return self.action_executor.execute(
            request,
            host,
            approval=approval,
            host_idempotency_supported=host_idempotency_supported,
        )
