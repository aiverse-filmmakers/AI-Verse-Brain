"""Owner API for explicit and proposed strategic-intent capture.

The selected host must authenticate ``evidence_ref`` before assigning EXPLICIT_USER. This
service enforces Brain's authority tier and lifecycle; it is not a transcript verifier.
"""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import re
import time
from typing import Any, Dict, Iterator, List, Optional

from .authority import AuthorityTier
from .errors import LockConflict, ValidationError
from .models import BrainObject, Scope
from .runtime_lock import RuntimeKeyLock

CURRENT = {"CONFIRMED", "ACTIVE", "PAUSED"}
SUBTYPES = {
    "problem", "mission", "strategy", "desired_state", "goal",
    "boundary", "constraint", "success_definition",
}
_LOCK_WAIT_SECONDS = 5.0
_LOCK_POLL_SECONDS = 0.01


def _fingerprint(value: Dict[str, Any]) -> str:
    material = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _text(value: Any, label: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
        raise ValidationError(f"{label} must be a non-empty string of at most {limit} characters")
    return value.strip()


class IntentOwnerService:
    """Brain-owned strategic intent API; OS remains authoritative for routing and scope."""

    def __init__(self, controller: Any):
        self.controller = controller
        self.store = controller.store
        self.lock = RuntimeKeyLock(controller.layout.runtime_dir, namespace="intent-owner")

    @contextmanager
    def _guard(self, scope: str, operation_id: str) -> Iterator[None]:
        # Serialize mutations for a scope so competing operation IDs cannot both
        # supersede the same current intent after independently reading its revision.
        key = scope
        deadline = time.monotonic() + _LOCK_WAIT_SECONDS
        guard = None
        while guard is None:
            candidate = self.lock.acquire(key)
            try:
                candidate.__enter__()
            except LockConflict:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(_LOCK_POLL_SECONDS)
            else:
                guard = candidate
        try:
            yield
        finally:
            guard.__exit__(None, None, None)

    def read(self, scope: str) -> Dict[str, Any]:
        Scope(scope)
        owner = self.controller.direction_owner(scope)
        if owner != "brain":
            return {"state": "owner-required", "scope": scope, "owner": owner, "intents": []}
        intents = []
        for obj in self.store.list("intent", scope, CURRENT):
            intents.append({
                "id": obj.id,
                "scope": scope,
                "subtype": obj.payload.get("subtype"),
                "statement": obj.payload.get("statement"),
                "status": obj.status,
                "revision": obj.revision,
                "canonical_ref": f"brain:intent:{obj.id}",
                "supersedes": obj.supersedes,
                "source_refs": list(obj.source_refs),
            })
        return {"state": "ready", "scope": scope, "owner": "brain", "intents": intents}

    def capture(
        self,
        scope: str,
        *,
        subtype: str,
        statement: str,
        operation_id: str,
        evidence_ref: str,
        source: AuthorityTier,
        supersedes: Optional[str] = None,
        expected_revision: Optional[int] = None,
    ) -> Dict[str, Any]:
        Scope(scope)
        subtype = _text(subtype, "subtype", 64)
        if subtype not in SUBTYPES:
            raise ValidationError("unsupported strategic-intent subtype")
        statement = _text(statement, "statement", 2000)
        operation_id = _text(operation_id, "operation_id", 128)
        evidence_ref = _text(evidence_ref, "evidence_ref", 2048)
        if not isinstance(source, AuthorityTier) or source not in {
            AuthorityTier.EXPLICIT_USER, AuthorityTier.TEMPORARY_HYPOTHESIS
        }:
            raise ValidationError("intent capture source must be explicit user evidence or a temporary hypothesis")
        explicit_user_declaration = source == AuthorityTier.EXPLICIT_USER
        if supersedes is not None:
            supersedes = _text(supersedes, "supersedes", 128)
            if not explicit_user_declaration:
                raise ValidationError("a strategic-intent correction requires an explicit user declaration")
            if not isinstance(expected_revision, int) or isinstance(expected_revision, bool) or expected_revision < 1:
                raise ValidationError("a correction requires expected_revision >= 1")
        elif expected_revision is not None:
            raise ValidationError("expected_revision is only valid with supersedes")

        request = {
            "scope": scope,
            "subtype": subtype,
            "statement": statement,
            "evidence_ref": evidence_ref,
            "source": source.name,
            "supersedes": supersedes,
            "expected_revision": expected_revision,
        }
        request_fingerprint = _fingerprint(request)
        owner = self.controller.direction_owner(scope)
        if owner != "brain":
            return {"state": "owner-required", "scope": scope, "owner": owner, "changed": False}

        with self._guard(scope, operation_id):
            objects = self.store.list("intent", scope)
            prior_operation = next((item for item in objects
                                    if item.payload.get("intent_capture", {}).get("operation_id") == operation_id), None)
            if prior_operation:
                metadata = prior_operation.payload.get("intent_capture", {})
                if metadata.get("fingerprint") != request_fingerprint:
                    raise ValidationError("operation_id was already used with different intent content")
                return self._resume_or_return(prior_operation, request, request_fingerprint)

            if supersedes is None:
                duplicate = next((item for item in objects
                                  if item.status in CURRENT
                                  and item.payload.get("subtype") == subtype
                                  and item.payload.get("statement", "").casefold() == statement.casefold()), None)
                if duplicate:
                    return {"state": "unchanged", "scope": scope, "ref": f"brain:intent:{duplicate.id}",
                            "status": duplicate.status, "revision": duplicate.revision, "changed": False}

            prior = None
            prior_links: List[str] = []
            if supersedes is not None:
                prior = self.store.load("intent", scope, supersedes)
                if prior.payload.get("subtype") != subtype:
                    raise ValidationError("correction target must have the same strategic-intent subtype")
                if prior.status not in CURRENT | {"SUPERSEDED"}:
                    raise ValidationError("correction target is not current")
                if prior.status != "SUPERSEDED" and prior.revision != expected_revision:
                    raise ValidationError("stale correction revision; reread the current intent before retrying")
                if prior.status == "SUPERSEDED":
                    raise ValidationError("correction target was already superseded by another operation")
                prior_links = self._workspace_links(prior)

            metadata = {
                "operation_id": operation_id,
                "fingerprint": request_fingerprint,
                "explicit": explicit_user_declaration,
                "evidence_ref": evidence_ref,
                "expected_prior_revision": expected_revision,
            }
            candidate = self.controller.create(
                "intent", scope, "PROPOSED",
                {"subtype": subtype, "statement": statement, "intent_capture": metadata},
                source=source,
                actor="user:intent-capture" if explicit_user_declaration else "host:intent-capture",
                source_refs=[evidence_ref],
                supersedes=supersedes,
            )
            if not explicit_user_declaration:
                return {"state": "awaiting-confirmation", "scope": scope,
                        "ref": f"brain:intent:{candidate.id}", "status": candidate.status,
                        "revision": candidate.revision, "changed": True}
            return self._activate(candidate, prior, prior_links, evidence_ref, request, request_fingerprint, replayed=False)

    def _resume_or_return(self, candidate: BrainObject, request: Dict[str, Any], fingerprint: str) -> Dict[str, Any]:
        if request["source"] == AuthorityTier.EXPLICIT_USER.name and request["supersedes"]:
            prior = self.store.load("intent", candidate.scope.value, request["supersedes"])
            links = self._workspace_links(prior)
            if prior.status == "SUPERSEDED":
                competing = [item for item in self.store.list("intent", candidate.scope.value, CURRENT)
                             if item.id != candidate.id and item.supersedes == prior.id]
                if competing:
                    raise ValidationError("correction target was superseded by another current intent")
            return self._activate(candidate, prior, links, request["evidence_ref"], request, fingerprint, replayed=True)
        if candidate.status in {"CONFIRMED", "ACTIVE", "PAUSED"}:
            return {"state": "saved", "scope": candidate.scope.value,
                    "ref": f"brain:intent:{candidate.id}", "status": candidate.status,
                    "revision": candidate.revision, "changed": False, "replayed": True}
        if candidate.status != "PROPOSED":
            return {"state": candidate.status.lower(), "scope": candidate.scope.value,
                    "ref": f"brain:intent:{candidate.id}", "status": candidate.status,
                    "revision": candidate.revision, "changed": False, "replayed": True}
        if request["source"] != AuthorityTier.EXPLICIT_USER.name:
            return {"state": "awaiting-confirmation", "scope": candidate.scope.value,
                    "ref": f"brain:intent:{candidate.id}", "status": candidate.status,
                    "revision": candidate.revision, "changed": False, "replayed": True}
        return self._activate(candidate, None, [], request["evidence_ref"], request, fingerprint, replayed=True)

    def _activate(
        self, candidate: BrainObject, prior: Optional[BrainObject], prior_links: List[str],
        evidence_ref: str, request: Dict[str, Any], fingerprint: str, *, replayed: bool,
    ) -> Dict[str, Any]:
        scope = candidate.scope.value
        changed = False
        if prior and prior.status != "SUPERSEDED":
            if prior.revision != request["expected_revision"]:
                raise ValidationError("stale correction revision; reread the current intent before retrying")
            prior = self.controller.transition(
                "intent", scope, prior.id, "SUPERSEDED",
                source=AuthorityTier.EXPLICIT_USER, actor="user:intent-capture",
            )
            changed = True
        if candidate.status == "PROPOSED":
            candidate = self.controller.transition(
                "intent", scope, candidate.id, "CONFIRMED",
                source=AuthorityTier.EXPLICIT_USER, actor="user:intent-capture",
            )
            changed = True
        if candidate.status == "CONFIRMED":
            candidate = self.controller.transition(
                "intent", scope, candidate.id, "ACTIVE",
                source=AuthorityTier.EXPLICIT_USER, actor="user:intent-capture",
            )
            changed = True
        for workspace_scope in prior_links:
            if workspace_scope not in self._workspace_links(candidate):
                operation_id = "intent-correction-link:" + hashlib.sha256(
                    f"{candidate.id}|{workspace_scope}|{evidence_ref}".encode("utf-8")
                ).hexdigest()[:32]
                candidate = self.controller.link_workspace_intent(
                    candidate.id, workspace_scope, expected_revision=candidate.revision,
                    operation_id=operation_id, evidence_ref=evidence_ref,
                    source=AuthorityTier.EXPLICIT_USER,
                )
                changed = True
        return {"state": "saved", "scope": scope, "ref": f"brain:intent:{candidate.id}",
                "status": candidate.status, "revision": candidate.revision, "changed": changed,
                "replayed": replayed}

    @staticmethod
    def _workspace_links(obj: Optional[BrainObject]) -> List[str]:
        if obj is None:
            return []
        raw = obj.payload.get("workspace_links", [])
        if not isinstance(raw, list) or len(raw) > 32:
            raise ValidationError("intent workspace links are malformed")
        result: List[str] = []
        for link in raw:
            scope = link if isinstance(link, str) else link.get("scope") if isinstance(link, dict) else None
            if not isinstance(scope, str) or not re.fullmatch(r"workspace:[a-z0-9][a-z0-9-]{0,127}", scope):
                raise ValidationError("intent workspace link is malformed")
            if scope not in result:
                result.append(scope)
        return result
