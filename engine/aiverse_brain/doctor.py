from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Dict, List

from .installation import STATE_SCHEMA_VERSION, installation_marker_path, read_installation_marker
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


def _has_confirmed_intent(state_root: Path, subtype: str) -> bool:
    directory = state_root / "intent"
    if not directory.is_dir():
        return False
    for path in directory.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if data.get("status") in {"CONFIRMED", "ACTIVE"} and (data.get("payload") or {}).get("subtype") == subtype:
            return True
    return False


def _check_installation(report: DoctorReport, root: Path, state_root: Path) -> None:
    marker_path = installation_marker_path(str(root))
    if marker_path is None:
        report.add("installation", "FAIL", "host mode has no safe installation marker path")
        return
    if not marker_path.exists():
        if state_root.exists():
            report.add("installation", "WARN", f"Brain state exists without an installation marker: {marker_path}")
        else:
            report.add("installation", "WARN", "Brain is not initialized; run `ai-verse-brain init --apply`")
        return
    try:
        marker = read_installation_marker(str(root))
    except Exception as exc:
        report.add("installation", "FAIL", str(exc))
        return
    if marker is None:
        report.add("installation", "FAIL", "installation marker could not be resolved")
        return
    report.add(
        "installation",
        "PASS",
        f"installation marker valid; state schema {marker.get('state_schema_version')} (supported {STATE_SCHEMA_VERSION})",
    )
    desired = _has_confirmed_intent(state_root, "desired_state")
    success = _has_confirmed_intent(state_root, "success_definition")
    if desired and success:
        report.add("onboarding", "PASS", "explicit desired state and success definition are present")
    else:
        missing = []
        if not desired:
            missing.append("desired_state")
        if not success:
            missing.append("success_definition")
        report.add("onboarding", "WARN", "onboarding incomplete; missing " + ", ".join(missing))


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
        state_root = base / ".ai-verse-brain"
        _scan_state_root(report, state_root, "operator")
        _check_installation(report, base, state_root)
        return report

    if (base / ".ai-verse-brain").exists():
        report.add("parallel-store", "FAIL", "standalone .ai-verse-brain exists inside native AI-Verse mode")
    else:
        report.add("parallel-store", "PASS", "no standalone Brain store in native mode")

    if not host.brain_extension_slot:
        report.add(
            "brain-attachment",
            "WARN",
            "Brain is not attached in .aiverse/extensions/registry.json; native Brain writes are unavailable",
        )
    elif host.brain_registration_valid:
        report.add("brain-attachment", "PASS", "local Brain attachment is supported, installed and enabled")
    else:
        report.add(
            "brain-attachment",
            "FAIL",
            f"local Brain attachment is not write-ready (supported={host.brain_supported!r}, enabled={host.brain_enabled!r})",
        )

    report.add("memory", "INFO", "AI-Verse Memory detected" if host.memory_detected else "AI-Verse Memory not detected; it remains optional")
    operator_state = base / "operator" / "brain"
    _scan_state_root(report, operator_state, "operator")
    _check_installation(report, base, operator_state)
    workspaces = base / "workspaces"
    for workspace in sorted(workspaces.iterdir() if workspaces.is_dir() else []):
        if workspace.is_dir() and not workspace.name.startswith("."):
            _scan_state_root(report, workspace / "brain", f"workspace:{workspace.name}")
    return report
