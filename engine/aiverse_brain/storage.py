from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Iterable, List, Optional

from .errors import RevisionConflict, ScopeError
from .models import BrainObject, Scope, utc_now

_KIND_DIR = {
    "intent": "intent", "practice": "practices", "gap": "gaps", "opportunity": "opportunities",
    "initiative": "initiatives", "objective": "objectives", "model_belief": "models",
    "evaluation": "evaluations", "learning": "learning", "strategy_rule": "strategies", "policy": "policies",
}


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
            return self.root / ".ai-verse-brain"
        if scope.is_operator:
            return self.root / "operator" / "brain"
        workspace = self.root / "workspaces" / str(scope.workspace_id)
        if not workspace.is_dir():
            raise ScopeError(f"workspace does not exist: {scope.workspace_id}")
        return workspace / "brain"

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
    def __init__(self, layout: StorageLayout):
        self.layout = layout

    def load(self, kind: str, scope: str, object_id: str) -> BrainObject:
        s = Scope(scope)
        path = self.layout.kind_dir(s, kind) / f"{object_id}.json"
        return BrainObject.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def save(self, obj: BrainObject, *, expected_revision: Optional[int]) -> BrainObject:
        path = self.layout.object_path(obj)
        path.parent.mkdir(parents=True, exist_ok=True)
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
