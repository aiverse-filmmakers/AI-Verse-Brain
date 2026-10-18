from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .attention import AttentionLedger
from .authority import (
    AuthorityTier,
    PURPOSE_STRATEGIC_INTENT_SUBTYPES,
    assert_policy_mutation,
    assert_strategic_intent_replacement,
)
from .cadence import Trigger, TriggerLedger
from .direction import DirectionService
from .effective_policy import (
    assert_policy_tightens,
    load_effective_policy,
    validate_policy_payload_for_scope,
)
from .errors import AuthorityError, PolicyViolation, ValidationError
from .evaluator import EvaluationService
from .freshness import FreshnessService
from .goal import GoalService
from .improvement import ImprovementCandidateService
from .learning import LearningService, assert_learning_transition, assert_strategy_activation
from .models import BrainObject, EvidenceRef, Scope
from .owner_write import route_durable_write
from .policy import BrainPolicy
from .progress import ProgressTracker
from .state_machine import assert_creation, assert_transition
from .storage import ObjectStore, StorageLayout
from .validation import workspace_link_scope
from .strategy_revision import StrategyRevisionService


@dataclass
class Orientation:
    scope: str
    confirmed_goals: List[Dict[str, Any]]
    active_practices: List[Dict[str, Any]]
    active_initiatives: List[Dict[str, Any]]
    current_objectives: List[Dict[str, Any]]
    hard_policies: List[Dict[str, Any]]


