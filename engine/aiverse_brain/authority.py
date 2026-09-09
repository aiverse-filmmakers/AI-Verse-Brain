from enum import IntEnum
from typing import Iterable

from .errors import AuthorityError


class AuthorityTier(IntEnum):
    HOST_HARD_CONSTRAINT = 0
    EXPLICIT_USER = 1
    CANONICAL_SCOPED_STATE = 2
    VERIFIED_EVIDENCE = 3
    CONFIRMED_DERIVED_MODEL = 4
    VALIDATED_STRATEGY = 5
    TEMPORARY_HYPOTHESIS = 6
    EXTERNAL_DATA = 7


PRIVILEGED_KINDS = {"policy"}
PRIVILEGED_INTENT_FIELDS = {
    "goal", "desired_state", "boundary", "constraint", "success_definition"
}
SELF_EVOLUTION_FORBIDDEN_FIELDS = {
    "confirmed_user_values", "confirmed_user_goals", "identity", "hard_boundaries",
    "permission_matrix", "privacy_policy", "risk_tolerance", "approval_requirements",
    "meaning_of_success", "scope_isolation", "self_improvement_privilege_tiers",
}


def may_override(incoming: AuthorityTier, existing: AuthorityTier) -> bool:
    """Higher authority has a numerically lower tier."""
    return incoming <= existing


def require_user_authority(source: AuthorityTier, reason: str) -> None:
    if source > AuthorityTier.EXPLICIT_USER:
        raise AuthorityError(f"explicit user authority required: {reason}")


def assert_goal_confirmation(source: AuthorityTier) -> None:
    require_user_authority(source, "material goal confirmation")


def assert_policy_mutation(source: AuthorityTier) -> None:
    require_user_authority(source, "policy mutation")


def assert_self_evolution_fields(fields: Iterable[str]) -> None:
    forbidden = sorted(set(fields) & SELF_EVOLUTION_FORBIDDEN_FIELDS)
    if forbidden:
        raise AuthorityError("self-improvement may not modify privileged fields: " + ", ".join(forbidden))


def assert_control_channel(source: AuthorityTier) -> None:
    """External/retrieved content is evidence, never a control channel."""
    if source >= AuthorityTier.EXTERNAL_DATA:
        raise AuthorityError("external content cannot alter Brain control state")
