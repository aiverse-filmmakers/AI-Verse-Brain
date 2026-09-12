from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .authority import AuthorityTier
from .errors import LockConflict, ValidationError
from .models import BrainObject, Scope
from .runtime_lock import RuntimeKeyLock

_SCHEMA_VERSION = 1
_OWNER_OS = "os"
_OWNER_BRAIN = "brain"
_REGISTRY_LOCK_KEY = "ownership-registry"
_REGISTRY_LOCK_WAIT_SECONDS = 10.0
_REGISTRY_LOCK_POLL_SECONDS = 0.02
_STRATEGIC_ANSWER_KEYS = {
    "desired_state", "success_definition", "goals", "boundaries", "constraints",
}
_STRATEGIC_SUBTYPES = {
    "desired_state": "Desired state",
    "success_definition": "Success definition",
    "goal": "Goal",
    "boundary": "Boundary",
    "constraint": "Constraint",
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


def _atomic_text_write(root: Path, boundary: Path, target: Path, text: str) -> None:
    root = Path(root).resolve()
    boundary = Path(boundary).resolve()
    target = Path(target)
    if not boundary.is_dir() or boundary.is_symlink():
        raise ValidationError("direction export target boundary must be a real directory")
    if not _inside(boundary, root):
        raise ValidationError("direction export boundary escapes host root")
    if target.exists() and (target.is_symlink() or not target.is_file()):
        raise ValidationError(f"direction export target is unsafe: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.parent.is_symlink() or not _inside(target.parent, boundary):
        raise ValidationError("direction export target parent escapes its scope boundary")
    fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _replace_h2_section(text: str, heading: str, body_lines: List[str]) -> str:
    lines = text.splitlines()
    match_index: Optional[int] = None
    end_index = len(lines)
    wanted = heading.strip().casefold()
    for index, line in enumerate(lines):
        match = re.match(r"^##\s+(.+?)\s*$", line)
        if match and match.group(1).strip().casefold() == wanted:
            match_index = index
            for later in range(index + 1, len(lines)):
                if re.match(r"^##\s+(.+?)\s*$", lines[later]):
                    end_index = later
                    break
            break

    section = [f"## {heading}", "", *body_lines]
    if match_index is None:
        base = text.rstrip()
        return (base + ("\n\n" if base else "") + "\n".join(section).rstrip() + "\n")
    before = lines[:match_index]
    after = lines[end_index:]
    rebuilt = before + section
    if after:
        if rebuilt and rebuilt[-1] != "":
            rebuilt.append("")
        rebuilt.extend(after)
    return "\n".join(rebuilt).rstrip() + "\n"


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
class DirectionReturnPlan:
    scope: str
    current_owner: str
    can_handover: bool
    target_path: Optional[str]
    export_items: List[Dict[str, str]] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scope": self.scope,
            "current_owner": self.current_owner,
            "can_handover": self.can_handover,
            "target_path": self.target_path,
            "export_items": [dict(item) for item in self.export_items],
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
        self.registry_lock = RuntimeKeyLock(controller.layout.runtime_dir, namespace="direction-owner-registry")

    @contextmanager
    def _registry_guard(self):
        deadline = time.monotonic() + _REGISTRY_LOCK_WAIT_SECONDS
        while True:
            manager = self.registry_lock.acquire(_REGISTRY_LOCK_KEY)
            try:
                manager.__enter__()
            except LockConflict:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(_REGISTRY_LOCK_POLL_SECONDS)
                continue
            break
        try:
            yield
        except BaseException as exc:
            manager.__exit__(type(exc), exc, exc.__traceback__)
            raise
        else:
            manager.__exit__(None, None, None)

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

    def _os_current_target(self, scope: str) -> tuple[Path, Path, str]:
        parsed = Scope(scope)
        if parsed.is_operator:
            boundary = self.root / "operator"
            target = boundary / "context" / "CURRENT.md"
            return boundary, target, "Current priorities"
        boundary = self.root / "workspaces" / str(parsed.workspace_id)
        if not boundary.is_dir() or boundary.is_symlink():
            raise ValidationError(f"workspace does not exist or is unsafe: {parsed.workspace_id}")
        target = boundary / "context" / "CURRENT.md"
        return boundary, target, "Objective"

    def _brain_direction_items(self, scope: str) -> List[Dict[str, str]]:
        result: List[Dict[str, str]] = []
        for obj in self.controller.store.list("intent", scope, {"CONFIRMED", "ACTIVE"}):
            subtype = obj.payload.get("subtype")
            statement = obj.payload.get("statement")
            if subtype not in _STRATEGIC_SUBTYPES:
                continue
            if not isinstance(statement, str) or not statement.strip():
                continue
            result.append({
                "ref": f"brain:intent:{obj.id}",
                "subtype": str(subtype),
                "label": _STRATEGIC_SUBTYPES[str(subtype)],
                "statement": statement.strip(),
            })
        return result

    def plan_return_to_os(self, scope: str) -> DirectionReturnPlan:
        Scope(scope)
        owner = self.owner(scope)
        if self.controller.layout.mode != "native":
            return DirectionReturnPlan(
                scope, owner, False, None, [],
                ["Standalone Brain has no AI-Verse OS strategic owner to return to."],
            )
        boundary, target, _ = self._os_current_target(scope)
        items = self._brain_direction_items(scope) if owner == _OWNER_BRAIN else []
        return DirectionReturnPlan(
            scope=scope,
            current_owner=owner,
            can_handover=(owner == _OWNER_BRAIN and bool(items)),
            target_path=target.relative_to(self.root).as_posix(),
            export_items=items,
            notes=[
                "Return requires explicit --apply --confirm-export.",
                "Brain strategic intent is exported before ownership changes.",
                "Only the OS strategic section is replaced; operational/current-state sections are preserved.",
                "Canonical Brain objects remain intact as provenance after OS becomes the owner.",
                "If export succeeds but ownership flip is interrupted, Brain remains owner and OS continues filtering the staged OS strategic section.",
            ],
        )

    def _render_return_export(
        self,
        scope: str,
        handback_id: str,
        items: List[Dict[str, str]],
        target_relative: str,
    ) -> Path:
        export = (
            self.root
            / ".aiverse"
            / "direction"
            / "exports"
            / f"{_safe_scope_filename(scope)}-{handback_id}.md"
        )
        _assert_safe_direction_path(self.root, export)
        lines = [
            f"# Brain → OS Direction Export — {scope}",
            "",
            f"Handback: `{handback_id}`",
            f"Target OS source: `{target_relative}`",
            "",
            "This snapshot was explicitly exported before strategic ownership returned to AI-Verse OS.",
            "Canonical Brain objects are retained as provenance; this export does not delete or rewrite them.",
            "",
            "## Strategic direction",
            "",
        ]
        for item in items:
            lines.append(f"- **{item['label']}**: {item['statement']}  ")
            lines.append(f"  Brain ref: `{item['ref']}`")
        lines.append("")
        export.parent.mkdir(parents=True, exist_ok=True)
        _atomic_text_write(self.root, self.root / ".aiverse" / "direction", export, "\n".join(lines))
        return export

    def handback_to_os(self, scope: str, *, confirm_export: bool) -> DirectionHandoverResult:
        Scope(scope)
        if not confirm_export:
            raise ValidationError("explicit --confirm-export is required for Brain-to-OS direction handback")
        if self.controller.layout.mode != "native":
            raise ValidationError("direction handback requires an AI-Verse OS native installation")

        with self.lock.acquire(scope):
            with self._registry_guard():
                registry = read_registry(self.root)
                existing = registry["scopes"].get(scope)
                if not isinstance(existing, dict) or existing.get("owner") != _OWNER_BRAIN:
                    if existing and existing.get("owner") == _OWNER_OS:
                        return self.status(scope)
                    raise ValidationError(f"Brain does not own strategic direction for {scope}")
                if existing.get("state") != "active":
                    raise ValidationError(
                        f"Brain direction handover for {scope} is not active; resume/repair it before returning ownership"
                    )

                items = self._brain_direction_items(scope)
                if not items:
                    raise ValidationError(
                        f"cannot return {scope} direction to OS without at least one confirmed/active Brain strategic intent"
                    )

                boundary, target, heading = self._os_current_target(scope)
                target.parent.mkdir(parents=True, exist_ok=True)
                current = target.read_text(encoding="utf-8", errors="replace") if target.exists() else ""
                before_sha = _sha256(current.encode("utf-8"))
                handback_id = f"handback-{uuid4()}"
                body = [f"- {item['label']}: {item['statement']}" for item in items]
                staged = _replace_h2_section(current, heading, body)
                _atomic_text_write(self.root, boundary, target, staged)
                target_sha = _sha256(staged.encode("utf-8"))

                export = self._render_return_export(
                    scope,
                    handback_id,
                    items,
                    target.relative_to(self.root).as_posix(),
                )

                latest = read_registry(self.root)
                record = latest["scopes"].get(scope)
                if (
                    not isinstance(record, dict)
                    or record.get("owner") != _OWNER_BRAIN
                    or record.get("state") != "active"
                ):
                    raise ValidationError(
                        "direction ownership changed while Brain-to-OS export was being staged; ownership was not flipped"
                    )

                returned = dict(record)
                returned.update({
                    "owner": _OWNER_OS,
                    "state": "active",
                    "handback_id": handback_id,
                    "handed_back_at": _utc_now(),
                    "handback_actor": "explicit-user",
                    "export_confirmed": True,
                    "os_source_path": target.relative_to(self.root).as_posix(),
                    "os_source_previous_sha256": before_sha,
                    "os_source_sha256": target_sha,
                    "brain_export_path": export.relative_to(self.root).as_posix(),
                    "brain_refs": [item["ref"] for item in items],
                })
                latest["scopes"][scope] = returned
                _atomic_json_write(self.root, ownership_path(self.root), latest)

                return DirectionHandoverResult(
                    scope,
                    _OWNER_OS,
                    handback_id,
                    "active",
                    list(returned.get("brain_refs", [])),
                    list(returned.get("legacy_sources", [])),
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

    def _resume_pending(self, scope: str) -> DirectionHandoverResult:
        # Recovery rewrites the same shared ownership registry as a fresh handover.
        # Acquire the registry-wide lock and reread the latest document so one scope
        # can never replace records written by another scope while it was interrupted.
        with self._registry_guard():
            registry = read_registry(self.root)
            record = registry["scopes"].get(scope)
            if not isinstance(record, dict) or record.get("owner") != _OWNER_BRAIN:
                raise ValidationError(f"no Brain-owned direction handover is available to resume for {scope}")
            if record.get("state") != "activating":
                return DirectionHandoverResult(
                    scope,
                    _OWNER_BRAIN,
                    record.get("handover_id"),
                    str(record.get("state", "active")),
                    list(record.get("brain_refs", [])),
                    list(record.get("legacy_sources", [])),
                )

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

            record = dict(record)
            record["brain_refs"] = confirmed
            record["state"] = "active"
            record["completed_at"] = _utc_now()
            registry["scopes"][scope] = record
            _atomic_json_write(self.root, ownership_path(self.root), registry)
            self._render_view(scope, record)
            return DirectionHandoverResult(
                scope,
                _OWNER_BRAIN,
                record.get("handover_id"),
                "active",
                list(record.get("brain_refs", [])),
                list(record.get("legacy_sources", [])),
            )

    def handover(self, scope: str, *, confirm_import: bool) -> DirectionHandoverResult:
        Scope(scope)
        if not confirm_import:
            raise ValidationError("explicit --confirm-import is required for strategic direction handover")
        if self.controller.layout.mode != "native":
            raise ValidationError("direction handover is only needed for an AI-Verse OS native installation")

        with self.lock.acquire(scope):
            existing = read_registry(self.root)["scopes"].get(scope)
            if existing and existing.get("owner") == _OWNER_BRAIN:
                if existing.get("state") == "activating":
                    return self._resume_pending(scope)
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

            # The shared ownership registry is one resource across every scope.
            # Reread it while holding one registry-wide lock immediately before the
            # read-modify-write so concurrent Alpha/Beta handovers preserve both.
            with self._registry_guard():
                registry = read_registry(self.root)
                latest = registry["scopes"].get(scope)
                if latest and latest.get("owner") == _OWNER_BRAIN:
                    if latest.get("state") != "activating":
                        return DirectionHandoverResult(
                            scope,
                            _OWNER_BRAIN,
                            latest.get("handover_id"),
                            str(latest.get("state", "active")),
                            list(latest.get("brain_refs", [])),
                            list(latest.get("legacy_sources", [])),
                        )
                else:
                    registry["scopes"][scope] = record
                    _atomic_json_write(self.root, ownership_path(self.root), registry)

            # Confirmation/recovery performs its own registry-wide locked reread.
            # If a process stops after the activating write, rerunning handover
            # resumes only this scope without replacing newer records from others.
            return self._resume_pending(scope)
