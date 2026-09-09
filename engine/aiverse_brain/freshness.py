from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional, TYPE_CHECKING

from .authority import AuthorityTier
from .errors import AuthorityError, ValidationError
from .models import BrainObject, EvidenceRef, utc_now

if TYPE_CHECKING:
    from .controller import BrainController


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


@dataclass(frozen=True)
class FreshnessAssessment:
    state: str
    observed_at: Optional[str]
    expires_at: Optional[str]
    age_seconds: Optional[float]
    reason: str


def assess_freshness(obj: BrainObject, *, now: Optional[datetime] = None) -> FreshnessAssessment:
    if obj.kind != "model_belief":
        raise ValidationError("freshness assessment currently applies to model_belief objects")
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    payload = obj.payload
    observed_at = payload.get("observed_at")
    expires_at = payload.get("expires_at")
    age_seconds = (now - _parse(observed_at)).total_seconds() if observed_at else None

    if obj.status == "CONTRADICTED" or payload.get("epistemic_state") == "contradicted":
        return FreshnessAssessment("contradicted", observed_at, expires_at, age_seconds, "contradictory evidence")
    if payload.get("epistemic_state") == "stale":
        return FreshnessAssessment("stale", observed_at, expires_at, age_seconds, "belief already marked stale")
    if expires_at and now >= _parse(expires_at):
        return FreshnessAssessment("stale", observed_at, expires_at, age_seconds, "explicit expiry reached")
    max_age = payload.get("max_age_seconds")
    if max_age is not None and age_seconds is not None and age_seconds >= float(max_age):
        return FreshnessAssessment("stale", observed_at, expires_at, age_seconds, "maximum evidence age exceeded")
    expiring_evidence = [item for item in obj.evidence_refs if item.expires_at]
    if obj.evidence_refs and len(expiring_evidence) == len(obj.evidence_refs):
        if all(now >= _parse(item.expires_at) for item in expiring_evidence):
            return FreshnessAssessment("stale", observed_at, expires_at, age_seconds, "all supporting evidence expired")
    if observed_at:
        return FreshnessAssessment("current", observed_at, expires_at, age_seconds, "within declared freshness window")
    return FreshnessAssessment("unknown", observed_at, expires_at, age_seconds, "no observation timestamp or freshness contract")


class FreshnessService:
    def __init__(self, controller: "BrainController"):
        self.controller = controller

    @staticmethod
    def _append_evidence(obj: BrainObject, evidence: List[EvidenceRef]) -> None:
        existing = {item.ref for item in obj.evidence_refs}
        for item in evidence:
            if item.ref not in existing:
                obj.evidence_refs.append(item)
                existing.add(item.ref)

    def create_belief(
        self,
        scope: str,
        *,
        domain: str,
        statement: str,
        epistemic_state: str,
        confidence: float,
        evidence_refs: Optional[List[EvidenceRef]] = None,
        observed_at: Optional[str] = None,
        expires_at: Optional[str] = None,
        max_age_seconds: Optional[int] = None,
        actor: str = "brain",
    ) -> BrainObject:
        evidence_refs = list(evidence_refs or [])
        if epistemic_state in {"known", "inferred"} and not evidence_refs:
            raise ValidationError(f"{epistemic_state} model belief requires evidence")
        payload = {
            "domain": domain,
            "statement": statement,
            "epistemic_state": epistemic_state,
            "confidence": confidence,
            "observed_at": observed_at or utc_now(),
            "expires_at": expires_at,
            "max_age_seconds": max_age_seconds,
            "last_reviewed": utc_now(),
            "contradiction_refs": [],
        }
        return self.controller.create(
            "model_belief", scope, "ACTIVE", payload,
            source=AuthorityTier.TEMPORARY_HYPOTHESIS,
            actor=actor,
            evidence_refs=evidence_refs,
        )

    def review(self, scope: str, belief_id: str, *, actor: str = "brain", now: Optional[datetime] = None) -> FreshnessAssessment:
        obj = self.controller.store.load("model_belief", scope, belief_id)
        assessment = assess_freshness(obj, now=now)
        if assessment.state == "stale" and obj.payload.get("epistemic_state") != "stale":
            expected = obj.revision
            obj.payload["epistemic_state"] = "stale"
            obj.payload["last_reviewed"] = utc_now()
            obj.updated_by = actor
            self.controller.store.save(obj, expected_revision=expected)
        return assessment

    def mark_contradicted(
        self,
        scope: str,
        belief_id: str,
        evidence_refs: List[EvidenceRef],
        *,
        actor: str = "brain",
    ) -> BrainObject:
        if not evidence_refs:
            raise ValidationError("contradiction requires evidence")
        obj = self.controller.store.load("model_belief", scope, belief_id)
        if obj.status == "RETIRED":
            raise ValidationError("retired belief cannot be contradicted")
        expected = obj.revision
        self._append_evidence(obj, evidence_refs)
        refs = list(obj.payload.get("contradiction_refs") or [])
        for evidence in evidence_refs:
            if evidence.ref not in refs:
                refs.append(evidence.ref)
        obj.payload["contradiction_refs"] = refs
        obj.payload["epistemic_state"] = "contradicted"
        obj.payload["last_reviewed"] = utc_now()
        obj.updated_by = actor
        saved = self.controller.store.save(obj, expected_revision=expected)
        if saved.status == "ACTIVE":
            saved = self.controller.transition(
                "model_belief", scope, belief_id, "CONTRADICTED",
                source=AuthorityTier.VERIFIED_EVIDENCE, actor=actor,
            )
        return saved

    def refresh(
        self,
        scope: str,
        belief_id: str,
        *,
        evidence_refs: List[EvidenceRef],
        source: AuthorityTier,
        epistemic_state: str = "known",
        confidence: Optional[float] = None,
        observed_at: Optional[str] = None,
        expires_at: Optional[str] = None,
        max_age_seconds: Optional[int] = None,
        actor: str = "brain",
    ) -> BrainObject:
        if source > AuthorityTier.VERIFIED_EVIDENCE:
            raise AuthorityError("refreshing stale/contradicted belief requires verified evidence or stronger authority")
        if not evidence_refs:
            raise ValidationError("belief refresh requires evidence")
        if epistemic_state not in {"known", "inferred"}:
            raise ValidationError("refreshed belief must be known or inferred")
        obj = self.controller.store.load("model_belief", scope, belief_id)
        if obj.status == "RETIRED":
            raise ValidationError("retired belief cannot be refreshed")
        expected = obj.revision
        self._append_evidence(obj, evidence_refs)
        obj.payload["epistemic_state"] = epistemic_state
        if confidence is not None:
            obj.payload["confidence"] = confidence
        obj.payload["observed_at"] = observed_at or utc_now()
        if expires_at is not None:
            obj.payload["expires_at"] = expires_at
        if max_age_seconds is not None:
            obj.payload["max_age_seconds"] = max_age_seconds
        obj.payload["last_reviewed"] = utc_now()
        obj.payload["contradiction_refs"] = []
        obj.updated_by = actor
        saved = self.controller.store.save(obj, expected_revision=expected)
        if saved.status == "CONTRADICTED":
            saved = self.controller.transition(
                "model_belief", scope, belief_id, "ACTIVE", source=source, actor=actor,
            )
        return saved
