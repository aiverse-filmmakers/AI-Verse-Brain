from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .errors import ValidationError
from .integration import HostMode, IntegrationReport, inspect_host, native_registration_blockers


@dataclass(frozen=True)
class WriteReadiness:
    root: str
    mode: HostMode
    registration_valid: bool
    initialized: bool
    installation_id: Optional[str] = None


def _native_marker(report: IntegrationReport) -> Path:
    return Path(report.root) / "operator" / "brain" / "installation.json"


def require_write_ready(root: str, *, allow_uninitialized_bootstrap: bool = False) -> WriteReadiness:
    """Validate the authority required before Brain mutates native host state.

    Standalone mode retains its existing self-contained behavior. Native mode is
    fail-closed: host compatibility, explicit supported+enabled registration and
    a valid installation marker are required for normal writes. Initialization is
    the sole bootstrap exception and may omit the marker while still requiring a
    valid native registration contract.
    """
    report = inspect_host(str(Path(root).resolve()))
    if report.mode == HostMode.INCOMPATIBLE_AI_VERSE:
        raise ValidationError("native Brain write blocked: incompatible AI-Verse host")
    if report.mode == HostMode.STANDALONE:
        return WriteReadiness(report.root, report.mode, True, True, None)

    blockers = native_registration_blockers(report)
    if blockers:
        raise ValidationError("native Brain write blocked: " + "; ".join(blockers))

    marker = _native_marker(report)
    if not marker.exists():
        if allow_uninitialized_bootstrap:
            return WriteReadiness(report.root, report.mode, True, False, None)
        raise ValidationError(
            "native Brain write blocked: Brain is not initialized; run `ai-verse-brain init --apply` after registration"
        )

    from .installation import read_installation_marker  # local import avoids module cycle

    data = read_installation_marker(report.root)
    if data is None:
        raise ValidationError("native Brain write blocked: installation marker is missing or invalid")
    return WriteReadiness(
        report.root,
        report.mode,
        True,
        True,
        str(data.get("installation_id")) if data.get("installation_id") else None,
    )
