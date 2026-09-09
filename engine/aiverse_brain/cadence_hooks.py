from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional

from .cadence_plan import plan_cadence
from .policy import BrainPolicy, ProactivityLevel


def render_cadence_hooks(
    root: str,
    *,
    vendor: str,
    scope: str = "operator",
    proactivity: int = 2,
    background_ticks_per_day: int = 4,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    context_file: Optional[str] = None,
) -> List[Dict[str, Any]]:
    policy = BrainPolicy(proactivity=ProactivityLevel(proactivity))
    policy.resources.max_background_ticks_per_day = background_ticks_per_day
    requests = plan_cadence(policy, scope)
    hooks: List[Dict[str, Any]] = []
    for request in requests:
        command = [
            sys.executable,
            "-m",
            "aiverse_brain.cli",
            "run-tick",
            root,
            "--vendor",
            vendor,
            "--scope",
            scope,
            "--trigger",
            request.trigger_type,
        ]
        if model:
            command.extend(["--model", model])
        if provider:
            command.extend(["--provider", provider])
        if context_file:
            command.extend(["--context-file", context_file])
        hooks.append(
            {
                "trigger_type": request.trigger_type,
                "delivery": request.delivery,
                "interval_seconds": request.interval_seconds,
                "reason": request.reason,
                "argv": command,
                "scheduler_owned_by_brain": False,
            }
        )
    return hooks
