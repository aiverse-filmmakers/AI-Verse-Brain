from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional, Sequence

from .cadence_plan import plan_cadence
from .doctor import run_doctor
from .integration import plan_integration
from .policy import BrainPolicy, ProactivityLevel


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai-verse-brain", description="AI-Verse Brain development utilities")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="read-only host and Brain-state health checks")
    doctor.add_argument("root", nargs="?", default=".")

    plan = sub.add_parser("plan-integration", help="read-only integration plan; performs no installation")
    plan.add_argument("root", nargs="?", default=".")

    cadence = sub.add_parser("plan-cadence", help="emit scheduler requests without scheduling them")
    cadence.add_argument("--scope", default="operator")
    cadence.add_argument("--proactivity", type=int, choices=range(0, 5), default=2)
    cadence.add_argument("--background-ticks-per-day", type=int, default=4)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "doctor":
        report = run_doctor(str(Path(args.root)))
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
        return 0 if report.ok else 2
    if args.command == "plan-integration":
        plan = plan_integration(str(Path(args.root)))
        print(json.dumps(plan.to_dict(), indent=2, sort_keys=True))
        return 0 if plan.safe_to_apply else 3
    if args.command == "plan-cadence":
        policy = BrainPolicy(proactivity=ProactivityLevel(args.proactivity))
        policy.resources.max_background_ticks_per_day = args.background_ticks_per_day
        requests = plan_cadence(policy, args.scope)
        print(json.dumps([item.to_dict() for item in requests], indent=2, sort_keys=True))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
