from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional, Sequence
from uuid import uuid4

from .bridge import BridgeConfig, adapter_doctor
from .cadence import Trigger
from .cadence_hooks import effective_cadence_policy, render_cadence_hooks
from .cadence_plan import plan_cadence
from .controller import BrainController
from .direction_ownership import DirectionOwnershipService
from .doctor import run_doctor
from .errors import BrainError
from .host_selection import HostSelection, select_host
from .installation import initialize, plan_init, read_installation_marker
from .integration import plan_integration
from .migration import apply_migration, plan_migration
from .models import Scope
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

    onboard = sub.add_parser("onboard", help="inspect or apply explicit user intent onboarding")
    onboard.add_argument("root", nargs="?", default=".")
    onboard.add_argument("--scope", default="operator")
    onboard.add_argument("--answers", help="path to a JSON answers file")
    onboard.add_argument("--apply", action="store_true", help="apply explicit answers as confirmed Brain intent/practices")

    direction = sub.add_parser("direction-owner", help="inspect or explicitly hand OS strategic direction to Brain")
    direction.add_argument("root", nargs="?", default=".")
    direction.add_argument("--scope", default="operator")
    direction.add_argument("--handover-to-brain", action="store_true", help="plan a one-way explicit handover from OS to Brain")
    direction.add_argument("--apply", action="store_true", help="apply the handover; requires --handover-to-brain and --confirm-import")
    direction.add_argument("--confirm-import", action="store_true", help="explicitly confirm importing discovered OS goals/objectives with provenance")

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


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init":
            root = str(Path(args.root))
            if args.apply:
                _print(initialize(root).to_dict())
                return 0
            plan = plan_init(root)
            _print(plan.to_dict())
            return 0 if plan.safe_to_apply else 3

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
            service = DirectionOwnershipService(BrainController(root))
            if not args.handover_to_brain:
                if args.apply or args.confirm_import:
                    raise ValueError("--apply/--confirm-import require --handover-to-brain")
                _print(service.status(args.scope).to_dict())
                return 0
            if not args.apply:
                _print(service.plan(args.scope).to_dict())
                return 0
            _print(service.handover(args.scope, confirm_import=args.confirm_import).to_dict())
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
            report = run_doctor(str(Path(args.root)))
            _print(report.to_dict())
            return 0 if report.ok else 2

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