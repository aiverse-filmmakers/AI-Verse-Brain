from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .authority import AuthorityTier
from .errors import ValidationError
from .models import BrainObject, Scope
from .runtime_lock import RuntimeKeyLock

_SCHEMA_VERSION = 1
_OWNER_OS = "os"
_OWNER_BRAIN = "brain"
_STRATEGIC_ANSWER_KEYS = {
    "desired_state", "success_definition", "goals", "boundaries", "constraints",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_scope_filename(scope: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", scope)


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def ownership_path(root: Path) -> Path:
    return Path(root).resolve() / ".aiverse" / "direction" / "ownership.json"


def _assert_safe_direction_path(root: Path, target: Path) -> None:
    root = Path(root).resolve()
    direction = root / ".aiverse" / "direction"
    if direction.exists() and direction.is_symlink():
        raise ValidationError("direction ownership directory must not be a symlink")
    if target.exists() and target.is_symlink():
        raise ValidationError("direction ownership file must not be a symlink")
    if not _inside(target.parent, root):
        raise ValidationError("direction ownership path escapes host root")


def _atomic_json_write(root: Path, target: Path, data: Dict[str, Any]) -> None:
    _assert_safe_direction_path(root, target)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _empty_registry() -> Dict[str, Any]:
    return {"schema_version": _SCHEMA_VERSION, "scopes": {}}


def read_registry(root: Path) -> Dict[str, Any]:
    root = Path(root).resolve()
    target = ownership_path(root)
    _assert_safe_direction_path(root, target)
    if not target.exists():
        return _empty_registry()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValidationError(f"invalid direction ownership registry: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema_version") != _SCHEMA_VERSION:
        raise ValidationError("unsupported or malformed direction ownership registry")
    scopes = data.get("scopes")
    if not isinstance(scopes, dict):
        raise ValidationError("direction ownership registry scopes must be an object")
    for scope, record in scopes.items():
        try:
            Scope(scope)
        except Exception as exc:
            raise ValidationError(f"invalid direction ownership scope: {scope}") from exc
        if not isinstance(record, dict) or record.get("owner") not in {_OWNER_OS, _OWNER_BRAIN}:
            raise ValidationError(f"invalid direction ownership record for {scope}")
    return data


def direction_owner_for(controller: Any, scope: str) -> str:
    Scope(scope)
    if controller.layout.mode != "native":
        return _OWNER_BRAIN
    registry = read_registry(controller.layout.root)
    record = registry["scopes"].get(scope)
    return str(record.get("owner")) if record else _OWNER_OS


def strategic_answers_present(answers: Dict[str, Any]) -> bool:
    for key in _STRATEGIC_ANSWER_KEYS:
        value = answers.get(key)
        if value is None:
            continue
        if isinstance(value, list) and not value:
            continue
        return True
    return False


@dataclass(frozen=True)
class DirectionImportCandidate:
    subtype: str
    statement: str
    source_path: str
    source_sha256: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "subtype": self.subtype,
            "statement": self.statement,
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
        }


@dataclass(frozen=True)
class DirectionHandoverPlan:
    scope: str
    current_owner: str
    can_handover: bool
    import_candidates: List[DirectionImportCandidate] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scope": self.scope,
            "current_owner": self.current_owner,
            "can_handover": self.can_handover,
            "import_candidates": [item.to_dict() for item in self.import_candidates],
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class DirectionHandoverResult:
    scope: str
    owner: str
    handover_id: Optional[str]
    state: str
    brain_refs: List[str] = field(default_factory=list)
    imported_sources: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scope": self.scope,
            "owner": self.owner,
            "handover_id": self.handover_id,
            "state": self.state,
            "brain_refs": list(self.brain_refs),
            "imported_sources": list(self.imported_sources),
        }


def _section(text: str, heading: str) -> Optional[str]:
    match = re.search(
        rf"(?ims)^##\s+{re.escape(heading)}\s*$\n(.*?)(?=^##\s+|\Z)",
        text,
    )
    return match.group(1).strip() if match else None


def _clean_bullet(value: str) -> Optional[str]:
    value = re.sub(r"^\s*[-*]\s+", "", value).strip()
    value = re.sub(r"^\[[ xX]\]\s*", "", value).strip()
    if not value or (value.startswith("[") and value.endswith("]")):
        return None
    return value


