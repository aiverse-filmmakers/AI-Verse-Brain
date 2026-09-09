from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional, Sequence

from .cadence_plan import plan_cadence
from .controller import BrainController
from .doctor import run_doctor
from .errors import BrainError
from .installation import initialize, plan_init, read_installation_marker
from .integration import plan_integration
from .onboarding import OnboardingService
from .policy import BrainPolicy, ProactivityLevel


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

    doctor = sub.add_parser("doctor", help="read-only host, installation, and Brain-state health checks")
    doctor.add_argument("root", nargs="?", default=".")

    plan = sub.add_parser("plan-integration", help="read-only integration plan; performs no installation")
    plan.add_argument("root", nargs="?", default=".")

    cadence = sub.add_parser("plan-cadence", help="emit scheduler requests without scheduling them")
    cadence.add_argument("--scope", default="operator")
    cadence.add_argument("--proactivity", type=int, choices=range(0, 5), default=2)
    cadence.add_argument("--background-ticks-per-day", type=int, default=4)
    return parser


def _print(data: object) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


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

        if args.command == "doctor":
            report = run_doctor(str(Path(args.root)))
            _print(report.to_dict())
            return 0 if report.ok else 2
        if args.command == "plan-integration":
            plan = plan_integration(str(Path(args.root)))
            _print(plan.to_dict())
            return 0 if plan.safe_to_apply else 3
        if args.command == "plan-cadence":
            policy = BrainPolicy(proactivity=ProactivityLevel(args.proactivity))
            policy.resources.max_background_ticks_per_day = args.background_ticks_per_day
            requests = plan_cadence(policy, args.scope)
            _print([item.to_dict() for item in requests])
            return 0
        return 1
    except (BrainError, OSError, ValueError, json.JSONDecodeError) as exc:
        _print({"ok": False, "error": str(exc), "command": args.command})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
