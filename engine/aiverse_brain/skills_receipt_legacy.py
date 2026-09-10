from __future__ import annotations

"""Fail-closed bridge from AI-Verse Skills receipt v2 into Brain semantics.

Execution accounting and objective verification are deliberately separate:
``translate_action_receipt`` produces a host response for ``ActionExecutor``;
``evaluation_from_receipt`` produces a Brain ``EvaluationResult`` whose final
application is still owned by ``EvaluationService``.
"""

from dataclasses import dataclass
import re
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple

from .errors import ValidationError
from .evaluator import CriterionVerdict, EvaluationResult, Independence
from .models import BrainObject, EvidenceRef

CONTRACT_ID = "aiverse-execution-receipt-v2"
PROVIDER_ID = "aiverse-skills"
PACKAGE_DIGEST_ALGORITHM = "aiverse-package-sha256-v1"

_STATUSES = {"success", "partial", "blocked", "failed", "aborted"}
_EFFECT_STATES = {"occurred", "not_occurred", "uncertain"}
_VERDICT_STATUSES = {"unverified", "passed", "failed", "insufficient_evidence", "not_applicable"}
_INDEPENDENCE = {
    "same_context": Independence.SAME_CONTEXT,
    "fresh_context": Independence.FRESH_CONTEXT,
    "independent_model": Independence.INDEPENDENT_MODEL,
    "external_authoritative": Independence.EXTERNAL_AUTHORITATIVE,
}
_INDEPENDENCE_RANK = {
    "same_context": 0,
    "fresh_context": 1,
    "independent_model": 2,
    "external_authoritative": 3,
}
_SOURCE_INDEPENDENCE = {
    "skill_runtime": {"same_context"},
    "ai_verse_os": {"same_context", "fresh_context"},
    "user": {"same_context"},
    "external_authority": {"external_authoritative"},
    "independent_evaluator": {"fresh_context", "independent_model"},
}
_EVIDENCE_CLASS: Dict[Tuple[str, str], str] = {
    ("observation", "skill_runtime"): "SINGLE_OBSERVATION",
    ("observation", "ai_verse_os"): "SINGLE_OBSERVATION",
    ("measurement", "ai_verse_os"): "DIRECT_MEASUREMENT",
    ("canonical_state", "ai_verse_os"): "CANONICAL_STATE",
    ("user_confirmation", "user"): "USER_CONFIRMATION",
    ("authoritative_external", "external_authority"): "AUTHORITATIVE_EXTERNAL",
    ("independent_evaluation", "independent_evaluator"): "INDEPENDENT_EVALUATION",
}
_HEX64 = re.compile(r"^[a-f0-9]{64}$")
_CAPABILITY = re.compile(r"^aiverse-skills:[a-z0-9][a-z0-9-]*$")
_GENERATION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,191}$")

_TOP_FIELDS = {
    "contract", "receipt_id", "status", "summary", "binding", "effect",
    "verification_context", "verification", "artifacts", "warnings",
    "remaining_uncertainty", "trace_id",
}
_REQUIRED_TOP = _TOP_FIELDS - {"artifacts"}
_BINDING_FIELDS = {
    "request_fingerprint", "scope", "action_class", "operation", "provider_id",
    "capability_id", "generation_id", "package_digest",
}
_EFFECT_FIELDS = {"state", "source_kind", "source_ref", "independence", "observed_at", "details"}
_CONTEXT_FIELDS = {"evaluator_id", "independence", "builder_context_id", "evaluator_context_id"}
_VERDICT_FIELDS = {"criterion_id", "status", "evidence", "rationale"}
_EVIDENCE_FIELDS = {
    "ref", "kind", "source_kind", "source_ref", "independence", "claim",
    "observed_at", "expires_at", "scope", "integrity",
}


@dataclass(frozen=True)
class SkillsExecutionIdentity:
    capability_id: str
    generation_id: str
    package_digest_sha256: str
    provider_id: str = PROVIDER_ID

    def validate(self) -> None:
        if self.provider_id != PROVIDER_ID:
            raise ValidationError(f"Skills provider_id must be {PROVIDER_ID}")
        if not isinstance(self.capability_id, str) or not _CAPABILITY.fullmatch(self.capability_id):
            raise ValidationError("Skills capability_id must be a qualified aiverse-skills id")
        if not isinstance(self.generation_id, str) or not _GENERATION.fullmatch(self.generation_id):
            raise ValidationError("Skills generation_id is invalid")
        if not isinstance(self.package_digest_sha256, str) or not _HEX64.fullmatch(self.package_digest_sha256):
            raise ValidationError("Skills package digest must be 64 lowercase hex characters")

    def to_binding_fragment(self) -> Dict[str, Any]:
        self.validate()
        return {
            "provider_id": self.provider_id,
            "capability_id": self.capability_id,
            "generation_id": self.generation_id,
            "package_digest": {
                "algorithm": PACKAGE_DIGEST_ALGORITHM,
                "value": self.package_digest_sha256,
            },
        }


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValidationError(f"{label} must be an object")
    return value


