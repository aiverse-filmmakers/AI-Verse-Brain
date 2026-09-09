from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import re
from typing import Dict, List, Optional, Sequence, Tuple, TYPE_CHECKING

from .authority import AuthorityTier
from .errors import CooldownActive, DuplicateOpportunity, ValidationError
from .models import BrainObject, EvidenceRef
from .ranking import Eligibility, RankResult, ScoreComponents, rank
from .runtime_lock import RuntimeKeyLock

if TYPE_CHECKING:
    from .controller import BrainController

_TERMINAL_OPPORTUNITY = {"DISMISSED", "EXPIRED", "PROPOSED_INITIATIVE"}
_TERMINAL_INITIATIVE = {"REJECTED", "COMPLETED", "ABANDONED", "SUPERSEDED"}
_ACTIVE_DUPLICATE_OPPORTUNITY = {"DETECTED", "WATCHING", "QUALIFIED"}
_ACTIVE_DUPLICATE_INITIATIVE = {
    "DISCOVERED", "PROPOSED", "DEFERRED", "ACCEPTED", "ACTIVE", "WAITING",
    "BLOCKED", "STALLED", "PAUSED", "REVIEW",
}


def _normalize(text: str) -> str:
    return " ".join(re.findall(r"[\w'-]+", text.casefold(), flags=re.UNICODE))


def proposal_fingerprint(scope: str, gap_refs: Sequence[str], hypothesis: str, dedupe_key: Optional[str] = None) -> str:
    """Stable exact fingerprint. `dedupe_key` lets a reasoner supply semantic grouping explicitly."""
    semantic = _normalize(dedupe_key) if dedupe_key else _normalize(hypothesis)
    raw = "|".join([scope, *sorted(set(gap_refs)), semantic])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


@dataclass(frozen=True)
class GapProposal:
    desired_state_refs: List[str]
    current_state_refs: List[str]
    interpretation: str
    assumptions: List[str] = field(default_factory=list)
    unknowns: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class OpportunityProposal:
    gap_refs: List[str]
    hypothesis: str
    confidence: float
    mechanism: Optional[str] = None
    expires_at: Optional[str] = None
    dedupe_key: Optional[str] = None


@dataclass(frozen=True)
class InitiativeProposal:
    serves: List[str]
    gap_refs: List[str]
    hypothesis: str
    outcome: str
    score_components: ScoreComponents
    next_action: Optional[str] = None
    review_after: Optional[str] = None
    invalidation_conditions: List[str] = field(default_factory=list)


