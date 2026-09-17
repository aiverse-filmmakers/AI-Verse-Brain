from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from ._version import INSTALLATION_SCHEMA_VERSION, STATE_SCHEMA_VERSION, __version__
from .errors import ValidationError
from .integration import HostMode, inspect_host
from .models import BrainObject, Scope, utc_now
from .path_safety import safe_host_path
from .validation import validate_object

_KIND_DIR = {
    "intent": "intent", "practice": "practices", "gap": "gaps", "opportunity": "opportunities",
    "initiative": "initiatives", "objective": "objectives", "goal": "goals",
    "model_belief": "models", "evaluation": "evaluations", "learning": "learning",
    "learning_candidate": "learning-candidates", "strategy_rule": "strategies", "policy": "policies",
}


@dataclass(frozen=True)
class AdoptionPlan:
    root: str
    needed: bool
    safe_to_apply: bool
    source: Optional[str] = None
    destination: Optional[str] = None
    blockers: List[str] = field(default_factory=list)
    operations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "root": self.root, "needed": self.needed, "safe_to_apply": self.safe_to_apply,
            "source": self.source, "destination": self.destination,
            "blockers": list(self.blockers), "operations": list(self.operations),
            "strategic_handover": False,
        }


@dataclass(frozen=True)
class AdoptionResult:
    plan: AdoptionPlan
    transaction_id: Optional[str]
    state: str
    retired_source: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan": self.plan.to_dict(), "transaction_id": self.transaction_id,
            "state": self.state, "retired_source": self.retired_source,
            "strategic_handover": False,
        }


def _tx_root(root: Path) -> Path:
    return safe_host_path(root, ".aiverse", "brain-adoption")


def _tx_path(root: Path) -> Path:
    return safe_host_path(root, ".aiverse", "brain-adoption", "transaction.json")


def _adoption_paths(root: Path) -> Tuple[Path, Path, Path]:
    return (
        safe_host_path(root, ".ai-verse-brain"),
        safe_host_path(root, "operator", "brain"),
        _tx_path(root),
    )


def _atomic_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".brain-adoption-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name): os.unlink(temp_name)


def _read_marker(source: Path) -> Dict[str, Any]:
    marker = source / "installation.json"
    if not marker.is_file() or marker.is_symlink():
        raise ValidationError("standalone Brain state has no safe installation.json marker")
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValidationError(f"cannot parse standalone Brain installation marker: {exc}") from exc
    if not isinstance(data, dict): raise ValidationError("standalone installation marker must be an object")
    if data.get("schema_version") != INSTALLATION_SCHEMA_VERSION:
        raise ValidationError("standalone installation marker schema is unsupported")
    if data.get("state_schema_version") != STATE_SCHEMA_VERSION:
        raise ValidationError(
            f"standalone Brain state schema {data.get('state_schema_version')!r} requires migration before adoption"
        )
    if data.get("mode") != HostMode.STANDALONE.value:
        raise ValidationError("source Brain installation is not marked standalone")
    return data


def _validate_source(source: Path) -> None:
    _read_marker(source)
    for kind, dirname in _KIND_DIR.items():
        directory = source / dirname
        if not directory.exists(): continue
        if directory.is_symlink() or not directory.is_dir():
            raise ValidationError(f"unsafe standalone Brain kind directory: {directory}")
        for path in directory.glob("*.json"):
            if path.is_symlink() or not path.is_file():
                raise ValidationError(f"unsafe standalone Brain object: {path}")
            try:
                obj = BrainObject.from_dict(json.loads(path.read_text(encoding="utf-8")))
            except Exception as exc:
                raise ValidationError(f"invalid standalone Brain object {path}: {exc}") from exc
            if obj.scope != Scope("operator") or obj.kind != kind:
                raise ValidationError(f"standalone Brain object owner mismatch: {path}")
            validate_object(obj.kind, obj.status, obj.payload)


