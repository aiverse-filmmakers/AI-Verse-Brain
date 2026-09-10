from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Dict, List, Optional

from .authority import AuthorityTier
from .direction_ownership import direction_owner_for, strategic_answers_present
from .errors import ValidationError
from .models import BrainObject

_ALLOWED_ANSWER_KEYS = {
    "desired_state", "success_definition", "goals", "boundaries", "constraints", "practices",
}


def _normalized(value: str) -> str:
    return " ".join(re.findall(r"[\w'-]+", value.casefold(), flags=re.UNICODE))


def _require_text(value: Any, key: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"onboarding {key} must be a non-empty string")
    return value.strip()


def _string_list(value: Any, key: str) -> List[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValidationError(f"onboarding {key} must be a list of strings")
    result: List[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValidationError(f"onboarding {key} entries must be non-empty strings")
        result.append(item.strip())
    return result


@dataclass(frozen=True)
class OnboardingQuestion:
    key: str
    prompt: str
    required: bool
    writes: str
    why: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "prompt": self.prompt,
            "required": self.required,
            "writes": self.writes,
            "why": self.why,
        }


@dataclass(frozen=True)
class OnboardingPlan:
    scope: str
    complete_enough_to_orient: bool
    questions: List[OnboardingQuestion] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    direction_owner: str = "brain"
    strategic_write_enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scope": self.scope,
            "complete_enough_to_orient": self.complete_enough_to_orient,
            "direction_owner": self.direction_owner,
            "strategic_write_enabled": self.strategic_write_enabled,
            "questions": [item.to_dict() for item in self.questions],
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class OnboardingResult:
    scope: str
    created_refs: List[str]
    existing_refs: List[str]
    plan: OnboardingPlan

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scope": self.scope,
            "created_refs": list(self.created_refs),
            "existing_refs": list(self.existing_refs),
            "plan": self.plan.to_dict(),
        }


