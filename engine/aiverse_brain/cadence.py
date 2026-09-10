from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any, Dict, List
from uuid import uuid4

from .errors import DuplicateTrigger
from .models import Scope, utc_now

TRIGGER_TYPES = {
    "explicit", "session_start", "session_end", "scheduled_orientation",
    "scheduled_review", "event", "objective_wake", "blocker_resolution",
    "external_change", "manual_recovery",
}


@dataclass(frozen=True)
class Trigger:
    trigger_type: str
    scope: Scope
    idempotency_key: str
    trigger_id: str = field(default_factory=lambda: str(uuid4()))
    occurred_at: str = field(default_factory=utc_now)
    source_refs: List[str] = field(default_factory=list)
    payload_refs: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.trigger_type not in TRIGGER_TYPES:
            raise ValueError(f"unknown trigger type: {self.trigger_type}")
        if not self.idempotency_key:
            raise ValueError("idempotency_key is required")


class TriggerLedger:
    """Disposable runtime ledger. It prevents duplicate ticks; it is not canonical intent state."""

    def __init__(self, runtime_dir: Path):
        self.runtime_dir = Path(runtime_dir)
        self.root = self.runtime_dir.parent.parent
        self.dir = self.runtime_dir / "trigger-receipts"

    def _prepare_write(self) -> None:
        from .write_gate import require_write_ready
        require_write_ready(str(self.root))
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.dir / f"{digest}.json"

    def claim(self, trigger: Trigger) -> Path:
        self._prepare_write()
        path = self._path(trigger.idempotency_key)
        payload: Dict[str, Any] = {
            "trigger_id": trigger.trigger_id,
            "trigger_type": trigger.trigger_type,
            "scope": trigger.scope.value,
            "idempotency_key": trigger.idempotency_key,
            "claimed_at": utc_now(),
            "status": "claimed",
        }
        try:
            fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as exc:
            raise DuplicateTrigger(trigger.idempotency_key) from exc
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
        return path

    def complete(self, trigger: Trigger) -> None:
        self._prepare_write()
        path = self._path(trigger.idempotency_key)
        data = json.loads(path.read_text(encoding="utf-8"))
        data["status"] = "completed"
        data["completed_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(str(temp), str(path))

    def recover_stale_claim(self, idempotency_key: str, *, minimum_age_seconds: int = 300) -> bool:
        """Explicit recovery only. Completed receipts are never cleared by this method."""
        from .write_gate import require_write_ready
        require_write_ready(str(self.root))
        path = self._path(idempotency_key)
        if not path.exists():
            return False
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("status") != "claimed":
            return False
        age = time.time() - path.stat().st_mtime
        if age < minimum_age_seconds:
            return False
        path.unlink()
        return True
