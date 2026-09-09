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


def _extension_slot(text: str, name: str) -> bool:
    in_extensions = False
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith((" ", "\t")):
            in_extensions = line.strip() == "extensions:"
            continue
        if in_extensions and re.match(rf"^\s{{2,}}{re.escape(name)}:\s*(?:#.*)?$", line):
            return True
    return False


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
            brain_extension_slot=_extension_slot(text, "brain"),
            warnings=warnings,
        )

    brain_slot = _extension_slot(text, "brain")
    if not brain_slot:
        warnings.append(
            "compatible OS v2 detected but AI-VERSE.yaml has no extensions.brain slot; Brain must not patch the OS manifest implicitly"
        )
    return IntegrationReport(
        str(base), HostMode.AI_VERSE_OS_V2, True,
        schema_version=schema_version,
        architecture=architecture,
        memory_detected=_memory_detected(base),
        brain_extension_slot=brain_slot,
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
    blockers: List[str] = []
    if not report.brain_extension_slot:
        blockers.append("AI-VERSE.yaml does not yet expose an extensions.brain registration slot")
    notes = list(report.warnings)
    notes.append("Memory is optional; Brain must not copy or merge the Memory implementation")
    return IntegrationPlan(report.mode, not blockers, steps, blockers, notes)
