from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional, Sequence
from uuid import uuid4

from .authority import AuthorityTier
from .bridge import BridgeConfig, adapter_doctor
from .cadence import Trigger
from .cadence_hooks import effective_cadence_policy, render_cadence_hooks
from .cadence_plan import plan_cadence
from .controller import BrainController
from .direction_ownership import DirectionOwnershipService, read_registry as read_direction_registry
from .doctor import run_doctor
from .errors import BrainError, ValidationError
from .extension_registry import attach_brain, brain_attachment, detach_brain_registration, set_brain_enabled
from .host_selection import HostSelection, select_host
from .installation import initialize, plan_init, read_installation_marker
from .integration import HostMode, inspect_host, plan_integration
from .migration import apply_migration, plan_migration
from .lifecycle import (
    component_descriptor, disable_component, enable_component, lifecycle_doctor,
    lifecycle_status, setup_component, uninstall_component, update_component,
)
from .models import EvidenceRef, Scope
from .onboarding import OnboardingService
from .runtime import BrainRuntime
from .tick_output import build_tick_summary
from .vendor import vendor_bridge_config, vendor_reasoner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai-verse-brain", description="AI-Verse Brain utilities")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="plan or initialize Brain-owned state without modifying host-owned canonical files")
    init.add_argument("root", nargs="?", default=".")
    init.add_argument("--apply", action="store_true", help="apply the safe initialization plan; default is dry-run")
    init.add_argument("--json", action="store_true", help="emit stable structured JSON")

    install_cmd = sub.add_parser("install", help="report the installed Brain package and machine-readable install contract")
    install_cmd.add_argument("root", nargs="?", default=".")
    install_cmd.add_argument("--json", action="store_true", help="emit stable structured JSON")

    setup_cmd = sub.add_parser("setup", help="attach/adopt/initialize Brain without strategic authority handover")
    setup_cmd.add_argument("root", nargs="?", default=".")
    setup_cmd.add_argument("--apply", action="store_true", help="apply the setup plan; default is dry-run")
    setup_cmd.add_argument("--json", action="store_true", help="emit stable structured JSON")

    status_cmd = sub.add_parser("status", help="fast non-destructive public lifecycle status")
    status_cmd.add_argument("root", nargs="?", default=".")
    status_cmd.add_argument("--json", action="store_true", help="emit stable structured JSON")

    enable_cmd = sub.add_parser("enable", help="re-enable an attached native Brain")
    enable_cmd.add_argument("root", nargs="?", default=".")
    enable_cmd.add_argument("--apply", action="store_true", help="apply enablement; default is dry-run")
    enable_cmd.add_argument("--json", action="store_true", help="emit stable structured JSON")

    update_cmd = sub.add_parser("update", help="reconcile Brain package/state metadata after software update")
    update_cmd.add_argument("root", nargs="?", default=".")
    update_cmd.add_argument("--apply", action="store_true", help="apply safe state/metadata update; default is dry-run")
    update_cmd.add_argument("--json", action="store_true", help="emit stable structured JSON")

    uninstall_cmd = sub.add_parser("uninstall", help="remove Brain integration while preserving canonical state by default")
    uninstall_cmd.add_argument("root", nargs="?", default=".")
    uninstall_cmd.add_argument("--apply", action="store_true", help="detach integration; default is dry-run")
    uninstall_cmd.add_argument("--json", action="store_true", help="emit stable structured JSON")

    descriptor_cmd = sub.add_parser("descriptor", help="machine-readable component lifecycle descriptor")
    descriptor_cmd.add_argument("root", nargs="?", default=".")
    descriptor_cmd.add_argument("--json", action="store_true", help="emit stable structured JSON")

    attach = sub.add_parser("attach", help="attach Brain to a compatible AI-Verse OS through the local extension registry")
    attach.add_argument("root", nargs="?", default=".")
    attach.add_argument("--apply", action="store_true", help="write the local attachment; default is dry-run")

    disable = sub.add_parser("disable", help="disable an attached native Brain without deleting Brain state")
    disable.add_argument("root", nargs="?", default=".")
    disable.add_argument("--apply", action="store_true", help="disable the local attachment; default is dry-run")
    disable.add_argument("--json", action="store_true", help="emit stable structured JSON")

    detach = sub.add_parser("detach", help="remove Brain's local OS attachment while preserving Brain state")
    detach.add_argument("root", nargs="?", default=".")
    detach.add_argument("--apply", action="store_true", help="remove the local attachment; default is dry-run")

    onboard = sub.add_parser("onboard", help="inspect or apply explicit user intent onboarding")
    onboard.add_argument("root", nargs="?", default=".")
    onboard.add_argument("--scope", default="operator")
    onboard.add_argument("--answers", help="path to a JSON answers file")
    onboard.add_argument("--apply", action="store_true", help="apply explicit answers as confirmed Brain intent/practices")

    direction = sub.add_parser("direction-owner", help="inspect or explicitly transfer strategic direction between OS and Brain")
    direction.add_argument("root", nargs="?", default=".")
    direction.add_argument("--scope", default="operator")
    direction.add_argument("--handover-to-brain", action="store_true", help="plan an explicit handover from OS to Brain")
    direction.add_argument("--handover-to-os", action="store_true", help="plan an explicit export-and-handback from Brain to OS")
    direction.add_argument("--apply", action="store_true", help="apply the selected handover after its explicit confirmation flag")
    direction.add_argument("--confirm-import", action="store_true", help="confirm importing discovered OS goals/objectives before OS-to-Brain handover")
    direction.add_argument("--confirm-export", action="store_true", help="confirm exporting current Brain strategic intent before Brain-to-OS handback")

    adapter = sub.add_parser("adapter-doctor", help="validate and handshake with a JSON subprocess adapter")
    adapter.add_argument("config", help="path to adapter JSON config; credential values must remain outside this file")

    vendor_doc = sub.add_parser("vendor-doctor", help="handshake with a built-in Claude/Codex/Hermes reasoner wrapper")
    vendor_doc.add_argument("vendor", choices=["claude", "codex", "hermes"])
    vendor_doc.add_argument("root", nargs="?", default=".")
    vendor_doc.add_argument("--model")
    vendor_doc.add_argument("--provider")
    vendor_doc.add_argument("--binary")
    vendor_doc.add_argument("--timeout", type=float, default=120.0)
    vendor_doc.add_argument("--env-name", action="append", default=[], help="explicit credential/environment variable name to forward")

    tick = sub.add_parser("run-tick", help="run one bounded Brain cognition tick with an explicitly selected host")
    tick.add_argument("root", nargs="?", default=".")
    tick.add_argument("--vendor", choices=["claude", "codex", "hermes"], required=True)
    host_mode = tick.add_mutually_exclusive_group(required=True)
    host_mode.add_argument("--host-adapter", help="JSON bridge config for the real host/runtime adapter")
    host_mode.add_argument(
        "--read-only-context",
        action="store_true",
        help="explicitly use the limited built-in current-context-only host",
    )
    tick.add_argument("--scope", default="operator")
    tick.add_argument(
        "--trigger",
        choices=[
            "explicit", "session_start", "session_end", "scheduled_orientation",
            "scheduled_review", "event", "objective_wake", "blocker_resolution",
            "external_change", "manual_recovery",
        ],
        default="explicit",
    )
    tick.add_argument("--idempotency-key")
    tick.add_argument("--session-id")
    tick.add_argument("--context-file", help="optional context file; valid only with --read-only-context")
    tick.add_argument("--model")
    tick.add_argument("--provider")
    tick.add_argument("--binary")
    tick.add_argument("--timeout", type=float, default=120.0)
    tick.add_argument("--env-name", action="append", default=[])

    doctor = sub.add_parser("doctor", help="read-only host, installation, and Brain-state health checks")
    doctor.add_argument("root", nargs="?", default=".")
    doctor.add_argument("--json", action="store_true", help="emit stable structured JSON")

    goal = sub.add_parser("goal", help="Brain-owned canonical Goal API for Gateway/operators")
    goal.add_argument("root", nargs="?", default=".")
    goal.add_argument("action", choices=[
        "create", "status", "show", "edit", "pause", "resume", "block", "complete", "clear",
        "criteria-add", "criteria-remove", "criteria-clear", "evaluate", "progress", "continuation",
    ])
    goal.add_argument("--scope", default="operator")
    goal.add_argument("--goal-id")
    goal.add_argument("--objective")
    goal.add_argument("--expected-version", type=int)
    goal.add_argument("--operation-id")
    goal.add_argument("--note")
    goal.add_argument("--criterion")
    goal.add_argument("--criterion-id")
    goal.add_argument("--progress-token")
    goal.add_argument("--tokens-used", type=int, default=0)
    goal.add_argument("--cost-used", type=float, default=0.0)
    goal.add_argument("--input", help="optional JSON file containing completion_contract/criteria/budget/evidence")
    goal.add_argument("--json", action="store_true", help="emit stable structured JSON")

    rollback = sub.add_parser("strategy-rollback", help="restore the exact known-good previous strategy revision")
    rollback.add_argument("root", nargs="?", default=".")
    rollback.add_argument("strategy_id")
    rollback.add_argument("--scope", default="operator")
    rollback.add_argument("--apply", action="store_true", help="apply restoration; default is dry-run")
    rollback.add_argument("--json", action="store_true", help="emit stable structured JSON")

    migrate = sub.add_parser("migrate", help="plan or apply explicit non-destructive Brain state migration")
    migrate.add_argument("root", nargs="?", default=".")
    migrate.add_argument("--apply", action="store_true", help="apply registered migration/metadata refresh; default is dry-run")

    plan = sub.add_parser("plan-integration", help="read-only integration plan; performs no installation")
    plan.add_argument("root", nargs="?", default=".")

    cadence = sub.add_parser("plan-cadence", help="emit scheduler requests from the persisted effective policy")
    cadence.add_argument("root", nargs="?", default=".")
    cadence.add_argument("--scope", default="operator")
    cadence.add_argument("--proactivity", type=int, choices=range(0, 5), default=None)
    cadence.add_argument("--background-ticks-per-day", type=int, default=None)

    hooks = sub.add_parser("cadence-hooks", help="emit portable scheduler argv hooks; Brain does not install a scheduler")
    hooks.add_argument("root", nargs="?", default=".")
    hooks.add_argument("--vendor", choices=["claude", "codex", "hermes"], required=True)
    hook_host_mode = hooks.add_mutually_exclusive_group(required=True)
    hook_host_mode.add_argument("--host-adapter", help="JSON bridge config for the real host/runtime adapter")
    hook_host_mode.add_argument(
        "--read-only-context",
        action="store_true",
        help="explicitly schedule ticks with the limited built-in current-context-only host",
    )
    hooks.add_argument("--scope", default="operator")
    hooks.add_argument("--proactivity", type=int, choices=range(0, 5), default=None)
    hooks.add_argument("--background-ticks-per-day", type=int, default=None)
    hooks.add_argument("--context-file", help="optional context file; valid only with --read-only-context")
    hooks.add_argument("--model")
    hooks.add_argument("--provider")
    return parser


