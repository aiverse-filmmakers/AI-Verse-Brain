from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from .errors import PermissionDenied, ValidationError
from .integration import HostMode, inspect_host
from .models import Scope


class ReadOnlyContextHost:
    """Minimal host for safe standalone/public-beta cognition.

    It reads current context only. It cannot execute actions, schedule work,
    notify users, write back, or claim historical-memory ownership.
    """

    def __init__(self, root: str, *, context_file: Optional[str] = None, max_bytes: int = 262144):
        self.root = Path(root).expanduser().resolve()
        self.context_file = Path(context_file).expanduser().resolve() if context_file else None
        self.max_bytes = int(max_bytes)
        if self.max_bytes < 1024 or self.max_bytes > 4 * 1024 * 1024:
            raise ValidationError("max_bytes must be between 1024 and 4194304")
        if self.context_file is not None and not self.context_file.is_file():
            raise ValidationError(f"context file does not exist: {self.context_file}")

    def _canonical_context_path(self, scope: Scope) -> Optional[Path]:
        if self.context_file is not None:
            return self.context_file
        report = inspect_host(str(self.root))
        if report.mode == HostMode.AI_VERSE_OS_V2:
            if scope.is_operator:
                candidate = self.root / "operator" / "context" / "CURRENT.md"
            else:
                candidate = self.root / "workspaces" / str(scope.workspace_id) / "context" / "CURRENT.md"
            return candidate if candidate.is_file() else None
        candidate = self.root / "CURRENT.md"
        return candidate if candidate.is_file() else None

    def _read_text(self, path: Path) -> str:
        size = path.stat().st_size
        if size > self.max_bytes:
            raise ValidationError(
                f"context file exceeds read-only host byte budget ({size} > {self.max_bytes}): {path}"
            )
        return path.read_text(encoding="utf-8")

    def read_context(self, scope: str) -> Dict[str, Any]:
        scoped = Scope(scope)
        path = self._canonical_context_path(scoped)
        if path is None:
            return {
                "scope": scoped.value,
                "current_context": "",
                "source": None,
                "note": "No current-context file was supplied or discovered; Brain will not invent current state.",
            }
        return {
            "scope": scoped.value,
            "current_context": self._read_text(path),
            "source": str(path),
            "read_only": True,
        }

    def retrieve_history(self, query: str, scope: str) -> Iterable[Dict[str, Any]]:
        Scope(scope)
        return []

    def list_capabilities(self, scope: str) -> Iterable[Dict[str, Any]]:
        Scope(scope)
        return []

    def list_connections(self, scope: str) -> Iterable[Dict[str, Any]]:
        Scope(scope)
        return []

    def request_action(self, request: Dict[str, Any]) -> Dict[str, Any]:
        raise PermissionDenied("ReadOnlyContextHost cannot execute actions")

    def request_evaluation(self, request: Dict[str, Any]) -> Dict[str, Any]:
        raise PermissionDenied("ReadOnlyContextHost cannot execute evaluations")

    def schedule_trigger(self, trigger: Dict[str, Any]) -> Dict[str, Any]:
        raise PermissionDenied("ReadOnlyContextHost does not own a scheduler")

    def cancel_trigger(self, trigger_id: str) -> None:
        raise PermissionDenied("ReadOnlyContextHost does not own a scheduler")

    def notify_user(self, notification: Dict[str, Any]) -> None:
        raise PermissionDenied("ReadOnlyContextHost cannot notify users")

    def write_route(self, classification: str, payload: Dict[str, Any], scope: str) -> Optional[str]:
        Scope(scope)
        raise PermissionDenied("ReadOnlyContextHost is read-only and cannot write routed state")
