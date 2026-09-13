from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Dict, Iterable, List, Optional

from .authority import AuthorityTier, require_user_authority
from .errors import AuthorityError, RevisionConflict, ValidationError
from .models import BrainObject, EvidenceRef, Scope, parse_timestamp, utc_now
from .runtime_lock import RuntimeKeyLock

PUBLIC_TO_INTERNAL = {
    "active": "ACTIVE", "paused": "PAUSED", "blocked": "BLOCKED",
    "budget_limited": "BUDGET_LIMITED", "usage_limited": "USAGE_LIMITED",
    "complete": "COMPLETE", "cleared": "CLEARED",
}
INTERNAL_TO_PUBLIC = {value: key for key, value in PUBLIC_TO_INTERNAL.items()}
TERMINAL = {"COMPLETE", "CLEARED"}
DEFAULT_MAX_TURNS = 20
DEFAULT_NO_PROGRESS_LIMIT = 3
_TRANSITION_TARGET = {
    "pause": "PAUSED", "resume": "ACTIVE", "block": "BLOCKED",
    "complete": "COMPLETE", "clear": "CLEARED",
    "budget_limit": "BUDGET_LIMITED", "usage_limit": "USAGE_LIMITED",
}


def _fingerprint(value: Dict[str, Any]) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{label} must be a non-empty string")
    return value.strip()


