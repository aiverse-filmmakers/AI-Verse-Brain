from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Dict, List, Tuple

from ._version import INSTALLATION_SCHEMA_VERSION, STATE_SCHEMA_VERSION, __version__
from .errors import ValidationError
from .installation import installation_marker_path
from .write_gate import require_write_ready


def _version_tuple(value: str) -> Tuple[int, ...]:
    if not isinstance(value, str) or not value:
        raise ValidationError("state schema version must be a non-empty string")
    parts = value.split(".")
    if not all(part.isdigit() for part in parts):
        raise ValidationError(f"invalid state schema version: {value!r}")
    return tuple(int(part) for part in parts)


@dataclass(frozen=True)
class MigrationPlan:
    safe_to_apply: bool
    needed: bool
    state_from: str
    state_to: str
    package_from: str
    package_to: str
    operations: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "safe_to_apply": self.safe_to_apply,
            "needed": self.needed,
            "state_from": self.state_from,
            "state_to": self.state_to,
            "package_from": self.package_from,
            "package_to": self.package_to,
            "operations": list(self.operations),
            "blockers": list(self.blockers),
        }


def _raw_marker(root: str) -> Tuple[Path, Dict[str, Any]]:
    marker_path = installation_marker_path(root)
    if marker_path is None or not marker_path.is_file():
        raise ValidationError("Brain is not initialized; no installation marker exists")
    try:
        data = json.loads(marker_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValidationError(f"cannot parse installation marker {marker_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValidationError("installation marker must be a JSON object")
    return marker_path, data


def plan_migration(root: str) -> MigrationPlan:
    _, marker = _raw_marker(root)
    if marker.get("schema_version") != INSTALLATION_SCHEMA_VERSION:
        return MigrationPlan(
            False,
            True,
            str(marker.get("state_schema_version", "unknown")),
            STATE_SCHEMA_VERSION,
            str(marker.get("package_version", "unknown")),
            __version__,
            blockers=[
                f"unsupported installation marker schema {marker.get('schema_version')!r}; "
                f"expected {INSTALLATION_SCHEMA_VERSION!r}"
            ],
        )
    old_state = str(marker.get("state_schema_version", ""))
    old_package = str(marker.get("package_version", ""))
    current = _version_tuple(STATE_SCHEMA_VERSION)
    previous = _version_tuple(old_state)
    if previous > current:
        return MigrationPlan(
            False,
            True,
            old_state,
            STATE_SCHEMA_VERSION,
            old_package,
            __version__,
            blockers=["installed Brain state is newer than this package; downgrade/upgrade mismatch must be resolved first"],
        )
    if previous < current:
        return MigrationPlan(
            False,
            True,
            old_state,
            STATE_SCHEMA_VERSION,
            old_package,
            __version__,
            blockers=[
                f"no registered state migration path from {old_state} to {STATE_SCHEMA_VERSION}; "
                "Brain refuses destructive or guessed migrations"
            ],
        )

    operations: List[str] = []
    if old_package != __version__:
        operations.append("refresh installation package_version metadata")
    return MigrationPlan(
        True,
        bool(operations),
        old_state,
        STATE_SCHEMA_VERSION,
        old_package,
        __version__,
        operations=operations,
    )


def _atomic_marker_write(path: Path, data: Dict[str, Any]) -> None:
    fd, temp_name = tempfile.mkstemp(prefix=".migration-", suffix=".tmp", dir=str(path.parent))
    try:
        try:
            os.chmod(temp_name, 0o600)
        except OSError:
            pass
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def apply_migration(root: str) -> MigrationPlan:
    require_write_ready(root)
    plan = plan_migration(root)
    if not plan.safe_to_apply:
        raise ValidationError("Brain migration blocked: " + "; ".join(plan.blockers))
    if not plan.needed:
        return plan
    marker_path, marker = _raw_marker(root)
    marker["package_version"] = __version__
    _atomic_marker_write(marker_path, marker)
    return plan_migration(root)
