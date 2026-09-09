from __future__ import annotations

from dataclasses import fields
from typing import Any, Dict, Mapping, Optional

from .errors import ValidationError
from .models import Scope
from .policy import (
    ACTION_CLASSES,
    AttentionPolicy,
    BrainPolicy,
    EvolutionPolicy,
    ProactivityLevel,
    ResourcePolicy,
)


_POLICY_SECTIONS = {
    "attention": AttentionPolicy,
    "resources": ResourcePolicy,
    "evolution": EvolutionPolicy,
}
_ALLOWED_TOP_LEVEL = {"proactivity", "action_policy", "permission_matrix", *_POLICY_SECTIONS, *ACTION_CLASSES}


def clone_policy(policy: BrainPolicy) -> BrainPolicy:
    return BrainPolicy(
        proactivity=ProactivityLevel(policy.proactivity),
        action_policy=dict(policy.action_policy),
        attention=AttentionPolicy(**dict(policy.attention.__dict__)),
        resources=ResourcePolicy(**dict(policy.resources.__dict__)),
        evolution=EvolutionPolicy(**dict(policy.evolution.__dict__)),
    )


def _parse_proactivity(value: Any) -> ProactivityLevel:
    if isinstance(value, ProactivityLevel):
        return value
    if isinstance(value, bool):
        raise ValidationError("policy.proactivity must be P0-P4 or an integer from 0 to 4")
    if isinstance(value, int):
        try:
            return ProactivityLevel(value)
        except ValueError as exc:
            raise ValidationError("policy.proactivity must be an integer from 0 to 4") from exc
    if isinstance(value, str):
        text = value.strip().upper()
        aliases = {
            "P0": ProactivityLevel.P0_REACTIVE,
            "P1": ProactivityLevel.P1_OBSERVANT,
            "P2": ProactivityLevel.P2_ADVISORY,
            "P3": ProactivityLevel.P3_ASSISTIVE,
            "P4": ProactivityLevel.P4_DELEGATED,
        }
        if text in aliases:
            return aliases[text]
        if text in ProactivityLevel.__members__:
            return ProactivityLevel[text]
        if text.isdigit():
            try:
                return ProactivityLevel(int(text))
            except ValueError as exc:
                raise ValidationError("policy.proactivity must be an integer from 0 to 4") from exc
    raise ValidationError("policy.proactivity must be P0-P4 or an integer from 0 to 4")


def _apply_section(target: Any, value: Any, *, section: str) -> None:
    if not isinstance(value, Mapping):
        raise ValidationError(f"policy.{section} must be an object")
    allowed = {item.name for item in fields(type(target))}
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValidationError(f"unknown policy.{section} fields: {', '.join(unknown)}")
    for key, item in value.items():
        setattr(target, key, item)


def policy_from_payload(payload: Dict[str, Any], *, base: Optional[BrainPolicy] = None) -> BrainPolicy:
    """Apply one persisted policy object as a strict partial patch over ``base``."""
    if not isinstance(payload, dict):
        raise ValidationError("policy payload must be an object")
    unknown = sorted(set(payload) - _ALLOWED_TOP_LEVEL)
    if unknown:
        raise ValidationError("unknown policy fields: " + ", ".join(unknown))

    policy = clone_policy(base or BrainPolicy())
    if "proactivity" in payload:
        policy.proactivity = _parse_proactivity(payload["proactivity"])

    matrix_sources = []
    if "action_policy" in payload:
        matrix_sources.append(("action_policy", payload["action_policy"]))
    if "permission_matrix" in payload:
        matrix_sources.append(("permission_matrix", payload["permission_matrix"]))
    direct_actions = {key: payload[key] for key in ACTION_CLASSES if key in payload}
    if direct_actions:
        matrix_sources.append(("direct action fields", direct_actions))

    seen: Dict[str, str] = {}
    for label, matrix in matrix_sources:
        if not isinstance(matrix, Mapping):
            raise ValidationError(f"policy.{label} must be an object")
        unknown_actions = sorted(set(matrix) - set(ACTION_CLASSES))
        if unknown_actions:
            raise ValidationError("unknown policy action classes: " + ", ".join(unknown_actions))
        for action, decision in matrix.items():
            if action in seen and seen[action] != decision:
                raise ValidationError(f"conflicting policy decisions for {action}")
            seen[action] = decision
            policy.action_policy[action] = decision

    for section in _POLICY_SECTIONS:
        if section in payload:
            _apply_section(getattr(policy, section), payload[section], section=section)

    try:
        policy.validate()
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    return policy


