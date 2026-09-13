from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from ._version import DISPLAY_VERSION, __version__
from .adoption import apply_standalone_adoption, plan_standalone_adoption
from .direction_ownership import read_registry as read_direction_registry
from .doctor import run_doctor
from .errors import ValidationError
from .extension_registry import attach_brain, brain_attachment, detach_brain_registration, set_brain_enabled
from .installation import initialize, read_installation_marker
from .integration import HostMode, inspect_host
from .migration import apply_migration, plan_migration

PUBLIC_COMMANDS = ("install", "setup", "status", "doctor", "enable", "disable", "update", "uninstall")


@dataclass(frozen=True)
class LifecycleStatus:
    component_id: str
    version: str
    root: str
    mode: str
    state: str
    installed: bool
    initialized: bool
    enabled: Optional[bool]
    migration_required: bool
    ready: bool
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "component_id": self.component_id, "version": self.version,
            "display_version": DISPLAY_VERSION, "root": self.root, "mode": self.mode,
            "state": self.state, "installed": self.installed, "initialized": self.initialized,
            "enabled": self.enabled, "migration_required": self.migration_required,
            "ready": self.ready, "blockers": list(self.blockers), "warnings": list(self.warnings),
        }


def _brain_owned_scopes(root: Path) -> List[str]:
    if inspect_host(str(root)).mode != HostMode.AI_VERSE_OS_V2: return []
    registry = read_direction_registry(root)
    return sorted(
        scope for scope, record in registry.get("scopes", {}).items()
        if isinstance(record, dict) and record.get("owner") == "brain"
    )


def lifecycle_status(root: str) -> LifecycleStatus:
    base = Path(root).resolve()
    if not base.exists() or not base.is_dir():
        return LifecycleStatus(
            "ai-verse-brain", __version__, str(base), "unknown", "unhealthy",
            True, False, None, False, False, ["target root does not exist or is not a directory"], [],
        )
    host = inspect_host(str(base))
    blockers, warnings = [], list(host.warnings)
    if host.mode == HostMode.INCOMPATIBLE_AI_VERSE:
        return LifecycleStatus(
            "ai-verse-brain", __version__, str(base), host.mode.value, "unhealthy",
            True, False, None, False, False,
            ["incompatible AI-Verse host; standalone fallback is forbidden"], warnings,
        )
    adoption = plan_standalone_adoption(str(base))
    if adoption.needed:
        return LifecycleStatus(
            "ai-verse-brain", __version__, str(base), host.mode.value,
            "migration-required" if adoption.safe_to_apply else "unhealthy",
            True, False, host.brain_enabled if host.mode == HostMode.AI_VERSE_OS_V2 else None,
            True, False, list(adoption.blockers), warnings,
        )

    enabled: Optional[bool] = None
    state = "setup-required"
    if host.mode == HostMode.AI_VERSE_OS_V2:
        attachment = brain_attachment(str(base))
        if attachment is not None:
            enabled = attachment.get("enabled") if isinstance(attachment.get("enabled"), bool) else None
        if attachment is None:
            state = "setup-required"
        elif attachment.get("supported") is not True or attachment.get("installed") is not True:
            state = "unhealthy"; blockers.append("native Brain attachment is not supported+installed")
        elif enabled is False:
            state = "disabled"

    try:
        marker = read_installation_marker(str(base))
    except Exception as exc:
        marker = None; blockers.append(str(exc)); state = "unhealthy"
    initialized = marker is not None
    migration_required = False
    if initialized:
        try:
            migration = plan_migration(str(base))
            migration_required = migration.needed
            if not migration.safe_to_apply:
                blockers.extend(migration.blockers); state = "migration-required"
            elif migration.needed and state != "disabled":
                state = "migration-required"
        except Exception as exc:
            blockers.append(str(exc)); state = "unhealthy"

    doctor = run_doctor(str(base))
    hard_failures = [
        check.message for check in doctor.checks
        if check.severity == "FAIL" and not (state == "disabled" and check.name == "brain-attachment")
    ]
    if hard_failures:
        blockers.extend(item for item in hard_failures if item not in blockers); state = "unhealthy"
    if not initialized and state not in {"unhealthy", "disabled"}:
        state = "setup-required"
    elif initialized and not blockers and not migration_required and state != "disabled":
        if host.mode == HostMode.STANDALONE or host.brain_registration_valid: state = "ready"
    return LifecycleStatus(
        "ai-verse-brain", __version__, str(base), host.mode.value, state, True,
        initialized, enabled, migration_required, state == "ready", blockers, warnings,
    )