def _bullet_candidates(path: Path, heading: str, subtype: str, root: Path) -> List[DirectionImportCandidate]:
    if not path.is_file() or path.is_symlink():
        return []
    raw = path.read_bytes()
    body = _section(raw.decode("utf-8"), heading)
    if body is None:
        return []
    result: List[DirectionImportCandidate] = []
    digest = _sha256(raw)
    rel = path.relative_to(root).as_posix()
    for line in body.splitlines():
        if not re.match(r"^\s*[-*]\s+", line):
            continue
        statement = _clean_bullet(line)
        if statement:
            result.append(DirectionImportCandidate(subtype, statement, rel, digest))
    return result


def _objective_candidate(path: Path, root: Path) -> List[DirectionImportCandidate]:
    if not path.is_file() or path.is_symlink():
        return []
    raw = path.read_bytes()
    body = _section(raw.decode("utf-8"), "Objective")
    if body is None:
        return []
    statement = " ".join(line.strip() for line in body.splitlines() if line.strip())
    if not statement or (statement.startswith("[") and statement.endswith("]")):
        return []
    return [DirectionImportCandidate("desired_state", statement, path.relative_to(root).as_posix(), _sha256(raw))]


def _dedupe(candidates: List[DirectionImportCandidate]) -> List[DirectionImportCandidate]:
    seen = set()
    result = []
    for item in candidates:
        key = (item.subtype, " ".join(item.statement.casefold().split()))
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


