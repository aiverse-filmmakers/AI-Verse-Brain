from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import re
from typing import Dict, List, Optional

from .errors import ScopeError
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


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _extension_settings(text: str, name: str) -> Optional[Dict[str, str]]:
    """Return direct scalar settings for one top-level extensions entry.

    This intentionally supports only the small host contract Brain needs rather
    than acting as a general YAML parser. Ambiguous/duplicate registrations are
    rejected by returning an invalid sentinel mapping.
    """
    lines = text.splitlines()
    extensions_indent: Optional[int] = None
    entry_indent: Optional[int] = None
    found = 0
    settings: Dict[str, str] = {}

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = _indent(line)
        if extensions_indent is None:
            if stripped == "extensions:":
                extensions_indent = indent
            continue

        if entry_indent is None:
            if indent <= extensions_indent:
                if stripped == "extensions:":
                    continue
                extensions_indent = None
                continue
            if re.match(rf"^{re.escape(name)}:\s*(?:#.*)?$", stripped):
                found += 1
                entry_indent = indent
            continue

        if indent <= entry_indent:
            if re.match(rf"^{re.escape(name)}:\s*(?:#.*)?$", stripped) and indent == entry_indent:
                found += 1
            break
        if ":" not in stripped:
            continue
        key, raw = stripped.split(":", 1)
        value = raw.split("#", 1)[0].strip().strip("\"'")
        if key in settings:
            return {"__invalid__": "duplicate-key"}
        settings[key] = value

    if found == 0:
        return None
    if found != 1:
        return {"__invalid__": "duplicate-registration"}
    return settings


def _contract_bool(settings: Optional[Dict[str, str]], key: str) -> Optional[bool]:
    if not settings or "__invalid__" in settings or key not in settings:
        return None
    value = settings[key].strip().lower()
    if value == "true":
        return True
    if value == "false":
        return False
    return None


def _memory_detected(root: Path) -> bool:
    markers = [
        root / "scripts" / "ai-verse-memory" / "memory.py",
        root / ".claude" / "skills" / "ai-verse-memory" / "SKILL.md",
        root / ".agents" / "skills" / "ai-verse-memory" / "SKILL.md",
    ]
    if any(path.is_file() for path in markers):
        return True
    registry = root / "skills" / "registry.yaml"
    if registry.is_file():
        try:
            return "ai-verse-memory" in registry.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return False
    return False


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
    settings = _extension_settings(text, "brain")
    brain_slot = settings is not None
    brain_supported = _contract_bool(settings, "supported")
    brain_enabled = _contract_bool(settings, "enabled")
    registration_valid = bool(brain_slot and brain_supported is True and brain_enabled is True)
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
            brain_extension_slot=brain_slot,
            brain_supported=brain_supported,
            brain_enabled=brain_enabled,
            brain_registration_valid=False,
            warnings=warnings,
        )

    if not brain_slot:
        warnings.append(
            "compatible OS v2 detected but AI-VERSE.yaml has no extensions.brain registration; Brain must not patch the OS manifest implicitly"
        )
    elif brain_supported is not True:
        warnings.append("extensions.brain.supported must be explicitly true before native Brain writes are allowed")
    elif brain_enabled is not True:
        warnings.append("extensions.brain.enabled must be explicitly true before native Brain writes are allowed")

    return IntegrationReport(
        str(base), HostMode.AI_VERSE_OS_V2, True,
        schema_version=schema_version,
        architecture=architecture,
        memory_detected=_memory_detected(base),
        brain_extension_slot=brain_slot,
        brain_supported=brain_supported,
        brain_enabled=brain_enabled,
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
        blockers.append("AI-VERSE.yaml does not expose extensions.brain registration")
    elif report.brain_supported is not True:
        blockers.append("extensions.brain.supported must be explicitly true")
    if report.brain_extension_slot and report.brain_enabled is not True:
        blockers.append("extensions.brain.enabled must be explicitly true")
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
        {"action": "use_operator_state", "target": "operator/brain/", "owner": "brain"},
        {"action": "use_workspace_state", "target": "workspaces/<id>/brain/", "owner": "brain"},
        {"action": "use_runtime_root", "target": "runtime/ai-verse-brain/", "owner": "brain-runtime"},
        {"action": "read_current_state", "target": "operator/workspace context", "owner": "os"},
        {"action": "read_history_when_needed", "target": "operator/workspace memory", "owner": "memory-or-os"},
    ]
    blockers = native_registration_blockers(report)
    notes = list(report.warnings)
    notes.append("Memory is optional; Brain must not copy or merge the Memory implementation")
    return IntegrationPlan(report.mode, not blockers, steps, blockers, notes)
