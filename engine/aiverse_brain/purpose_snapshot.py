from __future__ import annotations

from typing import Any, Dict, Iterable, List, TYPE_CHECKING

from .models import BrainObject, Scope

if TYPE_CHECKING:
    from .controller import BrainController

PURPOSE_SNAPSHOT_SCHEMA_VERSION = "1.0"

_CURRENT_INTENT_STATUSES = {"CONFIRMED", "ACTIVE", "PAUSED"}
_CURRENT_INITIATIVE_STATUSES = {"ACCEPTED", "ACTIVE", "WAITING", "BLOCKED", "STALLED", "PAUSED", "REVIEW"}
_CURRENT_GAP_STATUSES = {"ACTIVE"}


def canonical_ref(obj: BrainObject) -> Dict[str, str]:
    return {
        "owner": "ai-verse-brain",
        "scope": obj.scope.value,
        "kind": obj.kind,
        "id": obj.id,
        "version": str(obj.revision),
    }


def _object_view(obj: BrainObject) -> Dict[str, Any]:
    """Return a stable public strategic-object view without storage details."""
    return {
        "id": obj.id,
        "kind": obj.kind,
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


def build_purpose_snapshot(controller: "BrainController", scope: str) -> Dict[str, Any]:
    """Build the Brain-owned strategic read projection for Purpose Context.

    Read-only and bounded to confirmed/current strategic objects. Every public object view
    carries its exact Brain canonical ref plus preserved source/evidence references.
    """
    Scope(scope)
    intents = controller.store.list("intent", scope, _CURRENT_INTENT_STATUSES)
    gaps = controller.store.list("gap", scope, _CURRENT_GAP_STATUSES)
    initiatives = controller.store.list("initiative", scope, _CURRENT_INITIATIVE_STATUSES)

    return {
        "schema_version": PURPOSE_SNAPSHOT_SCHEMA_VERSION,
        "scope": scope,
        "status": "ok",
        "strategic_objects": {
            "intents": _views(intents),
            "gaps": _views(gaps),
            "initiatives": _views(initiatives),
        },
    }
