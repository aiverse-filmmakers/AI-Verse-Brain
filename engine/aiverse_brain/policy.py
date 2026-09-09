from dataclasses import dataclass, field
from enum import IntEnum
from typing import Dict

from .errors import PermissionDenied


class ProactivityLevel(IntEnum):
    P0_REACTIVE = 0
    P1_OBSERVANT = 1
    P2_ADVISORY = 2
    P3_ASSISTIVE = 3
    P4_DELEGATED = 4


ACTION_CLASSES = (
    "read_local", "read_connected", "write_local_reversible", "modify_canonical_state",
    "external_write_reversible", "send_message", "publish_publicly", "spend_money",
    "create_commit_or_pr", "merge_or_deploy", "delete_data", "change_permissions",
    "security_sensitive", "high_stakes_domain_action",
)

DECISIONS = {"deny", "ask_every_time", "allow_within_scope", "allow_within_budget", "allow_if_reversible"}

DEFAULT_ACTION_POLICY: Dict[str, str] = {
    "read_local": "allow_within_scope",
    "read_connected": "ask_every_time",
    "write_local_reversible": "ask_every_time",
    "modify_canonical_state": "ask_every_time",
    "external_write_reversible": "ask_every_time",
    "send_message": "ask_every_time",
    "publish_publicly": "ask_every_time",
    "spend_money": "deny",
    "create_commit_or_pr": "ask_every_time",
    "merge_or_deploy": "ask_every_time",
    "delete_data": "ask_every_time",
    "change_permissions": "deny",
    "security_sensitive": "deny",
    "high_stakes_domain_action": "ask_every_time",
}


@dataclass
class AttentionPolicy:
    max_active_initiatives: int = 3
    max_proactive_items_per_session: int = 3
    max_interruptions_per_day: int = 2
    minimum_interrupt_score: float = 0.82
    minimum_surface_score: float = 0.62
    dismissal_cooldown_hours: int = 168
    notification_cooldown_hours: int = 24


@dataclass
class ResourcePolicy:
    max_background_ticks_per_day: int = 4
    max_deep_reviews_per_week: int = 2
    max_eval_runs_per_strategy_candidate: int = 8
    max_objective_attempts: int = 8
    max_parallel_objectives: int = 2
    max_non_progressing_attempts_before_stall: int = 3


@dataclass
class EvolutionPolicy:
    allow_e1_auto_promotion: bool = True
    e1_min_evaluations: int = 1
    e2_min_evaluations: int = 2
    e2_requires_user_approval: bool = True


@dataclass
class BrainPolicy:
    proactivity: ProactivityLevel = ProactivityLevel.P2_ADVISORY
    action_policy: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_ACTION_POLICY))
    attention: AttentionPolicy = field(default_factory=AttentionPolicy)
    resources: ResourcePolicy = field(default_factory=ResourcePolicy)
    evolution: EvolutionPolicy = field(default_factory=EvolutionPolicy)

    def validate(self) -> None:
        try:
            ProactivityLevel(self.proactivity)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid proactivity level: {self.proactivity!r}") from exc
        for action, decision in self.action_policy.items():
            if action not in ACTION_CLASSES:
                raise ValueError(f"unknown action class: {action}")
            if decision not in DECISIONS:
                raise ValueError(f"unknown permission decision: {decision}")
        if self.attention.max_active_initiatives < 1:
            raise ValueError("max_active_initiatives must be >= 1")
        if self.attention.max_proactive_items_per_session < 0 or self.attention.max_interruptions_per_day < 0:
            raise ValueError("attention delivery caps cannot be negative")
        for name in ("minimum_interrupt_score", "minimum_surface_score"):
            value = getattr(self.attention, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be normalized to [0,1]")
        if self.attention.minimum_interrupt_score < self.attention.minimum_surface_score:
            raise ValueError("minimum_interrupt_score must be >= minimum_surface_score")
        if self.attention.dismissal_cooldown_hours < 0 or self.attention.notification_cooldown_hours < 0:
            raise ValueError("attention cooldowns cannot be negative")
        for name, value in self.resources.__dict__.items():
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"{name} must be an integer >= 1")
        if self.evolution.e1_min_evaluations < 1 or self.evolution.e2_min_evaluations < 1:
            raise ValueError("evolution evaluation minimums must be >= 1")
        if self.evolution.e2_min_evaluations < self.evolution.e1_min_evaluations:
            raise ValueError("E2 evaluation minimum cannot be weaker than E1")

    def action_decision(self, action_class: str) -> str:
        if action_class not in ACTION_CLASSES:
            raise PermissionDenied(f"unknown action class: {action_class}")
        return self.action_policy.get(action_class, "deny")

    def assert_pre_authorized(self, action_class: str, *, in_scope: bool, within_budget: bool, reversible: bool) -> None:
        decision = self.action_decision(action_class)
        if decision == "deny" or decision == "ask_every_time":
            raise PermissionDenied(f"action requires approval or is denied: {action_class} ({decision})")
        if decision == "allow_within_scope" and not in_scope:
            raise PermissionDenied("action is outside authorized scope")
        if decision == "allow_within_budget" and not within_budget:
            raise PermissionDenied("action exceeds authorized budget")
        if decision == "allow_if_reversible" and not reversible:
            raise PermissionDenied("action is not reversible")