def _exact_fields(value: Mapping[str, Any], allowed: Set[str], required: Set[str], label: str) -> None:
    unknown = set(value) - allowed
    missing = required - set(value)
    if unknown:
        raise ValidationError(f"{label} has unknown fields: {', '.join(sorted(unknown))}")
    if missing:
        raise ValidationError(f"{label} is missing fields: {', '.join(sorted(missing))}")


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{label} must be a non-empty string")
    return value.strip()


def _validate_source(source_kind: Any, independence: Any, label: str) -> Tuple[str, str]:
    source = _text(source_kind, f"{label}.source_kind")
    level = _text(independence, f"{label}.independence")
    allowed = _SOURCE_INDEPENDENCE.get(source)
    if allowed is None:
        raise ValidationError(f"unknown {label}.source_kind: {source}")
    if level not in allowed:
        raise ValidationError(f"{label} source {source} cannot claim independence {level}")
    return source, level


def _validate_binding(receipt: Mapping[str, Any], request: Any, identity: SkillsExecutionIdentity) -> Mapping[str, Any]:
    identity.validate()
    binding = _object(receipt.get("binding"), "receipt.binding")
    _exact_fields(binding, _BINDING_FIELDS, _BINDING_FIELDS, "receipt.binding")

    expected = {
        "request_fingerprint": request.fingerprint(),
        "scope": request.scope.value,
        "action_class": request.action_class,
        "operation": request.operation,
        **identity.to_binding_fragment(),
    }
    for key, expected_value in expected.items():
        if binding.get(key) != expected_value:
            raise ValidationError(f"Skills receipt binding mismatch for {key}")
    return binding


def _validate_context(context: Mapping[str, Any]) -> None:
    _exact_fields(context, _CONTEXT_FIELDS, {"evaluator_id", "independence"}, "receipt.verification_context")
    _text(context.get("evaluator_id"), "receipt.verification_context.evaluator_id")
    independence = _text(context.get("independence"), "receipt.verification_context.independence")
    if independence not in _INDEPENDENCE:
        raise ValidationError(f"unknown verification independence: {independence}")
    builder = context.get("builder_context_id")
    evaluator = context.get("evaluator_context_id")
    if independence == "fresh_context":
        builder = _text(builder, "receipt.verification_context.builder_context_id")
        evaluator = _text(evaluator, "receipt.verification_context.evaluator_context_id")
        if builder == evaluator:
            raise ValidationError("fresh-context receipt verification requires distinct builder and evaluator contexts")
    else:
        if builder is not None:
            _text(builder, "receipt.verification_context.builder_context_id")
        if evaluator is not None:
            _text(evaluator, "receipt.verification_context.evaluator_context_id")


def _evidence_ref(entry: Mapping[str, Any], *, trace_id: str, bound_scope: str, label: str) -> EvidenceRef:
    _exact_fields(entry, _EVIDENCE_FIELDS, {"ref", "kind", "source_kind", "source_ref", "independence"}, label)
    ref = _text(entry.get("ref"), f"{label}.ref")
    if ref == trace_id:
        raise ValidationError("Skills trace_id is correlation metadata and cannot be criterion evidence")
    kind = _text(entry.get("kind"), f"{label}.kind")
    source, independence = _validate_source(entry.get("source_kind"), entry.get("independence"), label)
    source_ref = _text(entry.get("source_ref"), f"{label}.source_ref")
    evidence_class = _EVIDENCE_CLASS.get((kind, source))
    if evidence_class is None:
        raise ValidationError(f"unsupported Skills evidence provenance for {kind}: {source}")
    evidence_scope = entry.get("scope")
    if evidence_scope is not None and evidence_scope != bound_scope:
        raise ValidationError("Skills receipt evidence scope does not match the bound action scope")

    return EvidenceRef(
        ref=ref,
        evidence_class=evidence_class,
        claim=entry.get("claim"),
        observed_at=entry.get("observed_at"),
        expires_at=entry.get("expires_at"),
        scope=bound_scope,
        integrity=entry.get("integrity"),
        source_kind=source,
        source_ref=source_ref,
        independence=independence,
    )


