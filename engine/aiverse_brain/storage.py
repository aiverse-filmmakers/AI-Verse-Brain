from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Iterable, Iterator, List, Optional
from uuid import uuid4

from .errors import LockConflict, RevisionConflict, ScopeError
from .models import BrainObject, Scope, utc_now
from .validation import validate_payload

_KIND_DIR = {
    "intent": "intent", "practice": "practices", "gap": "gaps", "opportunity": "opportunities",
    "initiative": "initiatives", "objective": "objectives", "model_belief": "models",
    "evaluation": "evaluations", "learning": "learning", "strategy_rule": "strategies", "policy": "policies",
}


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


class StorageLayout:
    def __init__(self, root: Path, mode: str):
        self.root = Path(root).resolve()
        if mode not in {"native", "standalone"}:
            raise ValueError("mode must be native or standalone")
        self.mode = mode

    @classmethod
    def detect(cls, root: Path) -> "StorageLayout":
        root = Path(root).resolve()
        manifest = root / "AI-VERSE.yaml"
        if manifest.exists() and (root / "operator").is_dir() and (root / "workspaces").is_dir():
            text = manifest.read_text(encoding="utf-8", errors="replace")
            if 'schema_version: "2.' in text and "architecture: unified-workspace" in text:
                return cls(root, "native")
        return cls(root, "standalone")

    def state_root(self, scope: Scope) -> Path:
        if self.mode == "standalone":
            if not scope.is_operator:
                raise ScopeError("standalone core v0.1 supports operator scope only; host adapters may add scoped mapping")
            state = self.root / ".ai-verse-brain"
            if state.exists() and not _inside(state, self.root):
                raise ScopeError("standalone Brain state escapes repository root")
            return state
        if scope.is_operator:
            state = self.root / "operator" / "brain"
            if state.exists() and not _inside(state, self.root / "operator"):
                raise ScopeError("operator Brain state escapes operator root")
            return state
        workspace_root = self.root / "workspaces"
        workspace = workspace_root / str(scope.workspace_id)
        if not workspace.is_dir():
            raise ScopeError(f"workspace does not exist: {scope.workspace_id}")
        if not _inside(workspace, workspace_root):
            raise ScopeError("workspace resolves outside workspaces root")
        state = workspace / "brain"
        if state.exists() and not _inside(state, workspace):
            raise ScopeError("workspace Brain state escapes workspace root")
        return state

    @property
    def runtime_dir(self) -> Path:
        if self.mode == "native":
            return self.root / "runtime" / "ai-verse-brain"
        return self.root / ".ai-verse-brain" / "runtime"

    def object_path(self, obj: BrainObject) -> Path:
        return self.state_root(obj.scope) / _KIND_DIR[obj.kind] / f"{obj.id}.json"

    def kind_dir(self, scope: Scope, kind: str) -> Path:
        return self.state_root(scope) / _KIND_DIR[kind]


class ObjectStore:
    def __init__(self, layout: StorageLayout, *, lock_ttl_seconds: int = 60):
        self.layout = layout
        self.lock_ttl_seconds = lock_ttl_seconds

    def _lock_path(self, obj: BrainObject) -> Path:
        raw = f"{obj.scope.value}|{obj.kind}|{obj.id}"
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        directory = self.layout.runtime_dir / "locks"
        directory.mkdir(parents=True, exist_ok=True)
        return directory / f"{digest}.lock"

    def _release_if_owned(self, path: Path, token: str) -> None:
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
            if current.get("token") == token:
                path.unlink(missing_ok=True)
        except FileNotFoundError:
            return

    @contextmanager
    def _lock(self, obj: BrainObject) -> Iterator[None]:
        path = self._lock_path(obj)
        token = str(uuid4())
        payload = json.dumps({"token": token, "acquired_at": utc_now(), "pid": os.getpid()}) + "\n"
        for attempt in range(2):
            try:
                fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                try:
                    age = time.time() - path.stat().st_mtime
                except FileNotFoundError:
                    continue
                if age > self.lock_ttl_seconds and attempt == 0:
                    try:
                        path.unlink()
                    except FileNotFoundError:
                        pass
                    continue
                raise LockConflict(f"object is currently locked: {obj.id}")
            else:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                break
        else:
            raise LockConflict(f"unable to acquire lock: {obj.id}")
        try:
            yield
        finally:
            self._release_if_owned(path, token)

    def load(self, kind: str, scope: str, object_id: str) -> BrainObject:
        s = Scope(scope)
        path = self.layout.kind_dir(s, kind) / f"{object_id}.json"
        return BrainObject.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def save(self, obj: BrainObject, *, expected_revision: Optional[int]) -> BrainObject:
        validate_payload(obj.kind, obj.payload)
        path = self.layout.object_path(obj)
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock(obj):
            exists = path.exists()
            if exists:
                current = BrainObject.from_dict(json.loads(path.read_text(encoding="utf-8")))
                if current.scope != obj.scope or current.kind != obj.kind:
                    raise RevisionConflict("immutable scope/kind mismatch")
                if expected_revision is None or current.revision != expected_revision:
                    raise RevisionConflict(f"expected revision {expected_revision}, found {current.revision}")
                obj.revision = current.revision + 1
                obj.created_at = current.created_at
                obj.created_by = current.created_by
            else:
                if expected_revision not in {None, -1}:
                    raise RevisionConflict("object does not yet exist")
                obj.revision = 1
            obj.updated_at = utc_now()
            data = json.dumps(obj.to_dict(), indent=2, sort_keys=True) + "\n"
            fd, temp_name = tempfile.mkstemp(prefix=f".{obj.id}.", suffix=".tmp", dir=str(path.parent))
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_name, path)
            finally:
                if os.path.exists(temp_name):
                    os.unlink(temp_name)
        return obj

    def list(self, kind: str, scope: str, statuses: Optional[Iterable[str]] = None) -> List[BrainObject]:
        directory = self.layout.kind_dir(Scope(scope), kind)
        if not directory.exists():
            return []
        allowed = set(statuses) if statuses else None
        result = []
        for path in sorted(directory.glob("*.json")):
            obj = BrainObject.from_dict(json.loads(path.read_text(encoding="utf-8")))
            if allowed is None or obj.status in allowed:
                result.append(obj)
        return result