class DirectionService:
    """Deterministic persistence/qualification layer for model-proposed Direction Loop candidates."""

    def __init__(self, controller: "BrainController"):
        self.controller = controller
        self.lock = RuntimeKeyLock(controller.layout.runtime_dir, namespace="direction")

    def create_gap(
        self,
        scope: str,
        proposal: GapProposal,
        *,
        source_refs: Optional[List[str]] = None,
        evidence_refs: Optional[List[EvidenceRef]] = None,
        actor: str = "brain",
    ) -> BrainObject:
        payload = {
            "desired_state_refs": list(proposal.desired_state_refs),
            "current_state_refs": list(proposal.current_state_refs),
            "interpretation": proposal.interpretation,
            "assumptions": list(proposal.assumptions),
            "unknowns": list(proposal.unknowns),
        }
        return self.controller.create(
            "gap", scope, "ACTIVE", payload,
            source=AuthorityTier.TEMPORARY_HYPOTHESIS,
            actor=actor,
            source_refs=source_refs or list(proposal.current_state_refs) + list(proposal.desired_state_refs),
            evidence_refs=evidence_refs or [],
        )

    def _assert_active_gaps(self, scope: str, gap_refs: Sequence[str]) -> None:
        if not gap_refs:
            raise ValidationError("opportunity/initiative requires at least one gap reference")
        for gap_id in gap_refs:
            gap = self.controller.store.load("gap", scope, gap_id)
            if gap.status != "ACTIVE":
                raise ValidationError(f"gap is not active: {gap_id} ({gap.status})")

    def _check_duplicate_or_cooldown(self, scope: str, fingerprint: str, now: datetime) -> None:
        for opportunity in self.controller.store.list("opportunity", scope):
            if opportunity.payload.get("cooldown_fingerprint") != fingerprint:
                continue
            if opportunity.status in _ACTIVE_DUPLICATE_OPPORTUNITY:
                raise DuplicateOpportunity(f"matching opportunity already exists: {opportunity.id}")
            if opportunity.status == "DISMISSED":
                age_hours = (now - _parse_ts(opportunity.updated_at)).total_seconds() / 3600
                if age_hours < self.controller.policy.attention.dismissal_cooldown_hours:
                    raise CooldownActive(f"matching opportunity was dismissed {age_hours:.1f}h ago")
        for initiative in self.controller.store.list("initiative", scope):
            if initiative.payload.get("source_fingerprint") != fingerprint:
                continue
            if initiative.status in _ACTIVE_DUPLICATE_INITIATIVE:
                raise DuplicateOpportunity(f"matching initiative already exists: {initiative.id}")
            if initiative.status in {"REJECTED", "ABANDONED"}:
                age_hours = (now - _parse_ts(initiative.updated_at)).total_seconds() / 3600
                if age_hours < self.controller.policy.attention.dismissal_cooldown_hours:
                    raise CooldownActive(f"matching initiative was rejected/abandoned {age_hours:.1f}h ago")

    def propose_opportunity(
        self,
        scope: str,
        proposal: OpportunityProposal,
        components: ScoreComponents,
        *,
        eligibility: Optional[Eligibility] = None,
        source_refs: Optional[List[str]] = None,
        evidence_refs: Optional[List[EvidenceRef]] = None,
        actor: str = "brain",
        now: Optional[datetime] = None,
    ) -> Tuple[BrainObject, RankResult]:
        self._assert_active_gaps(scope, proposal.gap_refs)
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        fingerprint = proposal_fingerprint(scope, proposal.gap_refs, proposal.hypothesis, proposal.dedupe_key)
        result = rank(
            eligibility or Eligibility(),
            components,
            minimum_interrupt=self.controller.policy.attention.minimum_interrupt_score,
            minimum_surface=self.controller.policy.attention.minimum_surface_score,
        )
        with self.lock.acquire(f"{scope}:{fingerprint}"):
            self._check_duplicate_or_cooldown(scope, fingerprint, now)
            payload: Dict[str, object] = {
                "gap_refs": list(proposal.gap_refs),
                "hypothesis": proposal.hypothesis,
                "confidence": proposal.confidence,
                "mechanism": proposal.mechanism,
                "expires_at": proposal.expires_at,
                "cooldown_fingerprint": fingerprint,
                "dedupe_key": proposal.dedupe_key,
                "score_components": dict(components.__dict__),
                "rank_result": {
                    "eligible": result.eligible,
                    "score": result.score,
                    "gate_failures": list(result.gate_failures),
                    "notification": result.notification.value,
                },
            }
            obj = self.controller.create(
                "opportunity", scope, "DETECTED", payload,
                source=AuthorityTier.TEMPORARY_HYPOTHESIS,
                actor=actor,
                source_refs=source_refs or list(proposal.gap_refs),
                evidence_refs=evidence_refs or [],
            )
            return obj, result

    def qualify_opportunity(self, scope: str, opportunity_id: str, *, actor: str = "brain") -> BrainObject:
        opportunity = self.controller.store.load("opportunity", scope, opportunity_id)
        if opportunity.status not in {"DETECTED", "WATCHING"}:
            raise ValidationError(f"opportunity cannot be qualified from {opportunity.status}")
        self._assert_active_gaps(scope, opportunity.payload["gap_refs"])
        rank_result = opportunity.payload.get("rank_result", {})
        if not rank_result.get("eligible"):
            failures = rank_result.get("gate_failures", [])
            raise ValidationError("opportunity failed eligibility gates: " + ", ".join(failures))
        return self.controller.transition(
            "opportunity", scope, opportunity_id, "QUALIFIED",
            source=AuthorityTier.VALIDATED_STRATEGY, actor=actor,
        )

    def propose_initiative(
        self,
        scope: str,
        opportunity_id: str,
        proposal: InitiativeProposal,
        *,
        actor: str = "brain",
    ) -> BrainObject:
        opportunity = self.controller.store.load("opportunity", scope, opportunity_id)
        if opportunity.status != "QUALIFIED":
            raise ValidationError("initiative proposal requires a QUALIFIED source opportunity")
        source_gaps = set(opportunity.payload.get("gap_refs", []))
        if not set(proposal.gap_refs).issubset(source_gaps):
            raise ValidationError("initiative gap refs must be covered by the qualified opportunity")
        self._assert_active_gaps(scope, proposal.gap_refs)
        source_components = opportunity.payload.get("score_components")
        if source_components != dict(proposal.score_components.__dict__):
            raise ValidationError("initiative score components must match the qualified opportunity")
        fingerprint = opportunity.payload.get("cooldown_fingerprint")
        if not fingerprint:
            raise ValidationError("qualified opportunity is missing its dedupe fingerprint")
        with self.lock.acquire(f"{scope}:{fingerprint}"):
            # Re-load under the runtime lock so two sessions cannot promote the same opportunity.
            opportunity = self.controller.store.load("opportunity", scope, opportunity_id)
            if opportunity.status != "QUALIFIED":
                raise DuplicateOpportunity("source opportunity was already consumed or changed")
            payload = {
                "serves": list(proposal.serves),
                "gap_refs": list(proposal.gap_refs),
                "hypothesis": proposal.hypothesis,
                "outcome": proposal.outcome,
                "score_components": dict(proposal.score_components.__dict__),
                "rank_result": dict(opportunity.payload.get("rank_result", {})),
                "source_opportunity_ref": opportunity.id,
                "source_fingerprint": fingerprint,
                "next_action": proposal.next_action,
                "review_after": proposal.review_after,
                "invalidation_conditions": list(proposal.invalidation_conditions),
                "evaluation_refs": [],
            }
            initiative = self.controller.create(
                "initiative", scope, "DISCOVERED", payload,
                source=AuthorityTier.TEMPORARY_HYPOTHESIS,
                actor=actor,
                source_refs=[opportunity.id] + list(proposal.gap_refs),
                evidence_refs=list(opportunity.evidence_refs),
            )
            initiative = self.controller.transition(
                "initiative", scope, initiative.id, "PROPOSED",
                source=AuthorityTier.TEMPORARY_HYPOTHESIS, actor=actor,
            )
            try:
                self.controller.transition(
                    "opportunity", scope, opportunity.id, "PROPOSED_INITIATIVE",
                    source=AuthorityTier.VALIDATED_STRATEGY, actor=actor,
                )
            except Exception:
                # Preserve a recoverable, non-active state if the source could not be consumed.
                try:
                    initiative = self.controller.transition(
                        "initiative", scope, initiative.id, "DEFERRED",
                        source=AuthorityTier.VALIDATED_STRATEGY, actor=actor,
                    )
                finally:
                    raise
            return initiative