def _decision_tightens(parent: str, child: str) -> bool:
    if child == parent or child == "deny":
        return True
    if child == "ask_every_time" and parent != "deny":
        return True
    return False


def assert_policy_tightens(parent: BrainPolicy, child: BrainPolicy, *, source: str) -> None:
    """Reject an override that can authorize behavior forbidden by its parent policy."""
    parent.validate()
    child.validate()
    failures = []

    if child.proactivity > parent.proactivity:
        failures.append("proactivity")

    for action in ACTION_CLASSES:
        parent_decision = parent.action_decision(action)
        child_decision = child.action_decision(action)
        if not _decision_tightens(parent_decision, child_decision):
            failures.append(f"action_policy.{action}")

    for name in ("max_active_initiatives", "max_proactive_items_per_session", "max_interruptions_per_day"):
        if getattr(child.attention, name) > getattr(parent.attention, name):
            failures.append(f"attention.{name}")
    for name in ("minimum_interrupt_score", "minimum_surface_score", "dismissal_cooldown_hours", "notification_cooldown_hours"):
        if getattr(child.attention, name) < getattr(parent.attention, name):
            failures.append(f"attention.{name}")

    for item in fields(ResourcePolicy):
        if getattr(child.resources, item.name) > getattr(parent.resources, item.name):
            failures.append(f"resources.{item.name}")

    if parent.evolution.allow_e1_auto_promotion is False and child.evolution.allow_e1_auto_promotion is True:
        failures.append("evolution.allow_e1_auto_promotion")
    if child.evolution.e1_min_evaluations < parent.evolution.e1_min_evaluations:
        failures.append("evolution.e1_min_evaluations")
    if child.evolution.e2_min_evaluations < parent.evolution.e2_min_evaluations:
        failures.append("evolution.e2_min_evaluations")
    if parent.evolution.e2_requires_user_approval is True and child.evolution.e2_requires_user_approval is False:
        failures.append("evolution.e2_requires_user_approval")

    if failures:
        raise ValidationError(
            f"{source} may only tighten the effective policy; weakening fields: " + ", ".join(sorted(set(failures)))
        )


def _single_active_payload(store: Any, scope: str) -> Optional[Dict[str, Any]]:
    active = store.list("policy", scope, {"ACTIVE"})
    if len(active) > 1:
        raise ValidationError(f"conflicting active policies in {scope}: expected at most one, found {len(active)}")
    if not active:
        return None
    payload = active[0].payload
    if not isinstance(payload, dict):
        raise ValidationError(f"active policy in {scope} has a malformed payload")
    return payload


def canonical_policy(store: Any, scope: str) -> BrainPolicy:
    """Load persisted operator policy plus an optional tightening workspace policy."""
    parsed_scope = Scope(scope)
    operator = BrainPolicy()
    operator_payload = _single_active_payload(store, "operator")
    if operator_payload is not None:
        operator = policy_from_payload(operator_payload, base=operator)

    if parsed_scope.is_operator:
        return operator

    workspace_payload = _single_active_payload(store, parsed_scope.value)
    if workspace_payload is None:
        return operator
    workspace = policy_from_payload(workspace_payload, base=operator)
    assert_policy_tightens(operator, workspace, source=f"workspace policy {parsed_scope.value}")
    return workspace


def validate_policy_payload_for_scope(store: Any, scope: str, payload: Dict[str, Any]) -> BrainPolicy:
    """Validate a user-authored policy before it can poison active canonical state."""
    parsed_scope = Scope(scope)
    if parsed_scope.is_operator:
        return policy_from_payload(payload, base=BrainPolicy())
    operator = canonical_policy(store, "operator")
    candidate = policy_from_payload(payload, base=operator)
    assert_policy_tightens(operator, candidate, source=f"workspace policy {parsed_scope.value}")
    return candidate


def load_effective_policy(store: Any, scope: str, *, caller_override: Optional[BrainPolicy] = None) -> BrainPolicy:
    """Return the policy that must govern one concrete scope right now."""
    effective = canonical_policy(store, scope)
    if caller_override is None:
        return effective
    override = clone_policy(caller_override)
    try:
        override.validate()
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    assert_policy_tightens(effective, override, source="caller override")
    return override
