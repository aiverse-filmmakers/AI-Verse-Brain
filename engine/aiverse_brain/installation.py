from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from ._version import INSTALLATION_SCHEMA_VERSION, STATE_SCHEMA_VERSION, __version__
from .errors import ValidationError
from .extension_registry import attach_brain
from .integration import HostMode, inspect_host, native_registration_blockers
from .models import utc_now

PACKAGE_VERSION = __version__


def _version_tuple(value: str) -> Tuple[int, ...]:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError("schema version must be a non-empty string")
    parts = value.strip().split(".")
    if not all(part.isdigit() for part in parts):
        raise ValidationError(f"invalid schema version: {value!r}")
    return tuple(int(part) for part in parts)


def _mode_paths(root: Path, mode: HostMode) -> Tuple[Path, Path]:
    if mode == HostMode.STANDALONE:
        state = root / ".ai-verse-brain"
        return state, state / "runtime"
    if mode == HostMode.AI_VERSE_OS_V2:
        return root / "operator" / "brain", root / "runtime" / "ai-verse-brain"
    raise ValidationError("incompatible AI-Verse host has no safe Brain initialization paths")


def installation_marker_path(root: str) -> Optional[Path]:
    base = Path(root).resolve()
    report = inspect_host(str(base))
    if report.mode == HostMode.INCOMPATIBLE_AI_VERSE:
        return None
    state, _ = _mode_paths(base, report.mode)
    return state / "installation.json"


def _validate_marker(data: Dict[str, Any], *, expected_mode: HostMode) -> None:
    required = {
        "schema_version", "state_schema_version", "package_version", "mode",
        "installation_id", "installed_at",
    }
    missing = sorted(required - set(data))
    if missing:
        raise ValidationError("installation marker missing fields: " + ", ".join(missing))
    if data["schema_version"] != INSTALLATION_SCHEMA_VERSION:
        raise ValidationError(
            f"unsupported installation marker schema {data['schema_version']!r}; expected {INSTALLATION_SCHEMA_VERSION}"
        )
    state_version = _version_tuple(str(data["state_schema_version"]))
    current = _version_tuple(STATE_SCHEMA_VERSION)
    if state_version > current:
        raise ValidationError(
            f"Brain state schema {data['state_schema_version']} is newer than this package supports ({STATE_SCHEMA_VERSION})"
        )
    if state_version < current:
        raise ValidationError(
            f"Brain state schema {data['state_schema_version']} requires an explicit migration to {STATE_SCHEMA_VERSION}"
        )
    if data["mode"] != expected_mode.value:
        raise ValidationError(
            f"installation marker mode {data['mode']!r} does not match detected host mode {expected_mode.value!r}"
        )
    if not isinstance(data["installation_id"], str) or not data["installation_id"].strip():
        raise ValidationError("installation_id must be non-empty")
    if not isinstance(data["installed_at"], str) or not data["installed_at"].strip():
        raise ValidationError("installed_at must be non-empty")


def read_installation_marker(root: str) -> Optional[Dict[str, Any]]:
    base = Path(root).resolve()
    report = inspect_host(str(base))
    if report.mode == HostMode.INCOMPATIBLE_AI_VERSE:
        return None
    state, _ = _mode_paths(base, report.mode)
    marker = state / "installation.json"
    if not marker.exists():
        return None
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValidationError(f"cannot parse installation marker {marker}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValidationError("installation marker must contain a JSON object")
    _validate_marker(data, expected_mode=report.mode)
    return data


@dataclass(frozen=True)
class InitPlan:
    root: str
    mode: HostMode
    safe_to_apply: bool
    state_root: Optional[str]
    runtime_root: Optional[str]
    creates: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    already_initialized: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "root": self.root,
            "mode": self.mode.value,
            "safe_to_apply": self.safe_to_apply,
            "state_root": self.state_root,
            "runtime_root": self.runtime_root,
            "creates": list(self.creates),
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "already_initialized": self.already_initialized,
            "state_schema_version": STATE_SCHEMA_VERSION,
            "package_version": PACKAGE_VERSION,
        }


@dataclass(frozen=True)
class InitResult:
    plan: InitPlan
    marker: Dict[str, Any]
    created: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "created": self.created,
            "plan": self.plan.to_dict(),
            "installation": dict(self.marker),
        }


