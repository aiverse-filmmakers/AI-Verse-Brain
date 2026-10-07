from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, TYPE_CHECKING

from .models import BrainObject, Scope

if TYPE_CHECKING:
    from .controller import BrainController

PURPOSE_SNAPSHOT_SCHEMA_VERSION = "1.0"

_CURRENT_INTENT_STATUSES = {"CONFIRMED", "ACTIVE", "PAUSED"}
_CURRENT_INITIATIVE_STATUSES = {"ACCEPTED", "ACTIVE", "WAITING", "BLOCKED", "STALLED", "PAUSED", "REVIEW"}
_CURRENT_GAP_STATUSES = {"ACTIVE"}

_INTENT_SEMANTIC_KIND = {
    "problem": "problem",
    "mission": "mission",
    "desired_state": "desired_outcome",
    "goal": "goal",
    "strategy": "strategy",
}


def canonical_ref(obj: BrainObject) -> Dict[str, str]:
    return {
        "owner": "ai-verse-brain",
        "scope": obj.scope.value,
        "kind": obj.kind,
        "id": obj.id,
        "version": str(obj.revision),
    }


def semantic_kind(obj: BrainObject) -> Optional[str]:
    if obj.kind == "intent":
        return _INTENT_SEMANTIC_KIND.get(str(obj.payload.get("subtype", "")))
    if obj.kind == "gap":
        return "challenge"
    if obj.kind == "initiative":
        return "initiative"
    return None


def _object_view(obj: BrainObject) -> Dict[str, Any]:
    return {
        "id": obj.id,
        "kind": obj.kind,
        "semantic_kind": semantic_kind(obj),
        "scope": obj.scope.value,
        "status": obj.status,
        "revision": obj.revision,
        "created_at": obj.created_at,
        "updated_at": obj.updated_at,
        "canonical_ref": canonical_ref(obj),
        "source_refs": list(obj.source_refs),
        "evidence_refs": [item.to_dict() for item in obj.evidence_refs],
        "payload": dict(obj.payload),
    }


def _views(items: Iterable[BrainObject]) -> List[Dict[str, Any]]:
    return [_object_view(item) for item in sorted(items, key=lambda item: (item.kind, item.id))]


def _edge(source: BrainObject, relation: str, target: BrainObject) -> Dict[str, Any]:
    return {
        "from_ref": canonical_ref(source),
        "from_kind": semantic_kind(source),
        "relation": relation,
        "to_ref": canonical_ref(target),
        "to_kind": semantic_kind(target),
        "source_refs": [canonical_ref(source)],
    }


def _relationships(intents: List[BrainObject], gaps: List[BrainObject], initiatives: List[BrainObject]) -> tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    current = {item.id: item for item in [*intents, *gaps, *initiatives]}
    edges: List[Dict[str, Any]] = []
    rejected: List[Dict[str, str]] = []

    def resolve(source: BrainObject, relation: str, target_id: object, allowed_target_kinds: set[str]) -> None:
        target_key = str(target_id)
        target = current.get(target_key)
        if target is None:
            rejected.append({"source_id": source.id, "relation": relation, "target_id": target_key, "reason": "target_not_current_or_missing"})
            return
        target_kind = semantic_kind(target)
        if target_kind not in allowed_target_kinds:
            rejected.append({"source_id": source.id, "relation": relation, "target_id": target.id, "reason": "target_kind_invalid"})
            return
        edges.append(_edge(source, relation, target))

    for initiative in initiatives:
        for target_id in initiative.payload.get("serves", []):
            resolve(initiative, "serves", target_id, {"mission", "desired_outcome", "goal"})
        for gap_id in initiative.payload.get("gap_refs", []):
            resolve(initiative, "addresses", gap_id, {"challenge"})

    for gap in gaps:
        for desired_id in gap.payload.get("desired_state_refs", []):
            resolve(gap, "blocks", desired_id, {"desired_outcome", "goal", "strategy", "initiative"})

    edges.sort(key=lambda item: (
        item["from_ref"]["owner"], item["from_ref"]["scope"], item["from_ref"]["kind"], item["from_ref"]["id"],
        item["relation"], item["to_ref"]["owner"], item["to_ref"]["scope"], item["to_ref"]["kind"], item["to_ref"]["id"],
    ))
    rejected.sort(key=lambda item: (item["source_id"], item["relation"], item["target_id"], item["reason"]))
    return edges, rejected


def build_purpose_snapshot(controller: "BrainController", scope: str) -> Dict[str, Any]:
    """Build the read-only Brain strategic projection used by Purpose Context.

    Brain exposes strategic truth only while Brain is the active direction owner for the
    requested scope. When OS owns direction, this API never republishes staged or stale Brain
    intent as current strategy.
    """
    Scope(scope)
    direction_owner = controller.direction_owner(scope)
    if direction_owner != "brain":
        return {
            "schema_version": PURPOSE_SNAPSHOT_SCHEMA_VERSION,
            "scope": scope,
            "direction_owner": direction_owner,
            "status": "unavailable",
            "reason": "direction_owned_by_os",
            "strategic_objects": {"intents": [], "gaps": [], "initiatives": []},
            "relationships": [],
            "relationship_rejections": [],
        }

    intents = controller.store.list("intent", scope, _CURRENT_INTENT_STATUSES)
    gaps = controller.store.list("gap", scope, _CURRENT_GAP_STATUSES)
    initiatives = controller.store.list("initiative", scope, _CURRENT_INITIATIVE_STATUSES)
    relationships, relationship_rejections = _relationships(intents, gaps, initiatives)

    return {
        "schema_version": PURPOSE_SNAPSHOT_SCHEMA_VERSION,
        "scope": scope,
        "direction_owner": "brain",
        "status": "ok",
        "strategic_objects": {
            "intents": _views(intents),
            "gaps": _views(gaps),
            "initiatives": _views(initiatives),
        },
        "relationships": relationships,
        "relationship_rejections": relationship_rejections,
    }
