from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
from pathlib import Path
import re
from typing import Dict, List, Optional

from .errors import ScopeError, ValidationError
from .extension_registry import brain_attachment
from .models import Scope


class HostMode(str, Enum):
    STANDALONE = "standalone"
    AI_VERSE_OS_V2 = "ai-verse-os-v2"
    INCOMPATIBLE_AI_VERSE = "incompatible-ai-verse"


@dataclass(frozen=True)
class IntegrationReport:
    root: str
    mode: HostMode
    compatible: bool
    schema_version: Optional[str] = None
    architecture: Optional[str] = None
    memory_detected: bool = False
    brain_extension_slot: bool = False
    brain_supported: Optional[bool] = None
    brain_enabled: Optional[bool] = None
    brain_registration_valid: bool = False
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "root": self.root,
            "mode": self.mode.value,
            "compatible": self.compatible,
            "schema_version": self.schema_version,
            "architecture": self.architecture,
            "memory_detected": self.memory_detected,
            "brain_extension_slot": self.brain_extension_slot,
            "brain_supported": self.brain_supported,
            "brain_enabled": self.brain_enabled,
            "brain_registration_valid": self.brain_registration_valid,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class NativePathContract:
    scope: str
    brain_state: str
    current_context: str
    memory_root: str
    decisions_root: str
    knowledge_root: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "scope": self.scope,
            "brain_state": self.brain_state,
            "current_context": self.current_context,
            "memory_root": self.memory_root,
            "decisions_root": self.decisions_root,
            "knowledge_root": self.knowledge_root,
        }


@dataclass(frozen=True)
class IntegrationPlan:
    mode: HostMode
    safe_to_apply: bool
    steps: List[Dict[str, str]]
    blockers: List[str]
    notes: List[str]

    def to_dict(self) -> Dict[str, object]:
        return {
            "mode": self.mode.value,
            "safe_to_apply": self.safe_to_apply,
            "steps": list(self.steps),
            "blockers": list(self.blockers),
            "notes": list(self.notes),
        }


def _extract_scalar(text: str, key: str) -> Optional[str]:
    match = re.search(rf"(?m)^\s*{re.escape(key)}:\s*[\"']?([^\"'#\s]+)", text)
    return match.group(1) if match else None


def _legacy_brain_manifest_registration(text: str) -> bool:
    """Detect the obsolete tracked AI-VERSE.yaml Brain install slot."""
    return bool(re.search(r"(?ms)^extensions:\s*$.*?^\s{2}brain:\s*$", text))


def _memory_detected(root: Path) -> bool:
    registry = root / ".aiverse" / "extensions" / "registry.json"
    if registry.is_file() and not registry.is_symlink():
        try:
            data = json.loads(registry.read_text(encoding="utf-8"))
            entry = (data.get("extensions") or {}).get("ai-verse-memory")
            if (
                isinstance(entry, dict)
                and entry.get("supported") is True
                and entry.get("installed") is True
                and entry.get("enabled") is True
            ):
                return True
        except Exception:
            pass
    markers = [
        root / "scripts" / "ai-verse-memory" / "memory.py",
        root / ".claude" / "skills" / "ai-verse-memory" / "SKILL.md",
        root / ".agents" / "skills" / "ai-verse-memory" / "SKILL.md",
    ]
    return any(path.is_file() for path in markers)


def inspect_host(root: str) -> IntegrationReport:
    base = Path(root).resolve()
    manifest = base / "AI-VERSE.yaml"
    if not manifest.exists():
        return IntegrationReport(str(base), HostMode.STANDALONE, True)

    text = manifest.read_text(encoding="utf-8", errors="replace")
    schema_version = _extract_scalar(text, "schema_version")
    architecture = _extract_scalar(text, "architecture")
    operator_ok = (base / "operator").is_dir()
    workspaces_ok = (base / "workspaces").is_dir()
    compatible = bool(
        schema_version
        and schema_version.startswith("2.")
        and architecture == "unified-workspace"
        and operator_ok
        and workspaces_ok
    )

    warnings: List[str] = []
    if not compatible:
        warnings.append(
            "AI-VERSE.yaml exists but the host is not a compatible AI-Verse OS v2 unified-workspace layout; refuse standalone fallback"
        )
        return IntegrationReport(
            str(base), HostMode.INCOMPATIBLE_AI_VERSE, False,
            schema_version=schema_version,
            architecture=architecture,
            memory_detected=_memory_detected(base),
            warnings=warnings,
        )

    entry: Optional[Dict[str, object]] = None
    attachment_error: Optional[str] = None
    try:
        entry = brain_attachment(str(base))
    except ValidationError as exc:
        attachment_error = str(exc)

    brain_slot = entry is not None
    brain_supported = entry.get("supported") if entry else None
    brain_enabled = entry.get("enabled") if entry else None
    brain_installed = entry.get("installed") if entry else None
    registration_valid = bool(
        brain_slot
        and brain_supported is True
        and brain_enabled is True
        and brain_installed is True
    )

    if attachment_error:
        warnings.append(f"local Brain attachment is invalid: {attachment_error}")
    elif not brain_slot:
        warnings.append(
            "compatible OS v2 detected but Brain is not attached in .aiverse/extensions/registry.json; "
            "run ai-verse-brain attach <root> --apply"
        )
    elif brain_supported is not True:
        warnings.append("ai-verse-brain local registration must declare supported=true")
    elif brain_installed is not True:
        warnings.append("ai-verse-brain local registration must declare installed=true")
    elif brain_enabled is not True:
        warnings.append("ai-verse-brain local registration is disabled")

    if _legacy_brain_manifest_registration(text):
        warnings.append(
            "legacy tracked AI-VERSE.yaml extensions.brain registration detected; "
            "it is no longer installation authority and should be removed so OS updates stay clean"
        )

    return IntegrationReport(
        str(base), HostMode.AI_VERSE_OS_V2, True,
        schema_version=schema_version,
        architecture=architecture,
        memory_detected=_memory_detected(base),
        brain_extension_slot=brain_slot,
        brain_supported=brain_supported if isinstance(brain_supported, bool) else None,
        brain_enabled=brain_enabled if isinstance(brain_enabled, bool) else None,
        brain_registration_valid=registration_valid,
        warnings=warnings,
    )


