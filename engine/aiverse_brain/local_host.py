from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
from typing import Any, Dict, Iterable, Optional

from .errors import PermissionDenied, ValidationError
from .integration import HostMode, inspect_host
from .models import Scope


class ReadOnlyContextHost:
    """Minimal host for safe standalone/public-beta cognition.

    It reads current context only. It cannot execute actions, schedule work,
    notify users, write back, or claim historical-memory ownership.

    On a compatible AI-Verse OS v2 host, current context is always resolved
    through the OS ownership-aware current-context contract. Brain never falls
    back to a raw OS CURRENT.md read when that contract is missing or broken.
    """

    def __init__(self, root: str, *, context_file: Optional[str] = None, max_bytes: int = 262144):
        self.root = Path(root).expanduser().resolve()
        self.context_file = Path(context_file).expanduser().resolve() if context_file else None
        self.max_bytes = int(max_bytes)
        if self.max_bytes < 1024 or self.max_bytes > 4 * 1024 * 1024:
            raise ValidationError("max_bytes must be between 1024 and 4194304")
        if self.context_file is not None and not self.context_file.is_file():
            raise ValidationError(f"context file does not exist: {self.context_file}")

        report = inspect_host(str(self.root))
        if report.mode == HostMode.AI_VERSE_OS_V2 and self.context_file is not None:
            raise ValidationError(
                "--context-file cannot override a compatible AI-Verse OS current-context resolver"
            )

    def _canonical_context_path(self, scope: Scope) -> Optional[Path]:
        if self.context_file is not None:
            return self.context_file
        candidate = self.root / "CURRENT.md"
        return candidate if candidate.is_file() else None

    def _read_text(self, path: Path) -> str:
        size = path.stat().st_size
        if size > self.max_bytes:
            raise ValidationError(
                f"context file exceeds read-only host byte budget ({size} > {self.max_bytes}): {path}"
            )
        return path.read_text(encoding="utf-8")

    def _read_ai_verse_os_context(self, scope: Scope) -> Dict[str, Any]:
        resolver = self.root / "scripts" / "current-context.mjs"
        if not resolver.is_file() or resolver.is_symlink():
            raise ValidationError(
                "compatible AI-Verse OS requires scripts/current-context.mjs; "
                "Brain will not fall back to raw CURRENT.md"
            )

        node = shutil.which("node")
        if not node:
            raise ValidationError(
                "compatible AI-Verse OS current-context resolver requires Node.js; "
                "Brain will not fall back to raw CURRENT.md"
            )

        try:
            completed = subprocess.run(
                [
                    node,
                    str(resolver),
                    "read",
                    "--root",
                    str(self.root),
                    "--scope",
                    scope.value,
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValidationError(f"AI-Verse OS current-context resolver failed: {exc}") from exc

        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "resolver returned non-zero").strip()
            if len(detail) > 512:
                detail = detail[:512] + "..."
            raise ValidationError(f"AI-Verse OS current-context resolver failed: {detail}")

        try:
            payload = json.loads(completed.stdout)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValidationError("AI-Verse OS current-context resolver returned invalid JSON") from exc

        if not isinstance(payload, dict):
            raise ValidationError("AI-Verse OS current-context resolver returned a non-object payload")
        if payload.get("scope") != scope.value:
            raise ValidationError("AI-Verse OS current-context resolver returned the wrong scope")
        if payload.get("direction_owner") not in {"os", "brain"}:
            raise ValidationError("AI-Verse OS current-context resolver returned invalid direction ownership")
        current_context = payload.get("current_context")
        if not isinstance(current_context, str):
            raise ValidationError("AI-Verse OS current-context resolver returned invalid current_context")
        context_bytes = len(current_context.encode("utf-8"))
        if context_bytes > self.max_bytes:
            raise ValidationError(
                "resolved current context exceeds read-only host byte budget "
                f"({context_bytes} > {self.max_bytes})"
            )

        source = payload.get("source")
        if source is not None and not isinstance(source, str):
            raise ValidationError("AI-Verse OS current-context resolver returned invalid source")

        return {
            **payload,
            "scope": scope.value,
            "current_context": current_context,
            "source": source,
            "read_only": True,
            "context_resolver": "ai-verse-os:scripts/current-context.mjs",
        }

    def read_context(self, scope: str) -> Dict[str, Any]:
        scoped = Scope(scope)
        report = inspect_host(str(self.root))
        if report.mode == HostMode.AI_VERSE_OS_V2:
            return self._read_ai_verse_os_context(scoped)

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
