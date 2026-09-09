from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Dict, Optional

from .policy import AttentionPolicy, ProactivityLevel
from .ranking import NotificationClass
from .runtime_lock import RuntimeKeyLock


@dataclass(frozen=True)
class AttentionDecision:
    allowed: bool
    notification: NotificationClass
    reason: str
    remaining_interruptions_today: int


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


class AttentionLedger:
    """Disposable delivery ledger. Canonical dismissal/rejection state remains on Brain objects."""

    def __init__(self, runtime_dir: Path):
        self.directory = Path(runtime_dir) / "attention"
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = RuntimeKeyLock(runtime_dir, namespace="attention")

    @staticmethod
    def _scope_key(scope: str) -> str:
        return hashlib.sha256(scope.encode("utf-8")).hexdigest()

    def _path(self, scope: str) -> Path:
        return self.directory / f"{self._scope_key(scope)}.json"

    def _read(self, scope: str) -> Dict[str, Any]:
        path = self._path(scope)
        if not path.exists():
            return {"scope": scope, "fingerprints": {}, "days": {}, "sessions": {}}
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("scope") != scope:
            return {"scope": scope, "fingerprints": {}, "days": {}, "sessions": {}}
        data.setdefault("fingerprints", {})
        data.setdefault("days", {})
        data.setdefault("sessions", {})
        return data

    def _write(self, scope: str, data: Dict[str, Any]) -> None:
        path = self._path(scope)
        fd, temp_name = tempfile.mkstemp(prefix=".attention-", suffix=".tmp", dir=str(self.directory))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def claim_notification(
        self,
        *,
        scope: str,
        fingerprint: str,
        notification: NotificationClass,
        policy: AttentionPolicy,
        proactivity: ProactivityLevel,
        session_id: Optional[str] = None,
        now: Optional[datetime] = None,
        unsolicited: bool = True,
    ) -> AttentionDecision:
        if not fingerprint:
            raise ValueError("attention fingerprint is required")
        now = (now or _utc_now()).astimezone(timezone.utc)
        if notification in {NotificationClass.DROP, NotificationClass.STORE}:
            return AttentionDecision(False, notification, "not_user_facing", policy.max_interruptions_per_day)
        if unsolicited and proactivity <= ProactivityLevel.P0_REACTIVE:
            return AttentionDecision(False, NotificationClass.STORE, "reactive_mode", policy.max_interruptions_per_day)
        if unsolicited and proactivity == ProactivityLevel.P1_OBSERVANT:
            return AttentionDecision(False, NotificationClass.STORE, "observant_mode", policy.max_interruptions_per_day)

        day_key = now.date().isoformat()
        session_key = session_id or "__no_session__"
        with self.lock.acquire(scope):
            data = self._read(scope)
            day = data["days"].setdefault(day_key, {"interruptions": 0})
            session = data["sessions"].setdefault(session_key, {"count": 0, "updated_at": _iso(now)})
            last = data["fingerprints"].get(fingerprint)
            if last:
                elapsed = (now - _parse(last["last_notified_at"])).total_seconds()
                if elapsed < policy.notification_cooldown_hours * 3600:
                    remaining = max(0, policy.max_interruptions_per_day - int(day.get("interruptions", 0)))
                    return AttentionDecision(False, NotificationClass.STORE, "notification_cooldown", remaining)
            if int(session.get("count", 0)) >= policy.max_proactive_items_per_session:
                remaining = max(0, policy.max_interruptions_per_day - int(day.get("interruptions", 0)))
                return AttentionDecision(False, NotificationClass.STORE, "session_attention_budget", remaining)

            actual = notification
            interruptions = int(day.get("interruptions", 0))
            if actual == NotificationClass.INTERRUPT and interruptions >= policy.max_interruptions_per_day:
                actual = NotificationClass.SURFACE

            session["count"] = int(session.get("count", 0)) + 1
            session["updated_at"] = _iso(now)
            if actual == NotificationClass.INTERRUPT:
                day["interruptions"] = interruptions + 1
            data["fingerprints"][fingerprint] = {
                "last_notified_at": _iso(now),
                "notification": actual.value,
                "session_id": session_id,
            }
            # Keep runtime ledgers bounded. The canonical object lifecycle owns long history.
            for key in sorted(data["days"].keys())[:-14]:
                data["days"].pop(key, None)
            if len(data["sessions"]) > 100:
                oldest = sorted(data["sessions"].items(), key=lambda item: item[1].get("updated_at", ""))[:-100]
                for key, _ in oldest:
                    data["sessions"].pop(key, None)
            self._write(scope, data)
            remaining = max(0, policy.max_interruptions_per_day - int(day.get("interruptions", 0)))
            reason = "interrupt_budget_downgrade" if actual != notification else "allowed"
            return AttentionDecision(True, actual, reason, remaining)