def _print(data: object) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


def _tick_summary(result, host_selection: HostSelection, runtime: BrainRuntime) -> dict:
    return build_tick_summary(result, host_selection, runtime)


def _brain_owned_scopes(root: str) -> list[str]:
    report = inspect_host(root)
    if report.mode != HostMode.AI_VERSE_OS_V2:
        return []
    registry = read_direction_registry(Path(root).resolve())
    return sorted(
        scope
        for scope, record in registry.get("scopes", {}).items()
        if isinstance(record, dict) and record.get("owner") == "brain"
    )


def _require_native_host(root: str) -> None:
    report = inspect_host(root)
    if report.mode == HostMode.STANDALONE:
        raise ValidationError("Brain attachment requires a compatible AI-Verse OS root")
    if report.mode == HostMode.INCOMPATIBLE_AI_VERSE:
        raise ValidationError("Brain attachment blocked: incompatible AI-Verse OS host")


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "install":
            root = str(Path(args.root).resolve())
            _print({
                "ok": True,
                "state": "installed",
                "note": "The ai-verse-brain package is already available because this command is running.",
                "descriptor": component_descriptor(root),
            })
            return 0

        if args.command == "setup":
            result = setup_component(str(Path(args.root)), apply=args.apply)
            _print(result)
            return 0 if result.get("ok", False) else 3

        if args.command == "status":
            result = lifecycle_status(str(Path(args.root))).to_dict()
            _print(result)
            return 0 if result["state"] not in {"unhealthy"} else 2

        if args.command == "descriptor":
            _print(component_descriptor(str(Path(args.root))))
            return 0

        if args.command == "enable":
            result = enable_component(str(Path(args.root)), apply=args.apply)
            _print(result)
            return 0 if result.get("ok", False) else 3

        if args.command == "disable":
            result = disable_component(str(Path(args.root)), apply=args.apply)
            _print(result)
            return 0 if result.get("ok", False) else 3

        if args.command == "update":
            result = update_component(str(Path(args.root)), apply=args.apply)
            _print(result)
            return 0 if result.get("ok", False) else 3

        if args.command == "uninstall":
            result = uninstall_component(str(Path(args.root)), apply=args.apply)
            _print(result)
            return 0 if result.get("ok", False) else 3

        if args.command == "goal":
            root = str(Path(args.root).resolve())
            if read_installation_marker(root) is None:
                raise ValidationError("Brain is not initialized; run setup --apply first")
            service = BrainController(root).goals
            payload = {}
            if args.input:
                payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    raise ValidationError("Goal --input must contain a JSON object")
            evidence = [EvidenceRef(**item) for item in payload.get("evidence_refs", [])]
            if args.action == "create":
                if not args.operation_id or not args.objective:
                    raise ValidationError("goal create requires --operation-id and --objective")
                result = service.create(
                    args.scope, objective=args.objective, operation_id=args.operation_id,
                    completion_contract=payload.get("completion_contract"),
                    criteria=payload.get("criteria"),
                    budget_policy=payload.get("budget_policy"),
                    active=not bool(payload.get("draft", False)),
                    provenance=payload.get("provenance"),
                    source=AuthorityTier.EXPLICIT_USER, actor="user:cli",
                ).to_dict()
            elif args.action in {"status", "show"}:
                result = service.get(args.scope, args.goal_id) if args.goal_id else {"goals": service.list(args.scope)}
            elif args.action == "edit":
                if not args.goal_id or args.expected_version is None or not args.operation_id:
                    raise ValidationError("goal edit requires --goal-id --expected-version --operation-id")
                result = service.edit(
                    args.scope, args.goal_id, expected_version=args.expected_version,
                    operation_id=args.operation_id, objective=args.objective,
                    completion_contract=payload.get("completion_contract"),
                    budget_policy=payload.get("budget_policy"),
                    source=AuthorityTier.EXPLICIT_USER, actor="user:cli",
                ).to_dict()
            elif args.action in {"pause", "resume", "block", "complete", "clear"}:
                if not args.goal_id or args.expected_version is None or not args.operation_id:
                    raise ValidationError("goal transition requires --goal-id --expected-version --operation-id")
                transition_source = (
                    AuthorityTier.VERIFIED_EVIDENCE
                    if args.action in {"block", "complete"} and evidence
                    else AuthorityTier.EXPLICIT_USER
                )
                result = service.transition(
                    args.scope, args.goal_id, expected_version=args.expected_version,
                    operation_id=args.operation_id, action=args.action, note=args.note,
                    evidence_refs=evidence, criterion_results=payload.get("criterion_results"),
                    source=transition_source, actor="user:cli",
                ).to_dict()
            elif args.action == "criteria-add":
                if not args.goal_id or args.expected_version is None or not args.operation_id:
                    raise ValidationError("criteria-add requires --goal-id --expected-version --operation-id")
                criterion = payload.get("criterion", args.criterion)
                if criterion is None:
                    raise ValidationError("criteria-add requires --criterion or input criterion")
                result = service.criteria_add(
                    args.scope, args.goal_id, expected_version=args.expected_version,
                    operation_id=args.operation_id, criterion=criterion,
                    source=AuthorityTier.EXPLICIT_USER, actor="user:cli",
                ).to_dict()
            elif args.action == "criteria-remove":
                if not args.goal_id or args.expected_version is None or not args.operation_id or not args.criterion_id:
                    raise ValidationError("criteria-remove requires --goal-id --expected-version --operation-id --criterion-id")
                result = service.criteria_remove(
                    args.scope, args.goal_id, expected_version=args.expected_version,
                    operation_id=args.operation_id, criterion_id=args.criterion_id,
                    source=AuthorityTier.EXPLICIT_USER, actor="user:cli",
                ).to_dict()
            elif args.action == "criteria-clear":
                if not args.goal_id or args.expected_version is None or not args.operation_id:
                    raise ValidationError("criteria-clear requires --goal-id --expected-version --operation-id")
                result = service.criteria_clear(
                    args.scope, args.goal_id, expected_version=args.expected_version,
                    operation_id=args.operation_id,
                    source=AuthorityTier.EXPLICIT_USER, actor="user:cli",
                ).to_dict()
            elif args.action == "evaluate":
                if not args.goal_id or args.expected_version is None:
                    raise ValidationError("goal evaluate requires --goal-id --expected-version")
                result = service.evaluate(
                    args.scope, args.goal_id, expected_version=args.expected_version,
                    evidence_refs=evidence, criterion_results=payload.get("criterion_results"), wait_hint=payload.get("wait_hint"),
                ).to_dict()
            elif args.action == "progress":
                if not args.goal_id or args.expected_version is None or not args.operation_id or not args.progress_token:
                    raise ValidationError("goal progress requires --goal-id --expected-version --operation-id --progress-token")
                result = service.record_progress(
                    args.scope, args.goal_id, expected_version=args.expected_version,
                    operation_id=args.operation_id, progress_token=args.progress_token,
                    evidence_refs=evidence, tokens_used=args.tokens_used, cost_used=args.cost_used,
                ).to_dict()
            else:
                if not args.goal_id:
                    raise ValidationError("goal continuation requires --goal-id")
                result = service.continuation_contract(args.scope, args.goal_id)
            _print(result)
            return 0

        if args.command == "strategy-rollback":
            root = str(Path(args.root).resolve())
            if read_installation_marker(root) is None:
                raise ValidationError("Brain is not initialized; run setup --apply first")
            controller = BrainController(root)
            current = controller.store.load("strategy_rule", args.scope, args.strategy_id)
            previous_id = current.payload.get("previous_revision_ref")
            if not previous_id:
                raise ValidationError("strategy has no known-good previous revision")
            previous = controller.store.load("strategy_rule", args.scope, str(previous_id))
            if not args.apply:
                _print({
                    "ok": True, "dry_run": True, "current_strategy_id": current.id,
                    "current_status": current.status, "restored_strategy_id": previous.id,
                    "restored_status": previous.status,
                })
                return 0
            result = controller.strategy_revisions.rollback(
                args.scope, args.strategy_id, source=AuthorityTier.EXPLICIT_USER, actor="user:cli"
            )
            _print({"ok": True, "dry_run": False, "restoration": result.to_dict()})
            return 0

        if args.command == "init":
            root = str(Path(args.root))
            if args.apply:
                _print(initialize(root).to_dict())
                return 0
            plan = plan_init(root)
            _print(plan.to_dict())
            return 0 if plan.safe_to_apply else 3

        if args.command == "attach":
            root = str(Path(args.root).resolve())
            _require_native_host(root)
            current = brain_attachment(root)
            if not args.apply:
                _print({
                    "ok": True,
                    "dry_run": True,
                    "root": root,
                    "current": current,
                    "will_attach": current is None or current.get("installed") is not True,
                    "tracked_os_files_modified": False,
                })
                return 0
            _print({"ok": True, "attachment": attach_brain(root), "tracked_os_files_modified": False})
            return 0

        if args.command in {"disable", "detach"}:
            root = str(Path(args.root).resolve())
            _require_native_host(root)
            owners = _brain_owned_scopes(root)
            if owners:
                raise ValidationError(
                    "Brain cannot be disabled or detached while it owns strategic direction for: "
                    + ", ".join(owners)
                    + ". Transfer direction ownership before removing Brain availability."
                )
            current = brain_attachment(root)
            if not args.apply:
                _print({
                    "ok": True,
                    "dry_run": True,
                    "root": root,
                    "current": current,
                    "operation": args.command,
                    "canonical_brain_state_preserved": True,
                })
                return 0
            if args.command == "disable":
                attachment = set_brain_enabled(root, False)
                _print({"ok": True, "attachment": attachment, "canonical_brain_state_preserved": True})
            else:
                removed = detach_brain_registration(root)
                _print({"ok": True, "detached": removed, "canonical_brain_state_preserved": True})
            return 0

        if args.command == "onboard":
            root = str(Path(args.root))
            marker = read_installation_marker(root)
            if marker is None:
                _print({"ok": False, "error": "Brain is not initialized; run `ai-verse-brain init --apply` first"})
                return 4
            service = OnboardingService(BrainController(root))
            if not args.answers:
                _print(service.plan(args.scope).to_dict())
                return 0
            answers_path = Path(args.answers)
            answers = json.loads(answers_path.read_text(encoding="utf-8"))
            if not args.apply:
                _print({
                    "ok": True,
                    "dry_run": True,
                    "answers_path": str(answers_path),
                    "plan": service.plan(args.scope).to_dict(),
                    "note": "answers were not applied; rerun with --apply after review",
                })
                return 0
            _print(service.apply(answers, args.scope).to_dict())
            return 0

        if args.command == "direction-owner":
            root = str(Path(args.root))
            if read_installation_marker(root) is None:
                _print({"ok": False, "error": "Brain is not initialized; run `ai-verse-brain init --apply` first"})
                return 4
            if args.handover_to_brain and args.handover_to_os:
                raise ValueError("choose exactly one of --handover-to-brain or --handover-to-os")
            service = DirectionOwnershipService(BrainController(root))
            if not args.handover_to_brain and not args.handover_to_os:
                if args.apply or args.confirm_import or args.confirm_export:
                    raise ValueError(
                        "--apply/--confirm-import/--confirm-export require an explicit handover direction"
                    )
                _print(service.status(args.scope).to_dict())
                return 0

            if args.handover_to_brain:
                if args.confirm_export:
                    raise ValueError("--confirm-export is only valid with --handover-to-os")
                if not args.apply:
                    _print(service.plan(args.scope).to_dict())
                    return 0
                _print(service.handover(args.scope, confirm_import=args.confirm_import).to_dict())
                return 0

            if args.confirm_import:
                raise ValueError("--confirm-import is only valid with --handover-to-brain")
            if not args.apply:
                _print(service.plan_return_to_os(args.scope).to_dict())
                return 0
            _print(service.handback_to_os(args.scope, confirm_export=args.confirm_export).to_dict())
            return 0

        if args.command == "adapter-doctor":
            config = BridgeConfig.load(args.config)
            _print(adapter_doctor(config))
            return 0

        if args.command == "vendor-doctor":
            root = str(Path(args.root).resolve())
            config = vendor_bridge_config(
                args.vendor,
                model=args.model,
                provider=args.provider,
                timeout_seconds=args.timeout,
                env_names=args.env_name,
                binary=args.binary,
                cwd=root,
            )
            report = adapter_doctor(config)
            report["reasoner_only"] = True
            report["host_action_authority"] = False
            _print(report)
            return 0

        if args.command == "run-tick":
            root = str(Path(args.root).resolve())
            if read_installation_marker(root) is None:
                _print({"ok": False, "error": "Brain is not initialized; run `ai-verse-brain init --apply` first"})
                return 4
            scope = Scope(args.scope)
            host_selection = select_host(
                root,
                host_adapter_config=args.host_adapter,
                read_only_context=args.read_only_context,
                context_file=args.context_file,
            )
            reasoner, config = vendor_reasoner(
                args.vendor,
                model=args.model,
                provider=args.provider,
                timeout_seconds=args.timeout,
                env_names=args.env_name,
                binary=args.binary,
                cwd=root,
            )
            adapter_doctor(config)
            trigger = Trigger(
                trigger_type=args.trigger,
                scope=scope,
                idempotency_key=args.idempotency_key or f"cli:{args.trigger}:{scope.value}:{uuid4()}",
            )
            runtime = BrainRuntime(root)
            result = runtime.run_tick(
                trigger,
                host=host_selection.host,
                reasoner=reasoner,
                session_id=args.session_id,
            )
            _print(_tick_summary(result, host_selection, runtime))
            return 0 if result.ok else 5

        if args.command == "doctor":
            report = lifecycle_doctor(str(Path(args.root)))
            _print(report)
            return 0 if report["ok"] else 2

        if args.command == "migrate":
            root = str(Path(args.root))
            if args.apply:
                _print(apply_migration(root).to_dict())
                return 0
            migration = plan_migration(root)
            _print(migration.to_dict())
            return 0 if migration.safe_to_apply else 3

        if args.command == "plan-integration":
            plan = plan_integration(str(Path(args.root)))
            _print(plan.to_dict())
            return 0 if plan.safe_to_apply else 3

        if args.command == "plan-cadence":
            policy = effective_cadence_policy(
                str(Path(args.root).resolve()),
                scope=args.scope,
                proactivity=args.proactivity,
                background_ticks_per_day=args.background_ticks_per_day,
            )
            requests = plan_cadence(policy, args.scope)
            _print([item.to_dict() for item in requests])
            return 0

        if args.command == "cadence-hooks":
            _print(
                render_cadence_hooks(
                    str(Path(args.root).resolve()),
                    vendor=args.vendor,
                    scope=args.scope,
                    proactivity=args.proactivity,
                    background_ticks_per_day=args.background_ticks_per_day,
                    model=args.model,
                    provider=args.provider,
                    host_adapter_config=args.host_adapter,
                    read_only_context=args.read_only_context,
                    context_file=args.context_file,
                )
            )
            return 0
        return 1
    except (BrainError, OSError, ValueError, json.JSONDecodeError) as exc:
        _print({"ok": False, "error": str(exc), "command": args.command})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())