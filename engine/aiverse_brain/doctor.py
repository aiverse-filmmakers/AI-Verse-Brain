from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Dict, List

from .integration import HostMode, inspect_host


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    severity: str
    message: str

    def to_dict(self) -> Dict[str, str]:
        return {"name": self.name, "severity": self.severity, "message": self.message}


@dataclass
class DoctorReport:
    mode: str
    checks: List[DoctorCheck] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(item.severity == "FAIL" for item in self.checks)

    def add(self, name: str, severity: str, message: str) -> None:
        self.checks.append(DoctorCheck(name, severity, message))

    def to_dict(self) -> Dict[str, object]:
        return {"ok": self.ok, "mode": self.mode, "checks": [item.to_dict() for item in self.checks]}


_KIND_DIR_SCOPE = {
    "intent": "intent", "practices": "practice", "gaps": "gap", "opportunities": "opportunity",
    "initiatives": "initiative", "objectives": "objective", "models": "model_belief",
    "evaluations": "evaluation", "learning": "learning", "strategies": "strategy_rule", "policies": "policy",
}


def _scan_state_root(report: DoctorReport, state_root: Path, expected_scope: str) -> None:
    if not state_root.exists():
        return
    if not state_root.is_dir():
        report.add("state-root", "FAIL", f"Brain state root is not a directory: {state_root}")
        return
    for dirname, expected_kind in _KIND_DIR_SCOPE.items():
        directory = state_root / dirname
        if not directory.exists():
            continue
        for path in directory.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                report.add("state-json", "FAIL", f"cannot parse {path}: {exc}")
                continue
            if data.get("scope") != expected_scope:
                report.add("scope-isolation", "FAIL", f"{path} declares scope {data.get('scope')!r}, expected {expected_scope!r}")
            if data.get("kind") != expected_kind:
                report.add("kind-integrity", "FAIL", f"{path} declares kind {data.get('kind')!r}, expected {expected_kind!r}")


def run_doctor(root: str) -> DoctorReport:
    base = Path(root).resolve()
    host = inspect_host(str(base))
    report = DoctorReport(host.mode.value)
    if not base.exists():
        report.add("root", "FAIL", f"target root does not exist: {base}")
        return report

    if host.mode == HostMode.INCOMPATIBLE_AI_VERSE:
        report.add("host-contract", "FAIL", "AI-Verse manifest exists but is not compatible OS v2 unified-workspace; standalone fallback is forbidden")
        return report

    report.add("host-contract", "PASS", f"detected {host.mode.value}")
    if host.mode == HostMode.STANDALONE:
        _scan_state_root(report, base / ".ai-verse-brain", "operator")
        return report

    if (base / ".ai-verse-brain").exists():
        report.add("parallel-store", "FAIL", "standalone .ai-verse-brain exists inside native AI-Verse mode")
    else:
        report.add("parallel-store", "PASS", "no standalone Brain store in native mode")

    if host.brain_extension_slot:
        report.add("brain-extension-slot", "PASS", "AI-VERSE.yaml exposes extensions.brain")
    else:
        report.add("brain-extension-slot", "WARN", "extensions.brain is absent; do not patch the OS manifest implicitly")

    report.add("memory", "INFO", "AI-Verse Memory detected" if host.memory_detected else "AI-Verse Memory not detected; it remains optional")
    _scan_state_root(report, base / "operator" / "brain", "operator")
    workspaces = base / "workspaces"
    for workspace in sorted(workspaces.iterdir() if workspaces.is_dir() else []):
        if workspace.is_dir() and not workspace.name.startswith("."):
            _scan_state_root(report, workspace / "brain", f"workspace:{workspace.name}")
    return report
