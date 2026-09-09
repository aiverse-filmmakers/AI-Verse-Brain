from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional

from .cadence_plan import plan_cadence
from .controller import BrainController
from .effective_policy import assert_policy_tightens, clone_policy
from .policy import BrainPolicy, ProactivityLevel


def effective_cadence_policy(
    root: str,
    *,
    scope: str = "operator",
    proactivity: Optional[int] = None,
    background_ticks_per_day: Optional[int] = None,
) -> BrainPolicy:
    """Load canonical cadence policy and apply only explicit tightening overrides."""
    controller = BrainController(root)
    canonical = controller.refresh_policy(scope)
    if proactivity is None and background_ticks_per_day is None:
        return canonical

    override = clone_policy(canonical)
    if proactivity is not None:
        override.proactivity = ProactivityLevel(proactivity)
    if background_ticks_per_day is not None:
        override.resources.max_background_ticks_per_day = background_ticks_per_day
    override.validate()
    assert_policy_tightens(canonical, override, source="cadence override")
    return override


def render_cadence_hooks(
    root: str,
    *,
    vendor: str,
    scope: str = "operator",
    proactivity: Optional[int] = None,
    background_ticks_per_day: Optional[int] = None,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    context_file: Optional[str] = None,
) -> List[Dict[str, Any]]:
    policy = effective_cadence_policy(
        root,
        scope=scope,
        proactivity=proactivity,
        background_ticks_per_day=background_ticks_per_day,
    )
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
