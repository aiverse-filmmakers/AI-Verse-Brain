from __future__ import annotations

"""Public Skills receipt bridge.

The original v2 contract parser/translator lives in ``skills_receipt_legacy``.
This wrapper keeps that validated contract intact and hardens objective
application so omitted receipt criteria become explicit insufficient-evidence
verdicts instead of an empty evaluation record.
"""

from typing import Any, Dict, List, Mapping

from . import skills_receipt_legacy as _legacy
from .skills_receipt_legacy import *  # noqa: F401,F403
from .errors import ValidationError
from .evaluator import CriterionVerdict, EvaluationResult
from .models import BrainObject


def evaluation_from_receipt(
    receipt: Mapping[str, Any],
    request: Any,
    identity: SkillsExecutionIdentity,
    objective: BrainObject,
) -> EvaluationResult:
    """Translate receipt evidence and explicitly materialize missing criteria.

    Execution success is not verification.  A Skills receipt may legitimately
    carry no criterion evidence; Brain records that absence as
    ``insufficient_evidence`` for every omitted objective criterion so the
    existing evaluator receives a complete, durable verdict set.
    """

    data = _legacy.validate_skills_receipt(receipt, request, identity)
    if objective.kind != "objective":
        raise ValidationError("Skills receipt verification target must be a Brain objective")
    if objective.scope.value != request.scope.value:
        raise ValidationError("Skills receipt objective scope does not match the bound action scope")

    criteria = objective.payload.get("criteria", [])
    if not isinstance(criteria, list):
        raise ValidationError("Brain objective criteria must be an array")

    criterion_ids: List[str] = []
    seen_objective = set()
    for index, item in enumerate(criteria):
        if not isinstance(item, Mapping):
            raise ValidationError(f"Brain objective criterion {index} must be an object")
        criterion_id = item.get("id")
        if not isinstance(criterion_id, str) or not criterion_id:
            raise ValidationError(f"Brain objective criterion {index} is missing id")
        if criterion_id in seen_objective:
            raise ValidationError(f"Brain objective has duplicate criterion id: {criterion_id}")
        seen_objective.add(criterion_id)
        criterion_ids.append(criterion_id)

    trace_id = str(data["trace_id"])
    provided: Dict[str, CriterionVerdict] = {}
    for index, raw in enumerate(data["verification"]):
        verdict = _legacy._object(raw, f"Skills receipt.verification[{index}]")
        criterion_id = str(verdict["criterion_id"])
        if criterion_id not in seen_objective:
            raise ValidationError(f"Skills receipt references unknown Brain criterion: {criterion_id}")
        evidence = [
            _legacy._evidence_ref(
                _legacy._object(item, f"Skills receipt.verification[{index}].evidence"),
                trace_id=trace_id,
                bound_scope=request.scope.value,
                label=f"Skills receipt.verification[{index}].evidence",
            )
            for item in verdict["evidence"]
        ]
        provided[criterion_id] = CriterionVerdict(
            criterion_id=criterion_id,
            status=str(verdict["status"]),
            evidence_refs=evidence,
            rationale=verdict.get("rationale"),
        )

    verdicts: List[CriterionVerdict] = []
    for criterion_id in criterion_ids:
        verdict = provided.get(criterion_id)
        if verdict is None:
            verdict = CriterionVerdict(
                criterion_id=criterion_id,
                status="insufficient_evidence",
                evidence_refs=[],
                rationale="Skills receipt supplied no evidence for this Brain objective criterion.",
            )
        verdicts.append(verdict)

    context = data["verification_context"]
    floor = objective.payload.get("verification_level", "V0")
    if floor not in {"V0", "V1", "V2", "V3"}:
        raise ValidationError(f"invalid Brain objective verification_level: {floor}")

    result = EvaluationResult(
        target_ref=objective.id,
        verification_level=str(floor),
        independence=_legacy._INDEPENDENCE[str(context["independence"])],
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
    """Build complete criterion verdicts, then delegate closure to EvaluationService."""

    objective = controller.store.load("objective", scope, objective_id)
    result = evaluation_from_receipt(receipt, request, identity, objective)
    return controller.evaluator.apply_to_objective(scope, objective_id, result, actor=actor)