def component_descriptor(root: str) -> Dict[str, Any]:
    status = lifecycle_status(root)
    host = inspect_host(status.root)
    return {
        "schema_version": "1.0", "component_id": "ai-verse-brain", "name": "AI-Verse Brain",
        "version": __version__, "display_version": DISPLAY_VERSION,
        "package": {"python_distribution": "ai-verse-brain", "install_source": "git-or-distribution-managed", "python": ">=3.9"},
        "compatibility": {
            "standalone": True, "ai_verse_os": "2.x unified-workspace",
            "detected_mode": host.mode.value, "compatible": host.compatible,
        },
        "supported_lifecycle_commands": list(PUBLIC_COMMANDS),
        "setup_requirements": {
            "native": ["local extension attachment", "Brain state initialization"],
            "standalone": ["Brain state initialization"], "standalone_to_native_adoption": True,
        },
        "current": status.to_dict(), "authority_transfer_separate": True,
        "setup_transfers_strategic_authority": False, "uninstall_preserves_canonical_state": True,
        "requested_scopes": ["operator", "workspace:<id> in native mode"],
        "requested_capabilities": [
            "Brain-owned canonical state", "read-only host context",
            "owner-routed writes through host boundary",
        ],
        "doctor_depths": [
            "structural", "attachment/discovery", "runtime", "dependency", "operational", "system/composed",
        ],
    }


def setup_component(root: str, *, apply: bool = False) -> Dict[str, Any]:
    base = Path(root).resolve()
    host = inspect_host(str(base))
    if host.mode == HostMode.INCOMPATIBLE_AI_VERSE:
        raise ValidationError("Brain setup blocked: incompatible AI-Verse host")
    adoption = plan_standalone_adoption(str(base))
    plan = {
        "ok": adoption.safe_to_apply, "dry_run": not apply, "root": str(base),
        "mode": host.mode.value, "adoption": adoption.to_dict(),
        "strategic_handover": False, "steps": [],
    }
    if host.mode == HostMode.AI_VERSE_OS_V2:
        plan["steps"].append("attach local Brain extension if absent")
        plan["steps"].append(
            "adopt verified standalone Brain state into native operator/brain"
            if adoption.needed else "initialize native Brain-owned state if absent"
        )
    else:
        plan["steps"].append("initialize standalone Brain-owned state if absent")
    plan["steps"].append("run structural/readiness verification")
    if not apply: return plan

    if host.mode == HostMode.AI_VERSE_OS_V2:
        attachment = brain_attachment(str(base))
        if attachment is None: attach_brain(str(base))
        elif attachment.get("enabled") is False:
            raise ValidationError("setup will not silently re-enable disabled Brain; run enable explicitly")
        adoption_result = apply_standalone_adoption(str(base)).to_dict() if adoption.needed else None
        if not adoption.needed and read_installation_marker(str(base)) is None: initialize(str(base))
    else:
        adoption_result = None
        if read_installation_marker(str(base)) is None: initialize(str(base))
    status = lifecycle_status(str(base))
    return {
        "ok": status.ready, "dry_run": False, "root": str(base),
        "adoption": adoption_result, "status": status.to_dict(), "strategic_handover": False,
    }


def enable_component(root: str, *, apply: bool = False) -> Dict[str, Any]:
    base = Path(root).resolve(); host = inspect_host(str(base))
    if host.mode != HostMode.AI_VERSE_OS_V2:
        return {"ok": True, "applicable": False, "mode": host.mode.value, "status": lifecycle_status(str(base)).to_dict()}
    attachment = brain_attachment(str(base))
    if attachment is None: raise ValidationError("Brain is not attached; run setup first")
    if not apply:
        return {"ok": True, "dry_run": True, "will_enable": attachment.get("enabled") is not True, "current": attachment}
    updated = set_brain_enabled(str(base), True)
    return {"ok": True, "dry_run": False, "attachment": updated, "status": lifecycle_status(str(base)).to_dict()}