def native_path_contract(root: str, scope: str) -> NativePathContract:
    report = inspect_host(root)
    if report.mode != HostMode.AI_VERSE_OS_V2 or not report.compatible:
        raise ScopeError("native path contract requires compatible AI-Verse OS v2")
    base = Path(root).resolve()
    parsed = Scope(scope)
    if parsed.is_operator:
        return NativePathContract(
            scope,
            str(base / "operator" / "brain"),
            str(base / "operator" / "context" / "CURRENT.md"),
            str(base / "operator" / "memory"),
            str(base / "operator" / "decisions"),
            str(base / "knowledge"),
        )
    workspace = base / "workspaces" / str(parsed.workspace_id)
    if not workspace.is_dir():
        raise ScopeError(f"workspace does not exist: {parsed.workspace_id}")
    return NativePathContract(
        scope,
        str(workspace / "brain"),
        str(workspace / "context" / "CURRENT.md"),
        str(workspace / "memory"),
        str(workspace / "decisions"),
        str(workspace / "knowledge"),
    )


def native_registration_blockers(report: IntegrationReport) -> List[str]:
    if report.mode != HostMode.AI_VERSE_OS_V2:
        return []
    blockers: List[str] = []
    if not report.brain_extension_slot:
        blockers.append(
            "Brain is not attached in .aiverse/extensions/registry.json; run ai-verse-brain attach <root> --apply"
        )
    elif report.brain_supported is not True:
        blockers.append("ai-verse-brain local registration must declare supported=true")
    if report.brain_extension_slot and report.brain_enabled is not True:
        blockers.append("ai-verse-brain local registration must declare enabled=true")
    if report.brain_extension_slot and not report.brain_registration_valid and not blockers:
        blockers.append("ai-verse-brain local registration is not installed/write-ready")
    return blockers


def plan_integration(root: str) -> IntegrationPlan:
    """Read-only integration plan. It never writes to the target host."""
    report = inspect_host(root)
    if report.mode == HostMode.INCOMPATIBLE_AI_VERSE:
        return IntegrationPlan(
            report.mode,
            False,
            [],
            ["incompatible AI-Verse host; do not create a standalone Brain store inside it"],
            list(report.warnings),
        )
    if report.mode == HostMode.STANDALONE:
        return IntegrationPlan(
            report.mode,
            True,
            [
                {"action": "use_state_root", "target": ".ai-verse-brain/", "owner": "brain"},
                {"action": "use_runtime_root", "target": ".ai-verse-brain/runtime/", "owner": "brain-runtime"},
            ],
            [],
            ["standalone plan only; no OS or Memory repository is required"],
        )

    steps = [
        {
            "action": "attach_local_extension",
            "target": ".aiverse/extensions/registry.json#ai-verse-brain",
            "owner": "brain-installation",
        },
        {"action": "use_operator_state", "target": "operator/brain/", "owner": "brain"},
        {"action": "use_workspace_state", "target": "workspaces/<id>/brain/", "owner": "brain"},
        {"action": "use_runtime_root", "target": "runtime/ai-verse-brain/", "owner": "brain-runtime"},
        {"action": "read_current_state", "target": "operator/workspace context", "owner": "os"},
        {"action": "read_history_when_needed", "target": "operator/workspace memory", "owner": "memory-or-os"},
    ]
    blockers = native_registration_blockers(report)
    notes = list(report.warnings)
    notes.append("Brain attachment never modifies tracked AI-Verse OS files")
    notes.append("Memory is optional; Brain must not copy or merge the Memory implementation")
    return IntegrationPlan(report.mode, not blockers, steps, blockers, notes)