def _strings(value: Any, label: str) -> List[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValidationError(f"{label} must be a list")
    return [_text(item, f"{label} item") for item in value]


def _criteria(raw: Optional[Iterable[Any]]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    seen = set()
    for index, item in enumerate(list(raw or [])):
        if isinstance(item, str):
            item = {"id": f"criterion_{index + 1}", "statement": item}
        if not isinstance(item, dict):
            raise ValidationError("goal criteria entries must be strings or objects")
        cid = _text(item.get("id") or f"criterion_{index + 1}", "goal criterion id")
        if cid in seen:
            raise ValidationError(f"duplicate goal criterion id: {cid}")
        seen.add(cid)
        status = str(item.get("status", "unverified"))
        if status not in {"unverified", "passed", "failed", "insufficient_evidence", "not_applicable"}:
            raise ValidationError(f"invalid goal criterion status: {status}")
        refs = item.get("evidence_refs", [])
        if not isinstance(refs, list) or any(not isinstance(ref, str) or not ref for ref in refs):
            raise ValidationError("goal criterion evidence_refs must be a string array")
        if status == "passed" and not refs:
            raise ValidationError("passed goal criterion requires evidence_refs")
        result.append({
            "id": cid,
            "statement": _text(item.get("statement"), "goal criterion statement"),
            "status": status,
            "verification": item.get("verification"),
            "evidence_refs": list(refs),
        })
    return result


def _contract(raw: Optional[Dict[str, Any]], objective: str) -> Dict[str, Any]:
    raw = dict(raw or {})
    verification = raw.get("verification", [])
    if not isinstance(verification, list):
        raise ValidationError("completion_contract.verification must be a list")
    gates = []
    for index, gate in enumerate(verification):
        if isinstance(gate, str):
            gate = {"statement": gate}
        if not isinstance(gate, dict):
            raise ValidationError("verification gates must be strings or objects")
        item = dict(gate)
        item["id"] = _text(item.get("id") or f"gate_{index + 1}", "verification gate id")
        item["kind"] = _text(item.get("kind") or "evidence", "verification gate kind")
        item["statement"] = _text(item.get("statement") or item.get("description"), "verification gate statement")
        item["required"] = bool(item.get("required", True))
        gates.append(item)
    return {
        "outcome": _text(raw.get("outcome") or objective, "completion_contract.outcome"),
        "verification": gates,
        "constraints": _strings(raw.get("constraints"), "completion_contract.constraints"),
        "boundaries": _strings(raw.get("boundaries"), "completion_contract.boundaries"),
        "stop_when": _strings(raw.get("stop_when"), "completion_contract.stop_when"),
    }


def _budget(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    raw = dict(raw or {})
    max_turns = raw.get("max_turns", DEFAULT_MAX_TURNS)
    max_tokens = raw.get("max_tokens")
    max_cost = raw.get("max_cost")
    deadline = raw.get("deadline")
    no_progress = raw.get("no_progress_limit", DEFAULT_NO_PROGRESS_LIMIT)
    for field, value in (("max_turns", max_turns), ("max_tokens", max_tokens)):
        if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 1):
            raise ValidationError(f"budget_policy.{field} must be null or integer >= 1")
    if max_cost is not None and (
        not isinstance(max_cost, (int, float)) or isinstance(max_cost, bool) or float(max_cost) < 0
    ):
        raise ValidationError("budget_policy.max_cost must be null or number >= 0")
    if deadline is not None:
        parse_timestamp(deadline, field_name="goal.budget_policy.deadline")
    if not isinstance(no_progress, int) or isinstance(no_progress, bool) or no_progress < 1:
        raise ValidationError("budget_policy.no_progress_limit must be integer >= 1")
    return {
        "max_turns": max_turns, "max_tokens": max_tokens, "max_cost": max_cost,
        "deadline": deadline, "no_progress_limit": no_progress,
    }


@dataclass(frozen=True)
class GoalVerdict:
    goal_id: str
    goal_version: int
    verdict: str
    reason: str
    evidence_refs: List[str]
    unmet_criteria: List[str]
    wait_hint: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal_id": self.goal_id, "goal_version": self.goal_version,
            "verdict": self.verdict, "reason": self.reason,
            "evidence_refs": list(self.evidence_refs),
            "unmet_criteria": list(self.unmet_criteria),
            "wait_hint": dict(self.wait_hint) if self.wait_hint else None,
        }


@dataclass(frozen=True)
class GoalMutationResult:
    goal: Dict[str, Any]
    operation_id: str
    replayed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {"goal": dict(self.goal), "operation_id": self.operation_id, "replayed": self.replayed}


class GoalService:
    """Brain-owned durable Goal state. Gateway/host owns continuation execution."""

    def __init__(self, controller: Any):
        self.controller = controller
        self.store = controller.store
        self.lock = RuntimeKeyLock(controller.layout.runtime_dir, namespace="goal")

    @staticmethod
    def _public(obj: BrainObject) -> Dict[str, Any]:
        return {
            "goal_id": obj.id, "scope": obj.scope.value,
            "objective": obj.payload["objective"],
            "status": INTERNAL_TO_PUBLIC[obj.status],
            "completion_contract": dict(obj.payload["completion_contract"]),
            "criteria": [dict(item) for item in obj.payload.get("criteria", [])],
            "budget_policy": dict(obj.payload["budget_policy"]),
            "progress": dict(obj.payload["progress"]),
            "version": obj.revision,
            "activation_epoch": int(obj.payload.get("activation_epoch", 1)),
            "created_at": obj.created_at, "updated_at": obj.updated_at,
            "provenance": dict(obj.payload.get("provenance", {})),
            "evidence_refs": [e.to_dict() for e in obj.evidence_refs],
            "notes": list(obj.payload.get("notes", [])),
            "source_refs": list(obj.source_refs),
        }

    def _receipt_path(self, scope: str, operation_id: str) -> Path:
        directory = self.controller.layout.state_root(Scope(scope)) / "goal-operations"
        digest = hashlib.sha256(operation_id.encode("utf-8")).hexdigest()
        return directory / f"{digest}.json"

    def _receipt(self, scope: str, operation_id: str) -> Optional[Dict[str, Any]]:
        path = self._receipt_path(scope, operation_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValidationError(f"invalid goal operation receipt: {exc}") from exc
        if not isinstance(data, dict):
            raise ValidationError("goal operation receipt must be an object")
        return data

    def _record(self, scope: str, operation_id: str, fp: str, goal: BrainObject) -> None:
        path = self._receipt_path(scope, operation_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "1.0", "operation_id": operation_id,
            "request_fingerprint": fp, "goal_id": goal.id,
            "goal_version": goal.revision, "recorded_at": utc_now(),
        }
        fd, tmp = tempfile.mkstemp(prefix=".goal-op-", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def _begin(self, scope: str, operation_id: str, request: Dict[str, Any]):
        operation_id = _text(operation_id, "operation_id")
        fp = _fingerprint(request)
        receipt = self._receipt(scope, operation_id)
        if receipt:
            if receipt.get("request_fingerprint") != fp:
                raise ValidationError("operation_id was already used with a different Goal mutation payload")
            obj = self.store.load("goal", scope, str(receipt["goal_id"]))
            return fp, GoalMutationResult(self._public(obj), operation_id, True)
        return fp, None

    @staticmethod
    def _version(obj: BrainObject, expected: int) -> None:
        if not isinstance(expected, int) or isinstance(expected, bool) or expected < 1:
            raise ValidationError("expected_version must be integer >= 1")
        if obj.revision != expected:
            raise RevisionConflict(f"expected Goal version {expected}, found {obj.revision}")

    @staticmethod
    def _operator(source: AuthorityTier, action: str) -> None:
        require_user_authority(source, f"Goal {action}")

    def get(self, scope: str, goal_id: str) -> Dict[str, Any]:
        Scope(scope)
        return self._public(self.store.load("goal", scope, goal_id))

    def list(self, scope: str, statuses: Optional[Iterable[str]] = None) -> List[Dict[str, Any]]:
        internal = None
        if statuses is not None:
            internal = []
            for status in statuses:
                key = _text(status, "status")
                if key not in PUBLIC_TO_INTERNAL:
                    raise ValidationError(f"unknown public Goal status: {key}")
                internal.append(PUBLIC_TO_INTERNAL[key])
        return [self._public(item) for item in self.store.list("goal", scope, internal)]

    def create(
        self, scope: str, *, objective: str, operation_id: str,
        completion_contract: Optional[Dict[str, Any]] = None,
        criteria: Optional[Iterable[Any]] = None,
        budget_policy: Optional[Dict[str, Any]] = None,
        active: bool = True, provenance: Optional[Dict[str, Any]] = None,
        source: AuthorityTier = AuthorityTier.EXPLICIT_USER, actor: str = "user",
    ) -> GoalMutationResult:
        self._operator(source, "create")
        Scope(scope)
        objective = _text(objective, "objective")
        request = {
            "action": "create", "scope": scope, "objective": objective,
            "completion_contract": completion_contract or {}, "criteria": list(criteria or []),
            "budget_policy": budget_policy or {}, "active": bool(active), "actor": actor,
        }
        fp, replay = self._begin(scope, operation_id, request)
        if replay:
            return replay
        goal_id = "goal_" + hashlib.sha256(f"{scope}|{operation_id}".encode()).hexdigest()[:32]
        with self.lock.acquire(f"{scope}|{operation_id}"):
            fp, replay = self._begin(scope, operation_id, request)
            if replay:
                return replay
            try:
                existing = self.store.load("goal", scope, goal_id)
            except FileNotFoundError:
                existing = None
            if existing:
                if existing.payload.get("creation_fingerprint") != fp:
                    raise ValidationError("deterministic Goal id collision or changed create payload")
                self._record(scope, operation_id, fp, existing)
                return GoalMutationResult(self._public(existing), operation_id, True)
            payload = {
                "objective": objective,
                "completion_contract": _contract(completion_contract, objective),
                "criteria": _criteria(criteria),
                "budget_policy": _budget(budget_policy),
                "progress": {
                    "attempts": 0, "tokens_used": 0, "cost_used": 0.0,
                    "last_evaluation": None, "last_progress_token": None,
                    "non_progress_count": 0, "last_evidence_refs": [],
                },
                "activation_epoch": 1, "provenance": dict(provenance or {}),
                "notes": [], "creation_operation_id": operation_id,
                "creation_fingerprint": fp,
            }
            obj = BrainObject.new("goal", scope, "ACTIVE" if active else "PAUSED", payload, created_by=actor)
            obj.id = goal_id
            saved = self.store.save(obj, expected_revision=-1)
            self._record(scope, operation_id, fp, saved)
            return GoalMutationResult(self._public(saved), operation_id)

    def edit(
        self, scope: str, goal_id: str, *, expected_version: int, operation_id: str,
        objective: Optional[str] = None,
        completion_contract: Optional[Dict[str, Any]] = None,
        budget_policy: Optional[Dict[str, Any]] = None,
        source: AuthorityTier = AuthorityTier.EXPLICIT_USER, actor: str = "user",
    ) -> GoalMutationResult:
        self._operator(source, "edit")
        request = {
            "action": "edit", "scope": scope, "goal_id": goal_id,
            "expected_version": expected_version, "objective": objective,
            "completion_contract": completion_contract, "budget_policy": budget_policy, "actor": actor,
        }
        fp, replay = self._begin(scope, operation_id, request)
        if replay: return replay
        with self.lock.acquire(f"{scope}|{goal_id}"):
            fp, replay = self._begin(scope, operation_id, request)
            if replay: return replay
            obj = self.store.load("goal", scope, goal_id)
            if obj.status in TERMINAL: raise ValidationError("terminal Goal cannot be edited")
            self._version(obj, expected_version)
            changed = False
            if objective is not None:
                value = _text(objective, "objective")
                changed = changed or value != obj.payload["objective"]
                obj.payload["objective"] = value
            if completion_contract is not None:
                value = _contract(completion_contract, obj.payload["objective"])
                changed = changed or value != obj.payload["completion_contract"]
                obj.payload["completion_contract"] = value
            if budget_policy is not None:
                value = _budget(budget_policy)
                changed = changed or value != obj.payload["budget_policy"]
                obj.payload["budget_policy"] = value
            if changed:
                obj.payload["activation_epoch"] = int(obj.payload.get("activation_epoch", 1)) + 1
            obj.updated_by = actor
            saved = self.store.save(obj, expected_revision=expected_version)
            self._record(scope, operation_id, fp, saved)
            return GoalMutationResult(self._public(saved), operation_id)

    def transition(
        self, scope: str, goal_id: str, *, expected_version: int, operation_id: str,
        action: str, note: Optional[str] = None,
        evidence_refs: Optional[List[EvidenceRef]] = None,
        criterion_results: Optional[List[Dict[str, Any]]] = None,
        source: AuthorityTier = AuthorityTier.EXPLICIT_USER, actor: str = "user",
    ) -> GoalMutationResult:
        action = str(action).lower()
        if action not in _TRANSITION_TARGET:
            raise ValidationError(f"unsupported Goal transition action: {action}")
        if action in {"pause", "resume", "clear"}:
            self._operator(source, action)
        if action in {"budget_limit", "usage_limit"} and source > AuthorityTier.CANONICAL_SCOPED_STATE:
            raise AuthorityError(f"Goal {action} requires canonical system evidence or stronger authority")
        if action == "block" and source > AuthorityTier.VERIFIED_EVIDENCE:
            raise AuthorityError("Goal block requires verified evidence or stronger authority")
        request = {
            "action": action, "scope": scope, "goal_id": goal_id, "expected_version": expected_version,
            "note": note, "evidence_refs": [e.to_dict() for e in evidence_refs or []],
            "criterion_results": list(criterion_results or []), "actor": actor,
        }
        fp, replay = self._begin(scope, operation_id, request)
        if replay: return replay
        with self.lock.acquire(f"{scope}|{goal_id}"):
            fp, replay = self._begin(scope, operation_id, request)
            if replay: return replay
            obj = self.store.load("goal", scope, goal_id)
            if obj.status in TERMINAL: raise ValidationError("terminal Goal cannot transition")
            self._version(obj, expected_version)
            target = _TRANSITION_TARGET[action]
            allowed = {
                "ACTIVE": {"PAUSED", "BLOCKED", "BUDGET_LIMITED", "USAGE_LIMITED", "COMPLETE", "CLEARED"},
                "PAUSED": {"ACTIVE", "CLEARED"}, "BLOCKED": {"ACTIVE", "PAUSED", "CLEARED"},
                "BUDGET_LIMITED": {"ACTIVE", "PAUSED", "CLEARED"},
                "USAGE_LIMITED": {"ACTIVE", "PAUSED", "CLEARED"},
            }
            if target not in allowed.get(obj.status, set()):
                raise ValidationError(f"invalid Goal transition: {INTERNAL_TO_PUBLIC[obj.status]} -> {INTERNAL_TO_PUBLIC[target]}")
            new_evidence = list(evidence_refs or [])
            if action == "complete":
                if source > AuthorityTier.VERIFIED_EVIDENCE:
                    raise AuthorityError("Goal completion requires verified evidence or explicit user authority")
                verdict = self.evaluate(
                    scope, goal_id, expected_version=expected_version,
                    evidence_refs=new_evidence, criterion_results=criterion_results,
                )
                if verdict.verdict != "complete":
                    raise ValidationError("Goal completion rejected: " + verdict.reason)
                results = {
                    item["criterion_id"]: item for item in list(criterion_results or [])
                    if isinstance(item, dict) and isinstance(item.get("criterion_id"), str)
                }
                if results:
                    materialized = []
                    for current in obj.payload.get("criteria", []):
                        item = dict(current)
                        result_item = results.get(item["id"])
                        if result_item is not None:
                            item["status"] = result_item["status"]
                            item["evidence_refs"] = list(result_item.get("evidence_refs", []))
                        materialized.append(item)
                    obj.payload["criteria"] = materialized
                obj.payload["progress"]["last_evaluation"] = {
                    **verdict.to_dict(), "evaluated_at": utc_now(), "actor": actor,
                }
            known = {item.ref for item in obj.evidence_refs}
            for item in new_evidence:
                if item.ref not in known:
                    obj.evidence_refs.append(item); known.add(item.ref)
            if note is not None:
                obj.payload.setdefault("notes", []).append({
                    "action": action, "note": _text(note, "note"), "actor": actor, "at": utc_now()
                })
            obj.status = target
            if target == "ACTIVE":
                obj.payload["activation_epoch"] = int(obj.payload.get("activation_epoch", 1)) + 1
            obj.updated_by = actor
            saved = self.store.save(obj, expected_revision=expected_version)
            self._record(scope, operation_id, fp, saved)
            return GoalMutationResult(self._public(saved), operation_id)

    def _criteria_mutation(
        self, scope: str, goal_id: str, *, expected_version: int, operation_id: str,
        action: str, criterion: Any = None, criterion_id: Optional[str] = None,
        source: AuthorityTier = AuthorityTier.EXPLICIT_USER, actor: str = "user",
    ) -> GoalMutationResult:
        self._operator(source, action)
        normalized = _criteria([criterion])[0] if action == "criteria_add" else None
        request = {
            "action": action, "scope": scope, "goal_id": goal_id, "expected_version": expected_version,
            "criterion": normalized, "criterion_id": criterion_id, "actor": actor,
        }
        fp, replay = self._begin(scope, operation_id, request)
        if replay: return replay
        with self.lock.acquire(f"{scope}|{goal_id}"):
            fp, replay = self._begin(scope, operation_id, request)
            if replay: return replay
            obj = self.store.load("goal", scope, goal_id)
            if obj.status in TERMINAL: raise ValidationError("terminal Goal criteria cannot be changed")
            self._version(obj, expected_version)
            items = list(obj.payload.get("criteria", []))
            if action == "criteria_add":
                if any(item["id"] == normalized["id"] for item in items):
                    raise ValidationError(f"Goal criterion already exists: {normalized['id']}")
                items.append(normalized)
            elif action == "criteria_remove":
                cid = _text(criterion_id, "criterion_id")
                updated = [item for item in items if item["id"] != cid]
                if len(updated) == len(items): raise ValidationError(f"unknown Goal criterion: {cid}")
                items = updated
            elif action == "criteria_clear":
                items = []
            obj.payload["criteria"] = items
            obj.payload["activation_epoch"] = int(obj.payload.get("activation_epoch", 1)) + 1
            obj.updated_by = actor
            saved = self.store.save(obj, expected_revision=expected_version)
            self._record(scope, operation_id, fp, saved)
            return GoalMutationResult(self._public(saved), operation_id)

    def criteria_add(self, scope: str, goal_id: str, **kwargs) -> GoalMutationResult:
        return self._criteria_mutation(scope, goal_id, action="criteria_add", **kwargs)

    def criteria_remove(self, scope: str, goal_id: str, **kwargs) -> GoalMutationResult:
        return self._criteria_mutation(scope, goal_id, action="criteria_remove", **kwargs)

    def criteria_clear(self, scope: str, goal_id: str, **kwargs) -> GoalMutationResult:
        return self._criteria_mutation(scope, goal_id, action="criteria_clear", **kwargs)

    def record_progress(
        self, scope: str, goal_id: str, *, expected_version: int, operation_id: str,
        progress_token: str, evidence_refs: Optional[List[EvidenceRef]] = None,
        tokens_used: int = 0, cost_used: float = 0.0, actor: str = "gateway",
    ) -> GoalMutationResult:
        progress_token = _text(progress_token, "progress_token")
        if not isinstance(tokens_used, int) or isinstance(tokens_used, bool) or tokens_used < 0:
            raise ValidationError("tokens_used must be integer >= 0")
        if not isinstance(cost_used, (int, float)) or isinstance(cost_used, bool) or cost_used < 0:
            raise ValidationError("cost_used must be number >= 0")
        request = {
            "action": "record_progress", "scope": scope, "goal_id": goal_id,
            "expected_version": expected_version, "progress_token": progress_token,
            "evidence_refs": [e.to_dict() for e in evidence_refs or []],
            "tokens_used": tokens_used, "cost_used": float(cost_used), "actor": actor,
        }
        fp, replay = self._begin(scope, operation_id, request)
        if replay: return replay
        with self.lock.acquire(f"{scope}|{goal_id}"):
            fp, replay = self._begin(scope, operation_id, request)
            if replay: return replay
            obj = self.store.load("goal", scope, goal_id)
            if obj.status != "ACTIVE": raise ValidationError("progress may only be committed to an active Goal")
            self._version(obj, expected_version)
            progress = obj.payload["progress"]
            prior = progress.get("last_progress_token")
            progress["attempts"] = int(progress.get("attempts", 0)) + 1
            progress["tokens_used"] = int(progress.get("tokens_used", 0)) + tokens_used
            progress["cost_used"] = float(progress.get("cost_used", 0.0)) + float(cost_used)
            progress["last_progress_token"] = progress_token
            progress["non_progress_count"] = (
                int(progress.get("non_progress_count", 0)) + 1 if prior == progress_token and prior is not None else 0
            )
            incoming = list(evidence_refs or [])
            known = {e.ref for e in obj.evidence_refs}
            for item in incoming:
                if item.ref not in known: obj.evidence_refs.append(item); known.add(item.ref)
            progress["last_evidence_refs"] = [item.ref for item in incoming]
            budget = obj.payload["budget_policy"]
            deadline_reached = bool(
                budget.get("deadline")
                and parse_timestamp(utc_now()) >= parse_timestamp(budget["deadline"], field_name="goal.budget_policy.deadline")
            )
            if deadline_reached:
                obj.status = "BUDGET_LIMITED"
            elif budget.get("max_turns") is not None and progress["attempts"] >= budget["max_turns"]:
                obj.status = "BUDGET_LIMITED"
            elif budget.get("max_tokens") is not None and progress["tokens_used"] >= budget["max_tokens"]:
                obj.status = "USAGE_LIMITED"
            elif budget.get("max_cost") is not None and progress["cost_used"] >= float(budget["max_cost"]):
                obj.status = "BUDGET_LIMITED"
            elif progress["non_progress_count"] >= int(budget["no_progress_limit"]):
                obj.status = "BLOCKED"
                obj.payload.setdefault("notes", []).append({
                    "action": "auto_block_no_progress", "note": "bounded no-progress threshold reached",
                    "actor": "brain:deterministic-gate", "at": utc_now(),
                })
            obj.updated_by = actor
            saved = self.store.save(obj, expected_revision=expected_version)
            self._record(scope, operation_id, fp, saved)
            return GoalMutationResult(self._public(saved), operation_id)

    def evaluate(
        self, scope: str, goal_id: str, *, expected_version: int,
        evidence_refs: Optional[List[EvidenceRef]] = None,
        criterion_results: Optional[List[Dict[str, Any]]] = None,
        wait_hint: Optional[Dict[str, Any]] = None,
        actor: str = "brain:evaluator",
    ) -> GoalVerdict:
        obj = self.store.load("goal", scope, goal_id)
        self._version(obj, expected_version)
        incoming = list(evidence_refs or [])
        evidence = {item.ref: item for item in obj.evidence_refs}
        evidence.update({item.ref: item for item in incoming})
        results = {}
        for result in list(criterion_results or []):
            if not isinstance(result, dict) or not isinstance(result.get("criterion_id"), str):
                raise ValidationError("criterion_results require criterion_id")
            status = result.get("status")
            if status not in {"passed", "failed", "insufficient_evidence", "not_applicable"}:
                raise ValidationError(f"invalid Goal criterion result status: {status}")
            refs = result.get("evidence_refs", [])
            if not isinstance(refs, list) or any(not isinstance(ref, str) or not ref for ref in refs):
                raise ValidationError("criterion result evidence_refs must be a string array")
            if status == "passed":
                if not refs or any(ref not in evidence for ref in refs):
                    raise ValidationError("passed Goal criterion result requires bound evidence")
                if all(evidence[ref].evidence_class == "MODEL_INFERENCE" for ref in refs):
                    raise ValidationError("MODEL_INFERENCE alone cannot pass a Goal criterion")
            results[result["criterion_id"]] = {"status": status, "evidence_refs": list(refs)}
        known_ids = {item["id"] for item in obj.payload.get("criteria", [])}
        unknown = sorted(set(results) - known_ids)
        if unknown:
            raise ValidationError("criterion_results contain unknown ids: " + ", ".join(unknown))
        materialized = []
        for current in obj.payload.get("criteria", []):
            item = dict(current)
            if item["id"] in results:
                item.update(results[item["id"]])
            materialized.append(item)
        unmet, used, failed_gates = [], [], []
        for item in materialized:
            refs = list(item.get("evidence_refs", []))
            if item.get("status") not in {"passed", "not_applicable"}:
                unmet.append(item["id"])
            elif item["status"] == "passed" and (not refs or any(ref not in evidence for ref in refs)):
                unmet.append(item["id"])
            else:
                used.extend(refs)
        for gate in obj.payload["completion_contract"].get("verification", []):
            if not gate.get("required", True): continue
            refs = []
            if isinstance(gate.get("evidence_ref"), str): refs.append(gate["evidence_ref"])
            if isinstance(gate.get("evidence_refs"), list): refs += [r for r in gate["evidence_refs"] if isinstance(r, str)]
            if not refs or any(ref not in evidence for ref in refs):
                failed_gates.append(gate["id"])
            else:
                used.extend(refs)
        if obj.status in {"PAUSED", "BUDGET_LIMITED", "USAGE_LIMITED"}:
            verdict, reason = "wait", f"Goal is {INTERNAL_TO_PUBLIC[obj.status]}"
        elif obj.status == "BLOCKED":
            verdict, reason = "blocked", "Goal is blocked pending new evidence or operator action"
        elif obj.status == "COMPLETE":
            verdict, reason = "complete", "Goal is already complete"
        elif obj.status == "CLEARED":
            verdict, reason = "wait", "Goal is cleared and cannot continue"
        elif unmet or failed_gates:
            verdict = "continue"
            reason = "; ".join(filter(None, [
                "unmet criteria: " + ", ".join(unmet) if unmet else "",
                "verification gates not satisfied: " + ", ".join(failed_gates) if failed_gates else "",
            ]))
        elif not evidence and (obj.payload.get("criteria") or obj.payload["completion_contract"].get("verification")):
            verdict, reason = "continue", "completion requires current evidence"
        else:
            verdict, reason = "complete", "all declared criteria and verification gates are satisfied by current evidence"
        result = GoalVerdict(
            obj.id, obj.revision, verdict, reason, sorted(set(used)),
            unmet + [f"gate:{item}" for item in failed_gates],
            dict(wait_hint) if wait_hint else None,
        )
        return result

    def continuation_contract(self, scope: str, goal_id: str) -> Dict[str, Any]:
        obj = self.store.load("goal", scope, goal_id)
        budget = dict(obj.payload["budget_policy"])
        deadline_reached = bool(
            budget.get("deadline")
            and parse_timestamp(utc_now()) >= parse_timestamp(budget["deadline"], field_name="goal.budget_policy.deadline")
        )
        return {
            "goal_id": obj.id, "goal_version": obj.revision,
            "activation_epoch": int(obj.payload.get("activation_epoch", 1)),
            "status": INTERNAL_TO_PUBLIC[obj.status],
            "may_continue": obj.status == "ACTIVE" and not deadline_reached,
            "deadline_reached": deadline_reached,
            "budget_policy": budget, "progress": dict(obj.payload["progress"]),
            "constraints": list(obj.payload["completion_contract"].get("constraints", [])),
            "boundaries": list(obj.payload["completion_contract"].get("boundaries", [])),
            "stop_when": list(obj.payload["completion_contract"].get("stop_when", [])),
            "authority_note": "This contract never grants tools, scheduling, connections, or permission expansion.",
        }