def validate_skills_receipt(receipt: Mapping[str, Any], request: Any, identity: SkillsExecutionIdentity) -> Dict[str, Any]:
    """Validate receipt v2 independently of the Skills implementation."""

    data = _object(receipt, "Skills receipt")
    _exact_fields(data, _TOP_FIELDS, _REQUIRED_TOP, "Skills receipt")
    if data.get("contract") != CONTRACT_ID:
        raise ValidationError(f"Skills receipt contract must be {CONTRACT_ID}")
    receipt_id = _text(data.get("receipt_id"), "Skills receipt.receipt_id")
    trace_id = _text(data.get("trace_id"), "Skills receipt.trace_id")
    if receipt_id == trace_id:
        raise ValidationError("Skills receipt_id and trace_id must be distinct; trace_id is not proof")
    status = _text(data.get("status"), "Skills receipt.status")
    if status not in _STATUSES:
        raise ValidationError(f"unknown Skills receipt status: {status}")
    _text(data.get("summary"), "Skills receipt.summary")
    for key in ("warnings", "remaining_uncertainty"):
        value = data.get(key)
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise ValidationError(f"Skills receipt.{key} must be an array of strings")
    if "artifacts" in data and not isinstance(data["artifacts"], list):
        raise ValidationError("Skills receipt.artifacts must be an array")

    binding = _validate_binding(data, request, identity)

    effect = _object(data.get("effect"), "Skills receipt.effect")
    _exact_fields(effect, _EFFECT_FIELDS, {"state", "source_kind", "source_ref", "independence"}, "Skills receipt.effect")
    effect_state = _text(effect.get("state"), "Skills receipt.effect.state")
    if effect_state not in _EFFECT_STATES:
        raise ValidationError(f"unknown Skills effect state: {effect_state}")
    effect_source, _ = _validate_source(effect.get("source_kind"), effect.get("independence"), "Skills receipt.effect")
    _text(effect.get("source_ref"), "Skills receipt.effect.source_ref")
    if "details" in effect and not isinstance(effect["details"], Mapping):
        raise ValidationError("Skills receipt.effect.details must be an object")

    context = _object(data.get("verification_context"), "Skills receipt.verification_context")
    _validate_context(context)

    verification = data.get("verification")
    if not isinstance(verification, list):
        raise ValidationError("Skills receipt.verification must be an array")
    seen: Set[str] = set()
    passed_independence: Dict[str, List[str]] = {}
    for index, raw in enumerate(verification):
        label = f"Skills receipt.verification[{index}]"
        verdict = _object(raw, label)
        _exact_fields(verdict, _VERDICT_FIELDS, {"criterion_id", "status", "evidence"}, label)
        criterion_id = _text(verdict.get("criterion_id"), f"{label}.criterion_id")
        if criterion_id in seen:
            raise ValidationError(f"duplicate Skills receipt criterion_id: {criterion_id}")
        seen.add(criterion_id)
        verdict_status = _text(verdict.get("status"), f"{label}.status")
        if verdict_status not in _VERDICT_STATUSES:
            raise ValidationError(f"unknown Skills criterion status: {verdict_status}")
        evidence = verdict.get("evidence")
        if not isinstance(evidence, list):
            raise ValidationError(f"{label}.evidence must be an array")
        if verdict_status == "passed" and not evidence:
            raise ValidationError(f"passed Skills criterion {criterion_id} requires evidence")
        levels: List[str] = []
        for evidence_index, raw_evidence in enumerate(evidence):
            evidence_label = f"{label}.evidence[{evidence_index}]"
            entry = _object(raw_evidence, evidence_label)
            mapped = _evidence_ref(entry, trace_id=trace_id, bound_scope=str(binding["scope"]), label=evidence_label)
            if mapped.independence is not None:
                levels.append(mapped.independence)
        if verdict_status == "passed":
            passed_independence[criterion_id] = levels

    declared_independence = str(context["independence"])
    required_rank = _INDEPENDENCE_RANK[declared_independence]
    if required_rank > 0:
        for criterion_id, levels in passed_independence.items():
            if not any(_INDEPENDENCE_RANK[level] >= required_rank for level in levels):
                raise ValidationError(
                    f"passed criterion {criterion_id} does not support declared verification independence {declared_independence}"
                )

    if status == "success" and request.is_side_effect:
        if effect_state != "occurred":
            raise ValidationError("successful Skills side effect must report effect.state=occurred")
        if effect_source != "ai_verse_os":
            raise ValidationError("successful Skills side effect requires AI-Verse OS effect verification")
    if status == "success" and not request.is_side_effect and effect_state != "not_occurred":
        raise ValidationError("successful read-only Skills action must report effect.state=not_occurred")

    return dict(data)