def plan_standalone_adoption(root: str) -> AdoptionPlan:
    base = Path(root).expanduser().resolve()
    host = inspect_host(str(base))
    if host.mode != HostMode.AI_VERSE_OS_V2:
        return AdoptionPlan(str(base), False, host.mode == HostMode.STANDALONE)
    try:
        source, destination, tx_path = _adoption_paths(base)
    except ValidationError as exc:
        return AdoptionPlan(str(base), True, False, blockers=[str(exc)])

    if tx_path.exists():
        if tx_path.is_symlink() or not tx_path.is_file():
            return AdoptionPlan(str(base), True, False, str(source), str(destination), ["unsafe adoption transaction path"])
        try: tx = json.loads(tx_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return AdoptionPlan(str(base), True, False, str(source), str(destination), [f"unreadable adoption transaction: {exc}"])
        if tx.get("state") == "complete":
            return AdoptionPlan(str(base), False, True, str(source), str(destination))
        return AdoptionPlan(
            str(base), True, True, str(source), str(destination),
            operations=["resume existing standalone-to-native adoption transaction"],
        )
    if not source.exists():
        return AdoptionPlan(str(base), False, True, str(source), str(destination))
    blockers: List[str] = []
    try: _validate_source(source)
    except Exception as exc: blockers.append(str(exc))
    if destination.exists() and any(destination.iterdir()):
        blockers.append("native operator/brain already contains state; adoption would create competing truth")
    return AdoptionPlan(
        str(base), True, not blockers, str(source), str(destination), blockers,
        [
            "validate standalone canonical Brain state",
            "retire standalone writable authority",
            "stage verified native state",
            "rewrite Brain installation mode/provenance metadata",
            "activate native operator/brain state",
            "retain old source as read-only provenance",
        ],
    )


def _copy_state(source: Path, staging: Path) -> None:
    if staging.exists(): shutil.rmtree(staging)
    shutil.copytree(source, staging, symlinks=False)
    runtime = staging / "runtime"
    if runtime.exists(): shutil.rmtree(runtime)
    marker = _read_marker(staging)
    marker["mode"] = HostMode.AI_VERSE_OS_V2.value
    marker["package_version"] = __version__
    marker["adopted_from"] = "standalone"
    marker["adopted_at"] = utc_now()
    _atomic_json(staging / "installation.json", marker)


def apply_standalone_adoption(root: str) -> AdoptionResult:
    base = Path(root).expanduser().resolve()
    plan = plan_standalone_adoption(str(base))
    if not plan.safe_to_apply:
        raise ValidationError("Brain standalone adoption blocked: " + "; ".join(plan.blockers))
    if not plan.needed: return AdoptionResult(plan, None, "not-needed")

    # Revalidate every Brain-owned adoption destination before mutation. This
    # prevents a native parent or transaction directory from redirecting the
    # migration outside the selected host root.
    source, destination, tx_path = _adoption_paths(base)
    tx_root = _tx_root(base)
    tx_root.mkdir(parents=True, exist_ok=True)
    tx_path = safe_host_path(base, ".aiverse", "brain-adoption", "transaction.json")
    if tx_path.exists():
        if tx_path.is_symlink() or not tx_path.is_file():
            raise ValidationError("unsafe adoption transaction path")
        tx = json.loads(tx_path.read_text(encoding="utf-8"))
    else:
        tx = {
            "schema_version": "1.0", "transaction_id": "adopt_" + uuid4().hex,
            "state": "prepared", "source": ".ai-verse-brain",
            "destination": "operator/brain", "created_at": utc_now(),
        }
        _atomic_json(tx_path, tx)
    tx_id = str(tx["transaction_id"])
    retired = safe_host_path(base, ".aiverse", "brain-adoption", f"retired-{tx_id}")
    staging = safe_host_path(base, ".aiverse", "brain-adoption", f"staging-{tx_id}")

    if tx["state"] == "prepared":
        source = safe_host_path(base, ".ai-verse-brain")
        if source.exists():
            if retired.exists(): raise ValidationError("source and retired snapshot both exist; operator review required")
            os.replace(source, retired)
        elif not retired.exists():
            raise ValidationError("standalone Brain source disappeared before retirement")
        tx["state"] = "source_retired"
        tx["retired_source"] = retired.relative_to(base).as_posix()
        _atomic_json(safe_host_path(base, ".aiverse", "brain-adoption", "transaction.json"), tx)

    if tx["state"] == "source_retired":
        retired = safe_host_path(base, ".aiverse", "brain-adoption", f"retired-{tx_id}", require_directory=True)
        staging = safe_host_path(base, ".aiverse", "brain-adoption", f"staging-{tx_id}")
        _validate_source(retired)
        _copy_state(retired, staging)
        tx["state"] = "staged"
        _atomic_json(safe_host_path(base, ".aiverse", "brain-adoption", "transaction.json"), tx)

    if tx["state"] == "staged":
        destination = safe_host_path(base, "operator", "brain")
        staging = safe_host_path(base, ".aiverse", "brain-adoption", f"staging-{tx_id}", require_directory=True)
        if destination.exists() and any(destination.iterdir()):
            raise ValidationError("native operator/brain became non-empty during adoption")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists(): destination.rmdir()
        destination = safe_host_path(base, "operator", "brain")
        os.replace(staging, destination)
        runtime = safe_host_path(base, "runtime", "ai-verse-brain")
        runtime.mkdir(parents=True, exist_ok=True)
        tx["state"] = "complete"; tx["completed_at"] = utc_now()
        _atomic_json(safe_host_path(base, ".aiverse", "brain-adoption", "transaction.json"), tx)

    if tx["state"] != "complete":
        raise ValidationError(f"unsupported adoption transaction state: {tx['state']}")
    retired = safe_host_path(base, ".aiverse", "brain-adoption", f"retired-{tx_id}")
    if retired.exists():
        for path in retired.rglob("*"):
            try:
                if path.is_file(): os.chmod(path, 0o400)
            except OSError: pass
        try: os.chmod(retired, 0o500)
        except OSError: pass
    return AdoptionResult(
        plan_standalone_adoption(str(base)), tx_id, "complete",
        retired.relative_to(base).as_posix() if retired.exists() else None,
    )