class DirectionOwnershipService:
    """Coordinates one durable strategic owner per AI-Verse OS scope."""

    def __init__(self, controller: Any):
        self.controller = controller
        self.root = controller.layout.root
        self.lock = RuntimeKeyLock(controller.layout.runtime_dir, namespace="direction-owner")

    def owner(self, scope: str) -> str:
        return direction_owner_for(self.controller, scope)

    def _candidates(self, scope: str) -> List[DirectionImportCandidate]:
        if self.controller.layout.mode != "native":
            return []
        root = self.root
        if scope == "operator":
            candidates = []
            candidates.extend(_bullet_candidates(root / "operator" / "profile" / "goals.md", "Current horizon", "goal", root))
            candidates.extend(_bullet_candidates(root / "operator" / "context" / "CURRENT.md", "Current priorities", "goal", root))
            return _dedupe(candidates)
        parsed = Scope(scope)
        if parsed.is_operator:
            return []
        current = root / "workspaces" / str(parsed.workspace_id) / "context" / "CURRENT.md"
        return _objective_candidate(current, root)

    def plan(self, scope: str) -> DirectionHandoverPlan:
        Scope(scope)
        owner = self.owner(scope)
        if self.controller.layout.mode != "native":
            return DirectionHandoverPlan(
                scope, owner, False, [],
                ["Standalone Brain has no competing OS strategic store; Brain is already the direction owner."],
            )
        return DirectionHandoverPlan(
            scope,
            owner,
            owner == _OWNER_OS,
            self._candidates(scope) if owner == _OWNER_OS else [],
            [
                "Handover requires explicit --apply --confirm-import.",
                "Existing OS goals/objectives are imported with path + SHA-256 provenance before ownership changes.",
                "After ownership changes to Brain, OS strategic sources are frozen provenance; OS may expose only refs/generated views as active direction.",
                "The ownership marker is OS-local durable state, so Brain unavailability never returns ownership to OS.",
            ],
        )

    def status(self, scope: str) -> DirectionHandoverResult:
        Scope(scope)
        if self.controller.layout.mode != "native":
            return DirectionHandoverResult(scope, _OWNER_BRAIN, None, "standalone", [], [])
        registry = read_registry(self.root)
        record = registry["scopes"].get(scope)
        if not record:
            return DirectionHandoverResult(scope, _OWNER_OS, None, "active", [], [])
        return DirectionHandoverResult(
            scope,
            str(record["owner"]),
            record.get("handover_id"),
            str(record.get("state", "active")),
            list(record.get("brain_refs", [])),
            list(record.get("legacy_sources", [])),
        )

    def _create_proposed_intent(self, scope: str, candidate: DirectionImportCandidate, handover_id: str) -> BrainObject:
        payload = {
            "subtype": candidate.subtype,
            "statement": candidate.statement,
            "provenance": {
                "source": "ai-verse-os",
                "source_path": candidate.source_path,
                "source_sha256": candidate.source_sha256,
                "handover_id": handover_id,
                "import_confirmed": True,
            },
        }
        return self.controller.create(
            "intent",
            scope,
            "PROPOSED",
            payload,
            source=AuthorityTier.EXPLICIT_USER,
            actor="user:direction-handover",
            source_refs=[f"os:{candidate.source_path}#sha256:{candidate.source_sha256}"],
        )

    def _render_view(self, scope: str, record: Dict[str, Any]) -> None:
        view = self.root / ".aiverse" / "direction" / "views" / f"{_safe_scope_filename(scope)}.md"
        _assert_safe_direction_path(self.root, view)
        view.parent.mkdir(parents=True, exist_ok=True)
        refs = record.get("brain_refs", [])
        body = [
            f"# Direction View — {scope}",
            "",
            "This is a generated OS-side reference view. AI-Verse Brain is the strategic direction owner for this scope.",
            "Do not edit strategic goals/objectives in OS files while the ownership marker remains `brain`.",
            "",
            "## Canonical Brain refs",
            "",
        ]
        body.extend(f"- `{ref}`" for ref in refs)
        if not refs:
            body.append("- none imported; use Brain onboarding to establish explicit strategic intent")
        body.extend(["", "## Frozen provenance", ""])
        for source in record.get("legacy_sources", []):
            body.append(f"- `{source['path']}` — sha256 `{source['sha256']}`")
        text = "\n".join(body) + "\n"
        fd, temp_name = tempfile.mkstemp(prefix=f".{view.name}.", suffix=".tmp", dir=str(view.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, view)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def _resume_pending(self, scope: str, registry: Dict[str, Any], record: Dict[str, Any]) -> DirectionHandoverResult:
        refs = list(record.get("brain_refs", []))
        confirmed: List[str] = []
        for ref in refs:
            prefix = "brain:intent:"
            if not isinstance(ref, str) or not ref.startswith(prefix):
                raise ValidationError("pending direction handover contains an invalid Brain intent ref")
            object_id = ref[len(prefix):]
            obj = self.controller.store.load("intent", scope, object_id)
            if obj.status == "PROPOSED":
                obj = self.controller.transition(
                    "intent", scope, object_id, "CONFIRMED",
                    source=AuthorityTier.EXPLICIT_USER,
                    actor="user:direction-handover",
                )
            if obj.status not in {"CONFIRMED", "ACTIVE"}:
                raise ValidationError(f"handover intent is not confirmable: {ref} ({obj.status})")
            confirmed.append(ref)
        record["brain_refs"] = confirmed
        record["state"] = "active"
        record["completed_at"] = _utc_now()
        registry["scopes"][scope] = record
        _atomic_json_write(self.root, ownership_path(self.root), registry)
        self._render_view(scope, record)
        return self.status(scope)

    def handover(self, scope: str, *, confirm_import: bool) -> DirectionHandoverResult:
        Scope(scope)
        if not confirm_import:
            raise ValidationError("explicit --confirm-import is required for strategic direction handover")
        if self.controller.layout.mode != "native":
            raise ValidationError("direction handover is only needed for an AI-Verse OS native installation")

        with self.lock.acquire(scope):
            registry = read_registry(self.root)
            existing = registry["scopes"].get(scope)
            if existing and existing.get("owner") == _OWNER_BRAIN:
                if existing.get("state") == "activating":
                    return self._resume_pending(scope, registry, existing)
                return self.status(scope)

            candidates = self._candidates(scope)
            handover_id = f"handover-{uuid4()}"
            objects = [self._create_proposed_intent(scope, item, handover_id) for item in candidates]
            refs = [f"brain:intent:{obj.id}" for obj in objects]
            sources = []
            seen_sources = set()
            for item in candidates:
                key = (item.source_path, item.source_sha256)
                if key not in seen_sources:
                    seen_sources.add(key)
                    sources.append({"path": item.source_path, "sha256": item.source_sha256})

            # Flip ownership only after all imported intent objects exist in a non-active PROPOSED state.
            # If the process stops after this write, OS remains locked out of strategic writes and rerunning
            # handover resumes confirmation from the recorded refs.
            record: Dict[str, Any] = {
                "owner": _OWNER_BRAIN,
                "state": "activating",
                "handover_id": handover_id,
                "handed_over_at": _utc_now(),
                "handover_actor": "explicit-user",
                "import_confirmed": True,
                "brain_refs": refs,
                "legacy_sources": sources,
                "view_path": f".aiverse/direction/views/{_safe_scope_filename(scope)}.md",
            }
            registry["scopes"][scope] = record
            _atomic_json_write(self.root, ownership_path(self.root), registry)
            return self._resume_pending(scope, registry, record)
