from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Dict
from uuid import uuid4

from .authority import AuthorityTier, require_user_authority
from .errors import ValidationError
from .models import Scope, utc_now
from .runtime_lock import RuntimeKeyLock


@dataclass(frozen=True)
class StrategyRestorationResult:
    current_strategy_id: str
    restored_strategy_id: str
    transaction_id: str
    state: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "current_strategy_id": self.current_strategy_id,
            "restored_strategy_id": self.restored_strategy_id,
            "transaction_id": self.transaction_id,
            "state": self.state,
        }


class StrategyRevisionService:
    """Version-linked strategy promotion and known-good restoration."""

    def __init__(self, controller: Any):
        self.controller = controller
        self.lock = RuntimeKeyLock(controller.layout.runtime_dir, namespace="strategy-revision")

    def _tx_dir(self, scope: str) -> Path:
        return self.controller.layout.state_root(Scope(scope)) / "strategy-restorations"

    @staticmethod
    def _write(path: Path, data: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=".strategy-tx-", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2, sort_keys=True)
                handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name): os.unlink(temp_name)

    def link_previous(self, scope: str, candidate_id: str, previous_strategy_id: str, *, actor: str = "brain:evolution"):
        candidate = self.controller.store.load("strategy_rule", scope, candidate_id)
        previous = self.controller.store.load("strategy_rule", scope, previous_strategy_id)
        if candidate.status != "CANDIDATE": raise ValidationError("only a CANDIDATE strategy can link a prior revision")
        if previous.status != "ACTIVE": raise ValidationError("previous strategy revision must be ACTIVE")
        if candidate.id == previous.id: raise ValidationError("strategy candidate cannot point to itself")
        expected = candidate.revision
        candidate.payload["previous_revision_ref"] = previous.id
        candidate.payload["previous_revision_snapshot"] = {
            "id": previous.id, "revision": previous.revision, "payload": dict(previous.payload),
        }
        candidate.updated_by = actor
        return self.controller.store.save(candidate, expected_revision=expected)

    def promote_revision(self, scope: str, candidate_id: str, *, source: AuthorityTier, actor: str = "brain:evolution"):
        candidate = self.controller.store.load("strategy_rule", scope, candidate_id)
        previous_id = candidate.payload.get("previous_revision_ref")
        if not previous_id:
            return self.controller.transition("strategy_rule", scope, candidate_id, "ACTIVE", source=source, actor=actor)
        with self.lock.acquire(f"{scope}|{candidate_id}|promote"):
            candidate = self.controller.store.load("strategy_rule", scope, candidate_id)
            previous = self.controller.store.load("strategy_rule", scope, str(previous_id))
            if candidate.status == "ACTIVE" and previous.status == "RETIRED": return candidate
            if candidate.status != "CANDIDATE" or previous.status != "ACTIVE":
                raise ValidationError("strategy promotion revision chain is no longer current")
            activated = self.controller.transition("strategy_rule", scope, candidate.id, "ACTIVE", source=source, actor=actor)
            try:
                self.controller.transition(
                    "strategy_rule", scope, previous.id, "RETIRED",
                    source=AuthorityTier.VALIDATED_STRATEGY, actor=actor,
                )
            except Exception:
                self.controller.transition(
                    "strategy_rule", scope, activated.id, "RETIRED",
                    source=AuthorityTier.VALIDATED_STRATEGY, actor="brain:promotion-recovery",
                )
                raise
            return self.controller.store.load("strategy_rule", scope, candidate.id)

    def rollback(
        self, scope: str, current_strategy_id: str, *,
        source: AuthorityTier = AuthorityTier.EXPLICIT_USER, actor: str = "user",
    ) -> StrategyRestorationResult:
        require_user_authority(source, "strategy rollback/restoration")
        with self.lock.acquire(f"{scope}|{current_strategy_id}|rollback"):
            current = self.controller.store.load("strategy_rule", scope, current_strategy_id)
            previous_id = current.payload.get("previous_revision_ref")
            if not previous_id: raise ValidationError("strategy has no known-good previous revision to restore")
            previous = self.controller.store.load("strategy_rule", scope, str(previous_id))
            tx_id = "restore_" + uuid4().hex
            path = self._tx_dir(scope) / f"{tx_id}.json"
            tx = {
                "schema_version": "1.0", "transaction_id": tx_id, "scope": scope,
                "current_strategy_id": current.id, "previous_strategy_id": previous.id,
                "state": "prepared", "created_at": utc_now(),
            }
            self._write(path, tx)
            if current.status == "ROLLED_BACK" and previous.status == "ACTIVE":
                tx["state"] = "complete"; self._write(path, tx)
                return StrategyRestorationResult(current.id, previous.id, tx_id, "complete")
            if current.status != "ACTIVE": raise ValidationError("only the ACTIVE strategy revision can be rolled back")
            if previous.status != "RETIRED": raise ValidationError("previous revision is not in restorable RETIRED state")
            restored = self.controller.transition(
                "strategy_rule", scope, previous.id, "ACTIVE",
                source=AuthorityTier.EXPLICIT_USER, actor=actor,
            )
            tx["state"] = "previous_restored"; tx["restored_revision"] = restored.revision; self._write(path, tx)
            try:
                self.controller.transition(
                    "strategy_rule", scope, current.id, "ROLLED_BACK",
                    source=AuthorityTier.EXPLICIT_USER, actor=actor,
                )
            except Exception:
                tx["state"] = "previous_restored_current_cleanup_required"; self._write(path, tx)
                raise
            tx["state"] = "complete"; tx["completed_at"] = utc_now(); self._write(path, tx)
            return StrategyRestorationResult(current.id, previous.id, tx_id, "complete")

    def reconcile(self, scope: str, transaction_id: str, *, actor: str = "brain:recovery") -> StrategyRestorationResult:
        path = self._tx_dir(scope) / f"{transaction_id}.json"
        if not path.is_file(): raise ValidationError("unknown strategy restoration transaction")
        data = json.loads(path.read_text(encoding="utf-8"))
        current = self.controller.store.load("strategy_rule", scope, str(data["current_strategy_id"]))
        previous = self.controller.store.load("strategy_rule", scope, str(data["previous_strategy_id"]))
        if previous.status == "ACTIVE" and current.status == "ROLLED_BACK":
            data["state"] = "complete"; data["completed_at"] = utc_now(); self._write(path, data)
            return StrategyRestorationResult(current.id, previous.id, transaction_id, "complete")
        if previous.status == "ACTIVE" and current.status == "ACTIVE":
            self.controller.transition(
                "strategy_rule", scope, current.id, "ROLLED_BACK",
                source=AuthorityTier.EXPLICIT_USER, actor=actor,
            )
            data["state"] = "complete"; data["completed_at"] = utc_now(); self._write(path, data)
            return StrategyRestorationResult(current.id, previous.id, transaction_id, "complete")
        raise ValidationError("strategy restoration transaction requires operator review")