class BrainController:
    """Deterministic state/control core. It does not perform model reasoning or external side effects."""

    ACTIVE_INITIATIVE_STATES = {"ACCEPTED", "ACTIVE", "WAITING", "BLOCKED", "STALLED", "REVIEW"}
    ACTIVE_OBJECTIVE_STATES = {"READY", "RUNNING", "WAITING", "BLOCKED", "STALLED", "VERIFYING", "INSUFFICIENT_EVIDENCE"}

    def __init__(self, root: str, policy: Optional[BrainPolicy] = None):
        self.layout = StorageLayout.detect(root)
        self.store = ObjectStore(self.layout)
        self._caller_policy = policy
        self.policy = load_effective_policy(self.store, "operator", caller_override=policy)
        self.trigger_ledger = TriggerLedger(self.layout.runtime_dir)
        self.attention = AttentionLedger(self.layout.runtime_dir)
        self.direction = DirectionService(self)
        self.progress = ProgressTracker(self)
        self.evaluator = EvaluationService(self)
        self.freshness = FreshnessService(self)
        self.learning = LearningService(self)
        self.goals = GoalService(self)
        self.improvements = ImprovementCandidateService(self)
        self.strategy_revisions = StrategyRevisionService(self)

    def refresh_policy(self, scope: str = "operator") -> BrainPolicy:
        """Reload the persisted policy for ``scope`` and re-apply only tightening caller overrides."""
        self.policy = load_effective_policy(self.store, scope, caller_override=self._caller_policy)
        return self.policy

    def route_durable_write(self, host: Any, classification: str, payload: Dict[str, Any], scope: str):
        """Route non-Brain durable state through the selected canonical-owner host boundary."""
        Scope(scope)
        return route_durable_write(host, classification, payload, scope)

    def direction_owner(self, scope: str) -> str:
        from .direction_ownership import direction_owner_for
        return direction_owner_for(self, scope)

    def _assert_intent_write_owner(self, scope: str, status: str, actor: str) -> None:
        """Brain may write strategic intent only when it is the durable owner for this scope.

        The sole exception is the non-active PROPOSED staging used by explicit handover. The
        ownership marker is flipped before any staged intent can transition to CONFIRMED.
        """
        if self.layout.mode != "native":
            return
        owner = self.direction_owner(scope)
        if owner == "brain":
            return
        if owner == "os" and status == "PROPOSED" and actor == "user:direction-handover":
            return
        raise ValidationError(
            f"strategic direction for {scope} is owned by AI-Verse OS; "
            "explicitly hand it over before writing Brain intent"
        )

    def _validate_policy_change(self, scope: str, payload: Dict[str, Any]) -> BrainPolicy:
        candidate = validate_policy_payload_for_scope(self.store, scope, payload)
        if self._caller_policy is not None:
            assert_policy_tightens(candidate, self._caller_policy, source="caller override")
        return candidate

    def _validate_purpose_supersedes(self, scope: str, payload: Dict[str, Any], supersedes: Optional[str]) -> None:
        subtype = payload.get("subtype")
        if not supersedes or subtype not in PURPOSE_STRATEGIC_INTENT_SUBTYPES:
            return
        prior = self.store.load("intent", scope, supersedes)
        if prior.payload.get("subtype") != subtype:
            raise ValidationError("Purpose strategic supersession requires the same intent subtype")

    def create(
        self,
        kind: str,
        scope: str,
        status: str,
        payload: Dict[str, Any],
        *,
        source: AuthorityTier = AuthorityTier.TEMPORARY_HYPOTHESIS,
        actor: str = "brain",
        source_refs: Optional[List[str]] = None,
        evidence_refs: Optional[List[EvidenceRef]] = None,
        supersedes: Optional[str] = None,
    ) -> BrainObject:
        assert_creation(kind, status, source)
        if kind == "intent":
            self._assert_intent_write_owner(scope, status, actor)
            self._validate_purpose_supersedes(scope, payload, supersedes)
            if payload.get("workspace_links") or payload.get("workspace_link_operations"):
                raise ValidationError("workspace links must use the Brain link_workspace_intent owner API")
        if kind == "policy":
            self._validate_policy_change(scope, payload)
            if self.store.list("policy", scope, {"ACTIVE"}):
                raise ValidationError(f"conflicting active policy in {scope}; supersede or update the existing policy first")
        obj = BrainObject.new(kind, scope, status, payload, created_by=actor)
        obj.source_refs = list(source_refs or [])
        obj.evidence_refs = list(evidence_refs or [])
        obj.supersedes = supersedes
        saved = self.store.save(obj, expected_revision=-1)
        if kind == "policy":
            self.refresh_policy(scope)
        return saved

    def _assert_initiative_capacity(self, scope: str, *, exclude_id: Optional[str] = None) -> None:
        policy = self.refresh_policy(scope)
        active = [
            item for item in self.store.list("initiative", scope, self.ACTIVE_INITIATIVE_STATES)
            if item.id != exclude_id
        ]
        if len(active) >= policy.attention.max_active_initiatives:
            raise PolicyViolation(f"active initiative WIP cap reached ({policy.attention.max_active_initiatives})")

    def _assert_objective_capacity(self, scope: str, *, exclude_id: Optional[str] = None) -> None:
        policy = self.refresh_policy(scope)
        active = [
            item for item in self.store.list("objective", scope, self.ACTIVE_OBJECTIVE_STATES)
            if item.id != exclude_id
        ]
        if len(active) >= policy.resources.max_parallel_objectives:
            raise PolicyViolation(f"parallel objective cap reached ({policy.resources.max_parallel_objectives})")

    @staticmethod
    def _assert_objective_passable(obj: BrainObject) -> None:
        criteria = obj.payload.get("criteria", [])
        if not criteria:
            raise ValidationError("objective cannot pass without criteria")
        invalid = [c.get("id", "?") for c in criteria if c.get("status") not in {"passed", "not_applicable"}]
        if invalid:
            raise ValidationError("objective cannot pass while criteria remain unverified/failed: " + ", ".join(invalid))
        passed = [c for c in criteria if c.get("status") == "passed"]
        if not passed:
            raise ValidationError("objective cannot pass without at least one passed criterion")
        if any(not c.get("evidence_refs") for c in passed):
            raise ValidationError("every passed criterion requires evidence_refs")

    @staticmethod
    def _assert_initiative_completable(obj: BrainObject) -> None:
        if not obj.payload.get("evaluation_refs"):
            raise ValidationError("initiative completion requires evaluation_refs")

    def transition(self, kind: str, scope: str, object_id: str, target: str, *, source: AuthorityTier, actor: str) -> BrainObject:
        if kind != "policy":
            policy = self.refresh_policy(scope)
        else:
            policy = self.policy
        obj = self.store.load(kind, scope, object_id)
        if kind == "intent":
            self._assert_intent_write_owner(scope, target, actor)
            if target == "SUPERSEDED" and obj.payload.get("subtype") in PURPOSE_STRATEGIC_INTENT_SUBTYPES:
                assert_strategic_intent_replacement(source)
        assert_transition(kind, obj.status, target, source)
        if kind == "initiative" and target in {"ACCEPTED", "ACTIVE"} and obj.status not in self.ACTIVE_INITIATIVE_STATES:
            self._assert_initiative_capacity(scope, exclude_id=obj.id)
        if kind == "objective" and target == "READY" and obj.status not in self.ACTIVE_OBJECTIVE_STATES:
            self._assert_objective_capacity(scope, exclude_id=obj.id)
        if kind == "objective" and target == "PASSED":
            self._assert_objective_passable(obj)
        if kind == "initiative" and target == "COMPLETED":
            self._assert_initiative_completable(obj)
        if kind == "learning":
            assert_learning_transition(obj, target, source)
        if kind == "strategy_rule" and target == "ACTIVE":
            assert_strategy_activation(obj, source, policy)
        expected = obj.revision
        obj.status = target
        obj.updated_by = actor
        saved = self.store.save(obj, expected_revision=expected)
        if kind == "policy":
            self.refresh_policy(scope)
        return saved

    def update_policy(self, object_id: str, scope: str, payload: Dict[str, Any], *, source: AuthorityTier, actor: str) -> BrainObject:
        assert_policy_mutation(source)
        self._validate_policy_change(scope, payload)
        obj = self.store.load("policy", scope, object_id)
        if obj.status != "ACTIVE":
            raise ValidationError("only an ACTIVE policy may be updated")
        expected = obj.revision
        obj.payload = dict(payload)
        obj.updated_by = actor
        saved = self.store.save(obj, expected_revision=expected)
        self.refresh_policy(scope)
        return saved

    def _mutate_workspace_intent_link(
        self, object_id: str, workspace_scope: str, *, action: str,
        expected_revision: int, operation_id: str, evidence_ref: str,
        source: AuthorityTier,
    ) -> BrainObject:
        """Owner API for explicit, visibility-only operator-intent/workspace links."""
        if source != AuthorityTier.EXPLICIT_USER:
            raise AuthorityError("explicit user authority required: workspace intent link")
        if action not in {"add", "remove"}:
            raise ValidationError("workspace intent link action must be add or remove")
        target = Scope(workspace_scope)
        if target.is_operator:
            raise ValidationError("workspace intent links require a workspace scope")
        if not isinstance(operation_id, str) or not operation_id.strip() or len(operation_id) > 128:
            raise ValidationError("operation_id must be 1..128 non-whitespace characters")
        if not isinstance(evidence_ref, str) or not evidence_ref.strip() or len(evidence_ref) > 2048:
            raise ValidationError("exact user evidence reference is required")
        if not isinstance(expected_revision, int) or isinstance(expected_revision, bool) or expected_revision < 0:
            raise ValidationError("expected_revision must be an integer >= 0")
        if self.direction_owner("operator") != "brain":
            raise ValidationError("operator direction must be Brain-owned before linking intents")

        obj = self.store.load("intent", "operator", object_id)
        if obj.status not in {"CONFIRMED", "ACTIVE", "PAUSED"}:
            raise ValidationError("only a current operator intent may be linked")
        payload = dict(obj.payload)
        raw_operations = payload.get("workspace_link_operations", [])
        if not isinstance(raw_operations, list) or len(raw_operations) > 128 or any(
            not isinstance(item, dict) or set(item) != {"id", "action", "workspace_scope", "evidence_ref"}
            for item in raw_operations
        ):
            raise ValidationError("operator intent workspace link operation metadata is invalid")
        operations = list(raw_operations)
        raw_links = payload.get("workspace_links", [])
        if not isinstance(raw_links, list) or len(raw_links) > 32:
            raise ValidationError("operator intent workspace link metadata is invalid")
        link_scopes = [workspace_link_scope(item) for item in raw_links]
        if len(link_scopes) != len(set(link_scopes)):
            raise ValidationError("operator intent workspace link scopes are duplicated")
        for legacy in raw_links:
            if isinstance(legacy, dict):
                legacy_operation = {
                    "id": legacy["operation_id"], "action": "add",
                    "workspace_scope": workspace_link_scope(legacy),
                    "evidence_ref": legacy["source_refs"][0],
                }
                existing = next((item for item in operations if item["id"] == legacy_operation["id"]), None)
                if existing is None:
                    operations.append(legacy_operation)
                elif existing != legacy_operation:
                    raise ValidationError("legacy workspace link operation conflicts with Brain history")
        prior = next((item for item in operations if item["id"] == operation_id), None)
        if prior is not None:
            if (prior["action"] != action or prior["workspace_scope"] != workspace_scope
                    or prior["evidence_ref"] != evidence_ref):
                raise ValidationError("operation_id was already used for a different workspace link request")
            return obj
        if len(operations) > 128:
            raise ValidationError("operator intent workspace link operation limit reached (128)")
        if obj.revision != expected_revision:
            raise ValidationError("workspace intent link revision conflict")

        links = list(raw_links)
        removed_refs = []
        if action == "add":
            if workspace_scope not in link_scopes:
                if len(links) >= 32:
                    raise ValidationError("operator intent workspace link limit reached (32)")
                links.append(workspace_scope)
        else:
            for item in links:
                if workspace_link_scope(item) == workspace_scope and isinstance(item, dict):
                    removed_refs.extend(item["source_refs"])
            links = [item for item in links if workspace_link_scope(item) != workspace_scope]

        payload["workspace_links"] = links
        operations.append({"id": operation_id, "action": action, "workspace_scope": workspace_scope, "evidence_ref": evidence_ref})
        obj.source_refs = list(dict.fromkeys([*obj.source_refs, *removed_refs]))
        payload["workspace_link_operations"] = operations[-128:]
        obj.payload = payload
        obj.updated_by = "user:workspace-link"
        return self.store.save(obj, expected_revision=expected_revision)

    def link_workspace_intent(
        self, object_id: str, workspace_scope: str, *, expected_revision: int,
        operation_id: str, evidence_ref: str,
        source: AuthorityTier = AuthorityTier.EXPLICIT_USER,
    ) -> BrainObject:
        return self._mutate_workspace_intent_link(
            object_id, workspace_scope, action="add", expected_revision=expected_revision,
            operation_id=operation_id, evidence_ref=evidence_ref, source=source,
        )

    def unlink_workspace_intent(
        self, object_id: str, workspace_scope: str, *, expected_revision: int,
        operation_id: str, evidence_ref: str,
        source: AuthorityTier = AuthorityTier.EXPLICIT_USER,
    ) -> BrainObject:
        return self._mutate_workspace_intent_link(
            object_id, workspace_scope, action="remove", expected_revision=expected_revision,
            operation_id=operation_id, evidence_ref=evidence_ref, source=source,
        )

    def orientation(self, scope: str) -> Orientation:
        Scope(scope)
        policy = self.refresh_policy(scope)
        if self.direction_owner(scope) == "brain":
            goals = [
                o.to_dict() for o in self.store.list("intent", scope, {"CONFIRMED", "ACTIVE"})
                if o.payload.get("subtype") in {"goal", "desired_state"}
            ]
        else:
            # OS-owned direction is read through the host context, never duplicated into Brain orientation.
            goals = []
        practices = [o.to_dict() for o in self.store.list("practice", scope, {"ACTIVE"})]
        initiatives = [o.to_dict() for o in self.store.list("initiative", scope, self.ACTIVE_INITIATIVE_STATES)]
        objectives = [o.to_dict() for o in self.store.list("objective", scope, self.ACTIVE_OBJECTIVE_STATES)]
        policies = [o.to_dict() for o in self.store.list("policy", scope)]
        return Orientation(scope, goals, practices, initiatives[: policy.attention.max_active_initiatives], objectives, policies)

    def run_trigger(self, trigger: Trigger) -> Orientation:
        self.trigger_ledger.claim(trigger)
        try:
            result = self.orientation(trigger.scope.value)
        except Exception:
            # Claimed receipt remains for explicit stale-claim recovery. Do not auto-replay uncertain work.
            raise
        self.trigger_ledger.complete(trigger)
        return result