class OnboardingService:
    """Captures Brain-owned intent/practice state from explicit user answers.

    In native AI-Verse OS mode, strategic intent is writable here only after an explicit
    durable handover makes Brain the direction owner for the scope. Current state, profile
    facts, history, knowledge, connections, and capabilities remain host/OS-owned.
    """

    def __init__(self, controller: Any):
        self.controller = controller

    def _owner(self, scope: str) -> str:
        return direction_owner_for(self.controller, scope)

    def _intents(self, scope: str, subtype: Optional[str] = None) -> List[BrainObject]:
        items = self.controller.store.list("intent", scope, {"CONFIRMED", "ACTIVE"})
        if subtype is not None:
            items = [item for item in items if item.payload.get("subtype") == subtype]
        return items

    def _practices(self, scope: str) -> List[BrainObject]:
        return self.controller.store.list("practice", scope, {"CONFIRMED", "ACTIVE", "PAUSED"})

    def plan(self, scope: str = "operator") -> OnboardingPlan:
        owner = self._owner(scope)
        practices = self._practices(scope)
        questions: List[OnboardingQuestion] = []

        if owner == "brain":
            desired = self._intents(scope, "desired_state")
            goals = self._intents(scope, "goal")
            success = self._intents(scope, "success_definition")
            boundaries = self._intents(scope, "boundary")
            constraints = self._intents(scope, "constraint")

            if not desired:
                questions.append(OnboardingQuestion(
                    "desired_state",
                    "What meaningful future state do you want this Brain to help move toward?",
                    True,
                    "intent:desired_state",
                    "Direction requires an explicitly user-authorized destination; the Brain may not infer one into existence.",
                ))
            if not success:
                questions.append(OnboardingQuestion(
                    "success_definition",
                    "How will you know meaningful progress or success has actually happened?",
                    True,
                    "intent:success_definition",
                    "Verification needs a user-owned definition of success rather than model self-grading.",
                ))
            if not goals:
                questions.append(OnboardingQuestion(
                    "goals",
                    "What concrete outcomes matter most right now? Provide a list, or leave it empty for now.",
                    False,
                    "intent:goal",
                    "Goals connect long-horizon direction to initiatives and bounded objectives.",
                ))
            if not boundaries:
                questions.append(OnboardingQuestion(
                    "boundaries",
                    "What should the Brain never optimize away, change silently, or cross?",
                    False,
                    "intent:boundary",
                    "User boundaries outrank agent strategy and self-improvement.",
                ))
            if not constraints:
                questions.append(OnboardingQuestion(
                    "constraints",
                    "What real constraints should planning respect?",
                    False,
                    "intent:constraint",
                    "Constraints prevent attractive but unusable initiatives.",
                ))
            complete = bool(desired and success)
            notes = [
                "Brain owns strategic direction for this scope; only explicit answers become confirmed Brain intent.",
                "Current-state facts remain in the host/OS canonical context and are not duplicated by onboarding.",
                "Profile, memory, knowledge, scheduler, connections, and capabilities remain outside Brain ownership.",
            ]
        else:
            # OS is the canonical strategy owner. Brain onboarding must not create a parallel
            # desired-state/goal/boundary/constraint store. Item 15 can make host-owned
            # direction available to reasoning without changing this ownership boundary.
            complete = True
            notes = [
                "AI-Verse OS currently owns strategic direction for this scope.",
                "Brain onboarding will not ask for or persist desired state, success definitions, goals, boundaries, or constraints until explicit handover.",
                "Use `ai-verse-brain direction-owner <root> --scope <scope> --handover-to-brain` to inspect the handover plan, then apply it explicitly if desired.",
            ]

        if not practices:
            questions.append(OnboardingQuestion(
                "practices",
                "Are there ongoing standards or practices you want maintained rather than completed once?",
                False,
                "practice",
                "Practices represent ongoing desired conditions rather than terminal goals.",
            ))

        return OnboardingPlan(
            scope=scope,
            complete_enough_to_orient=complete,
            questions=questions,
            notes=notes,
            direction_owner=owner,
            strategic_write_enabled=(owner == "brain"),
        )

    def _find_intent(self, scope: str, subtype: str, statement: str) -> Optional[BrainObject]:
        target = _normalized(statement)
        for item in self._intents(scope, subtype):
            if _normalized(str(item.payload.get("statement", ""))) == target:
                return item
        return None

    def _find_practice(self, scope: str, statement: str) -> Optional[BrainObject]:
        target = _normalized(statement)
        for item in self._practices(scope):
            if _normalized(str(item.payload.get("statement", ""))) == target:
                return item
        return None

    def _ensure_intent(self, scope: str, subtype: str, statement: str) -> tuple[BrainObject, bool]:
        existing = self._find_intent(scope, subtype, statement)
        if existing:
            return existing, False
        obj = self.controller.create(
            "intent",
            scope,
            "CONFIRMED",
            {"subtype": subtype, "statement": statement},
            source=AuthorityTier.EXPLICIT_USER,
            actor="user:onboarding",
        )
        return obj, True

    def _ensure_practice(self, scope: str, statement: str) -> tuple[BrainObject, bool]:
        existing = self._find_practice(scope, statement)
        if existing:
            return existing, False
        obj = self.controller.create(
            "practice",
            scope,
            "CONFIRMED",
            {"statement": statement, "health": "UNKNOWN"},
            source=AuthorityTier.EXPLICIT_USER,
            actor="user:onboarding",
        )
        return obj, True

    def apply(self, answers: Dict[str, Any], scope: str = "operator") -> OnboardingResult:
        if not isinstance(answers, dict):
            raise ValidationError("onboarding answers must be a JSON object")
        unknown = sorted(set(answers) - _ALLOWED_ANSWER_KEYS)
        if unknown:
            raise ValidationError("unknown onboarding answer keys: " + ", ".join(unknown))

        owner = self._owner(scope)
        if owner != "brain" and strategic_answers_present(answers):
            raise ValidationError(
                f"strategic direction for {scope} is owned by AI-Verse OS; "
                "Brain onboarding cannot create a second strategic store before explicit handover"
            )

        desired_value = answers.get("desired_state")
        success_value = answers.get("success_definition")
        goals = _string_list(answers.get("goals"), "goals")
        boundaries = _string_list(answers.get("boundaries"), "boundaries")
        constraints = _string_list(answers.get("constraints"), "constraints")
        practices = _string_list(answers.get("practices"), "practices")

        desired = _require_text(desired_value, "desired_state") if desired_value is not None else None
        success = _require_text(success_value, "success_definition") if success_value is not None else None

        before = self.plan(scope)
        missing_required = {item.key for item in before.questions if item.required}
        if "desired_state" in missing_required and desired is None:
            raise ValidationError("onboarding requires desired_state before the Brain can orient")
        if "success_definition" in missing_required and success is None:
            raise ValidationError("onboarding requires success_definition before the Brain can orient")

        created: List[str] = []
        existing: List[str] = []

        def track(obj: BrainObject, was_created: bool) -> None:
            ref = f"brain:{obj.kind}:{obj.id}"
            (created if was_created else existing).append(ref)

        if desired is not None:
            track(*self._ensure_intent(scope, "desired_state", desired))
        if success is not None:
            track(*self._ensure_intent(scope, "success_definition", success))
        for statement in goals:
            track(*self._ensure_intent(scope, "goal", statement))
        for statement in boundaries:
            track(*self._ensure_intent(scope, "boundary", statement))
        for statement in constraints:
            track(*self._ensure_intent(scope, "constraint", statement))
        for statement in practices:
            track(*self._ensure_practice(scope, statement))

        return OnboardingResult(scope, created, existing, self.plan(scope))
