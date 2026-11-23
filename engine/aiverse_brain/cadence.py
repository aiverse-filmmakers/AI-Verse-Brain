from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional
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


# Liveness is judged only by the receipt's age, and a tick with several reasoner
# calls can take many minutes, so the default wait before a claim counts as
# abandoned is one hour (FL-28 review).
DEFAULT_STALE_CLAIM_SECONDS = 3600


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
            # A receipt still marked "claimed" means an earlier run crashed mid tick. Brain
            # never replays that automatically (it may have done part of the work), so the
            # error names the explicit recovery command instead of failing silently (FL-28).
            status = self._read_status(path)
            if status in {"claimed", "unreadable"}:
                raise DuplicateTrigger(
                    f"{trigger.idempotency_key}: an earlier run claimed this slot and did not finish. "
                    "If no Brain run is still active, free it with "
                    f"`ai-verse-brain recover-trigger <root> --key {trigger.idempotency_key}`"
                ) from exc
            raise DuplicateTrigger(trigger.idempotency_key) from exc
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
        return path

    def complete(self, trigger: Trigger) -> None:
        self._prepare_write()
        path = self._path(trigger.idempotency_key)
        data = json.loads(path.read_text(encoding="utf-8"))
        data["status"] = "completed"
        data["completed_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        temp = path.with_suffix(".tmp")
        with temp.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(data, indent=2, sort_keys=True) + "\n")
        os.replace(str(temp), str(path))

    @staticmethod
    def _read_status(path: Path) -> Optional[str]:
        """Status of a receipt, None if absent, "unreadable" if empty or damaged.

        claim() creates the file before writing it, so a crash in between leaves an
        empty or partial receipt. That is an unfinished claim too and must be
        recoverable rather than an error (FL-28 review).
        """
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            return "unreadable"
        if not isinstance(data, dict):
            return "unreadable"
        return str(data.get("status"))

    def claim_status(self, idempotency_key: str) -> Optional[str]:
        """Read only: "claimed", "completed", "unreadable", another status, or None if absent."""
        return self._read_status(self._path(idempotency_key))

    def recover_stale_claim(self, idempotency_key: str, *, minimum_age_seconds: int = DEFAULT_STALE_CLAIM_SECONDS) -> bool:
        """Explicit recovery only. Completed receipts are never cleared by this method."""
        from .write_gate import require_write_ready
        require_write_ready(str(self.root))
        path = self._path(idempotency_key)
        if self._read_status(path) not in {"claimed", "unreadable"}:
            return False
        try:
            age = time.time() - path.stat().st_mtime
        except FileNotFoundError:
            return False
        if age < minimum_age_seconds:
            return False
        # Re-check right before removing, so a run that finished in the meantime
        # (complete() replaces the file) keeps its completed receipt.
        if self._read_status(path) not in {"claimed", "unreadable"}:
            return False
        path.unlink()
        return True