def plan_init(root: str) -> InitPlan:
    base = Path(root).resolve()
    if not base.exists():
        return InitPlan(
            str(base), HostMode.STANDALONE, False, None, None,
            blockers=[f"target root does not exist: {base}"],
        )
    if not base.is_dir():
        return InitPlan(
            str(base), HostMode.STANDALONE, False, None, None,
            blockers=[f"target root is not a directory: {base}"],
        )

    report = inspect_host(str(base))
    if report.mode == HostMode.INCOMPATIBLE_AI_VERSE:
        return InitPlan(
            str(base), report.mode, False, None, None,
            blockers=["incompatible AI-Verse host; standalone fallback is forbidden"],
            warnings=list(report.warnings),
        )

    state, runtime = _mode_paths(base, report.mode)
    blockers: List[str] = []
    warnings = list(report.warnings)
    creates: List[str] = []

    if report.mode == HostMode.AI_VERSE_OS_V2:
        if (base / ".ai-verse-brain").exists():
            blockers.append("parallel standalone .ai-verse-brain store exists inside native AI-Verse host")
        registration_blockers = native_registration_blockers(report)
        invalid_attachment = any(
            warning.startswith("local Brain attachment is invalid:")
            for warning in report.warnings
        )
        if report.brain_extension_slot or invalid_attachment:
            blockers.extend(registration_blockers)
        else:
            creates.append(str(base / ".aiverse" / "extensions" / "registry.json") + "#ai-verse-brain")
            warnings.append("Brain will attach locally before native state initialization")

    marker = state / "installation.json"
    already_initialized = False
    if marker.exists():
        try:
            data = json.loads(marker.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValidationError("installation marker must contain a JSON object")
            _validate_marker(data, expected_mode=report.mode)
            already_initialized = True
            if data.get("package_version") != PACKAGE_VERSION:
                warnings.append(
                    f"installation was initialized by package {data.get('package_version')}; current package is {PACKAGE_VERSION}"
                )
        except Exception as exc:
            blockers.append(str(exc))

    if not state.exists():
        creates.append(str(state))
    if not runtime.exists():
        creates.append(str(runtime))
    if not marker.exists():
        creates.append(str(marker))

    return InitPlan(
        str(base), report.mode, not blockers, str(state), str(runtime),
        creates=creates, blockers=blockers, warnings=warnings,
        already_initialized=already_initialized,
    )


def _atomic_json_write(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".installation-", suffix=".tmp", dir=str(path.parent))
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


def initialize(root: str) -> InitResult:
    plan = plan_init(root)
    if not plan.safe_to_apply:
        raise ValidationError("Brain initialization blocked: " + "; ".join(plan.blockers))
    if plan.state_root is None or plan.runtime_root is None:
        raise ValidationError("initialization plan has no safe state/runtime path")

    if plan.mode == HostMode.AI_VERSE_OS_V2:
        report = inspect_host(str(Path(root).resolve()))
        if not report.brain_extension_slot:
            attach_brain(root)
            plan = plan_init(root)
            if not plan.safe_to_apply:
                raise ValidationError("Brain initialization blocked after attachment: " + "; ".join(plan.blockers))
        from .write_gate import require_write_ready
        require_write_ready(root, allow_uninitialized_bootstrap=True)

    state = Path(plan.state_root)
    runtime = Path(plan.runtime_root)
    state.mkdir(parents=True, exist_ok=True)
    runtime.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(state, 0o700)
        os.chmod(runtime, 0o700)
    except OSError:
        pass

    marker_path = state / "installation.json"
    if marker_path.exists():
        marker = read_installation_marker(root)
        if marker is None:
            raise ValidationError("installation marker disappeared during initialization")
        return InitResult(plan_init(root), marker, False)

    marker = {
        "schema_version": INSTALLATION_SCHEMA_VERSION,
        "state_schema_version": STATE_SCHEMA_VERSION,
        "package_version": PACKAGE_VERSION,
        "mode": plan.mode.value,
        "installation_id": str(uuid4()),
        "installed_at": utc_now(),
    }
    _atomic_json_write(marker_path, marker)
    verified = read_installation_marker(root)
    if verified is None:
        raise ValidationError("failed to verify installation marker after write")
    return InitResult(plan_init(root), verified, True)