def disable_component(root: str, *, apply: bool = False) -> Dict[str, Any]:
    base = Path(root).resolve(); host = inspect_host(str(base))
    if host.mode != HostMode.AI_VERSE_OS_V2:
        return {"ok": True, "applicable": False, "mode": host.mode.value, "status": lifecycle_status(str(base)).to_dict()}
    owners = _brain_owned_scopes(base)
    if owners: raise ValidationError("Brain cannot be disabled while it owns strategic direction for: " + ", ".join(owners))
    attachment = brain_attachment(str(base))
    if attachment is None: raise ValidationError("Brain is not attached")
    if not apply:
        return {"ok": True, "dry_run": True, "will_disable": attachment.get("enabled") is not False, "current": attachment}
    updated = set_brain_enabled(str(base), False)
    return {
        "ok": True, "dry_run": False, "attachment": updated,
        "canonical_brain_state_preserved": True, "status": lifecycle_status(str(base)).to_dict(),
    }


def update_component(root: str, *, apply: bool = False) -> Dict[str, Any]:
    base = Path(root).resolve(); status_before = lifecycle_status(str(base))
    if not status_before.initialized: raise ValidationError("Brain is not initialized; run setup before update")
    migration = plan_migration(str(base))
    plan = {
        "ok": migration.safe_to_apply, "dry_run": not apply,
        "software_update_owner": "package-manager/distribution",
        "state_migration": migration.to_dict(), "enabled_state_preserved": True,
        "note": "Reconcile Brain metadata/state after the package itself is updated.",
    }
    if not apply: return plan
    if not migration.safe_to_apply: raise ValidationError("Brain update blocked: " + "; ".join(migration.blockers))
    if migration.needed: apply_migration(str(base), lifecycle_update=True)
    host = inspect_host(str(base))
    if host.mode == HostMode.AI_VERSE_OS_V2 and brain_attachment(str(base)) is not None:
        attach_brain(str(base))
    plan["dry_run"] = False; plan["status"] = lifecycle_status(str(base)).to_dict()
    return plan


def uninstall_component(root: str, *, apply: bool = False) -> Dict[str, Any]:
    base = Path(root).resolve(); host = inspect_host(str(base))
    if host.mode == HostMode.AI_VERSE_OS_V2:
        owners = _brain_owned_scopes(base)
        if owners: raise ValidationError("Brain cannot be uninstalled while it owns strategic direction for: " + ", ".join(owners))
        current = brain_attachment(str(base))
        if not apply:
            return {
                "ok": True, "dry_run": True, "will_detach": current is not None,
                "canonical_brain_state_preserved": True, "package_removal_owner": "package-manager/distribution",
            }
        removed = detach_brain_registration(str(base)) if current is not None else False
        return {
            "ok": True, "dry_run": False, "detached": removed,
            "canonical_brain_state_preserved": True, "package_removal_owner": "package-manager/distribution",
            "status": lifecycle_status(str(base)).to_dict(),
        }
    return {
        "ok": True, "dry_run": not apply, "applicable_integration_removal": False,
        "canonical_brain_state_preserved": True, "package_removal_owner": "package-manager/distribution",
        "note": "Standalone state is retained; package removal is performed by the package manager.",
    }


def lifecycle_doctor(root: str) -> Dict[str, Any]:
    structural = run_doctor(root); status = lifecycle_status(root); host = inspect_host(root)
    return {
        "ok": status.ready, "component_id": "ai-verse-brain",
        "depth": {
            "structural": structural.to_dict(),
            "attachment_discovery": {
                "checked": True, "mode": host.mode.value,
                "registration_valid": host.brain_registration_valid,
            },
            "runtime": {
                "checked": True, "brain_scheduler_owned": False,
                "note": "Brain runtime is disposable; Gateway/host owns execution loops.",
            },
            "dependency": {
                "checked": True, "memory_required": False,
                "gateway_required_for_goal_continuation": True,
                "skills_required_for_skill_promotion": True,
            },
            "operational": {
                "checked": False,
                "reason": "Operational model/tool execution requires an explicitly selected live host adapter.",
            },
            "system_composed": {
                "checked": False,
                "reason": "Whole-system readiness is owned by Distribution/System, not inferred by Brain doctor.",
            },
        },
        "status": status.to_dict(),
    }
