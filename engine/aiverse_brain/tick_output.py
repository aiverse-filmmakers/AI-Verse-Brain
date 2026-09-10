from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Optional, Sequence

from .cognition import CognitionPurpose
from .host_selection import HostSelection

_VISIBLE_ITEMS = 5
_LABEL_KEYS = {
    "goal": ("statement", "desired_state", "outcome", "title", "name"),
    "practice": ("name", "statement", "description", "practice"),
    "initiative": ("title", "hypothesis", "outcome", "summary", "statement"),
    "objective": ("outcome", "title", "statement", "summary"),
    "policy": ("name", "statement", "description"),
}


def _label(kind: str, item: Mapping[str, Any]) -> Optional[str]:
    payload = item.get("payload")
    if not isinstance(payload, Mapping):
        return None
    for key in _LABEL_KEYS.get(kind, ()):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _criterion_counts(item: Mapping[str, Any]) -> Dict[str, int]:
    payload = item.get("payload")
    if not isinstance(payload, Mapping):
        return {}
    criteria = payload.get("criteria")
    if not isinstance(criteria, list):
        return {}
    counts: Dict[str, int] = {}
    for criterion in criteria:
        if not isinstance(criterion, Mapping):
            continue
        status = criterion.get("status")
        if isinstance(status, str) and status:
            counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))


def _item(kind: str, raw: Mapping[str, Any]) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "id": raw.get("id"),
        "status": raw.get("status"),
    }
    label = _label(kind, raw)
    if label is not None:
        result["label"] = label
    payload = raw.get("payload")
    if isinstance(payload, Mapping):
        if kind == "objective":
            for key in ("progress", "verification_level"):
                value = payload.get(key)
                if value is not None:
                    result[key] = value
            counts = _criterion_counts(raw)
            if counts:
                result["criteria"] = counts
        elif kind == "initiative":
            score = payload.get("score")
            if isinstance(score, (int, float)) and not isinstance(score, bool):
                result["score"] = float(score)
    return {key: value for key, value in result.items() if value is not None}


def _bucket(kind: str, items: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    ordered = sorted(
        items,
        key=lambda item: (str(item.get("updated_at", "")), str(item.get("id", ""))),
        reverse=True,
    )
    visible = ordered[:_VISIBLE_ITEMS]
    return {
        "total": len(items),
        "shown": len(visible),
        "truncated": len(items) > len(visible),
        "items": [_item(kind, item) for item in visible],
    }


def _cognition_modes(requests: Iterable[Any]) -> list[Dict[str, Any]]:
    output = []
    for request in requests:
        proposal_kinds = list(request.output_contract.get("proposal_kinds") or [])
        if request.purpose == CognitionPurpose.ORIENT and not proposal_kinds:
            mode = "deterministic_orientation"
        elif proposal_kinds:
            mode = "reasoner_proposals"
        else:
            mode = "skipped_no_proposal_contract"
        output.append({
            "purpose": request.purpose.value,
            "mode": mode,
            "proposal_kinds": proposal_kinds,
        })
    return output


def build_tick_summary(result: Any, host_selection: HostSelection, runtime: Any) -> Dict[str, Any]:
    """Build bounded, useful CLI output without asking a model to narrate orientation.

    ``BrainRuntime.run_tick`` refreshes the effective persisted policy before it
    constructs ``result.plan``. Reporting ``runtime.policy`` here therefore shows
    the exact policy posture used by this manual or scheduled tick.
    """

    orientation = result.plan.orientation
    policy = runtime.policy
    deterministic_orientation = {
        "mode": "deterministic",
        "reasoner_used": False,
        "direction_owner": runtime.controller.direction_owner(result.scope),
        "state": {
            "goals": _bucket("goal", orientation.confirmed_goals),
            "practices": _bucket("practice", orientation.active_practices),
            "initiatives": _bucket("initiative", orientation.active_initiatives),
            "objectives": _bucket("objective", orientation.current_objectives),
            "policies": _bucket("policy", orientation.hard_policies),
        },
        "effective_policy": {
            "proactivity": {
                "level": int(policy.proactivity),
                "name": policy.proactivity.name,
            },
            "max_active_initiatives": policy.attention.max_active_initiatives,
            "max_proactive_items_per_session": policy.attention.max_proactive_items_per_session,
            "max_parallel_objectives": policy.resources.max_parallel_objectives,
            "max_background_ticks_per_day": policy.resources.max_background_ticks_per_day,
        },
    }

    return {
        "ok": result.ok,
        "trigger_type": result.trigger_type,
        "scope": result.scope,
        "host": host_selection.to_dict(),
        "orientation": deterministic_orientation,
        "cognition": _cognition_modes(result.plan.cognition_requests),
        "reasoner_calls": result.reasoner_calls,
        "applied": [
            {
                "object_ref": item.object_ref,
                "proposal_kind": item.proposal_kind,
                "status": item.status,
                "notification": item.notification.value,
                "duplicate": item.duplicate,
            }
            for item in result.applied
        ],
        "applied_refs": [item.object_ref for item in result.applied],
        "surface_items": [
            {
                "object_ref": item.object_ref,
                "proposal_kind": item.proposal_kind,
                "notification": item.notification,
                "reason": item.reason,
                "attention_fingerprint": item.attention_fingerprint,
            }
            for item in result.surface_items
        ],
        "errors": [
            {
                "stage": item.stage,
                "request_id": item.request_id,
                "error_type": item.error_type,
                "message": item.message,
                "proposal_index": item.proposal_index,
            }
            for item in result.errors
        ],
    }