def translate_action_receipt(receipt: Mapping[str, Any], request: Any, identity: SkillsExecutionIdentity) -> Dict[str, Any]:
    """Translate Skills status/effect certainty to the Brain host-response contract."""

    data = validate_skills_receipt(receipt, request, identity)
    status = str(data["status"])
    effect_state = str(data["effect"]["state"])

    if status == "success":
        brain_status = "succeeded"
    elif effect_state == "not_occurred":
        brain_status = "failed"
    else:
        brain_status = "uncertain"

    effect_occurred: Optional[bool]
    if effect_state == "occurred":
        effect_occurred = True
    elif effect_state == "not_occurred":
        effect_occurred = False
    else:
        effect_occurred = None

    binding = dict(data["binding"])
    result = {
        "skills_status": status,
        "summary": data["summary"],
        "effect_state": effect_state,
        "provider_id": binding["provider_id"],
        "capability_id": binding["capability_id"],
        "generation_id": binding["generation_id"],
        "package_digest": dict(binding["package_digest"]),
        "trace_id": data["trace_id"],
        "verification_criteria": len(data["verification"]),
    }
    return {
        "status": brain_status,
        "receipt_id": data["receipt_id"],
        "effect_occurred": effect_occurred,
        "execution_binding": binding,
        "result": result,
    }


def evaluation_from_receipt(
    receipt: Mapping[str, Any],
    request: Any,
    identity: SkillsExecutionIdentity,
    objective: BrainObject,
) -> EvaluationResult:
    """Translate criterion evidence; never mutate or close the objective here."""

    data = validate_skills_receipt(receipt, request, identity)
    if objective.kind != "objective":
        raise ValidationError("Skills receipt verification target must be a Brain objective")
    if objective.scope.value != request.scope.value:
        raise ValidationError("Skills receipt objective scope does not match the bound action scope")

    criteria = objective.payload.get("criteria", [])
    if not isinstance(criteria, list):
        raise ValidationError("Brain objective criteria must be an array")
    known_ids = {item.get("id") for item in criteria if isinstance(item, Mapping)}

    trace_id = str(data["trace_id"])
    verdicts: List[CriterionVerdict] = []
    for index, raw in enumerate(data["verification"]):
        verdict = _object(raw, f"Skills receipt.verification[{index}]")
        criterion_id = str(verdict["criterion_id"])
        if criterion_id not in known_ids:
            raise ValidationError(f"Skills receipt references unknown Brain criterion: {criterion_id}")
        evidence = [
            _evidence_ref(
                _object(item, f"Skills receipt.verification[{index}].evidence"),
                trace_id=trace_id,
                bound_scope=request.scope.value,
                label=f"Skills receipt.verification[{index}].evidence",
            )
            for item in verdict["evidence"]
        ]
        verdicts.append(CriterionVerdict(
            criterion_id=criterion_id,
            status=str(verdict["status"]),
            evidence_refs=evidence,
            rationale=verdict.get("rationale"),
        ))

    context = data["verification_context"]
    floor = objective.payload.get("verification_level", "V0")
    if floor not in {"V0", "V1", "V2", "V3"}:
        raise ValidationError(f"invalid Brain objective verification_level: {floor}")
    result = EvaluationResult(
        target_ref=objective.id,
        verification_level=str(floor),
        independence=_INDEPENDENCE[str(context["independence"])],
        verdicts=verdicts,
        evaluator_id=str(context["evaluator_id"]),
        builder_context_id=context.get("builder_context_id"),
        evaluator_context_id=context.get("evaluator_context_id"),
        notes=(
            f"Skills receipt {data['receipt_id']} from {identity.capability_id} "
            f"generation {identity.generation_id}; execution success is not objective completion"
        ),
    )
    result.validate()
    return result


def apply_receipt_to_objective(
    controller: Any,
    *,
    scope: str,
    objective_id: str,
    receipt: Mapping[str, Any],
    request: Any,
    identity: SkillsExecutionIdentity,
    actor: str = "skills-receipt-evaluator",
) -> BrainObject:
    """Brain-owned convenience path: build evidence, then use EvaluationService."""

    objective = controller.store.load("objective", scope, objective_id)
    result = evaluation_from_receipt(receipt, request, identity, objective)
    return controller.evaluator.apply_to_objective(scope, objective_id, result, actor=actor)
