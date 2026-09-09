from __future__ import annotations

import sys
from typing import Iterable, Optional, Tuple

from .bridge import BridgeConfig, BridgeReasonerAdapter, JSONSubprocessBridge
from .vendor_bridge import SUPPORTED_VENDORS


def vendor_bridge_config(
    vendor: str,
    *,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    timeout_seconds: float = 120.0,
    env_names: Iterable[str] = (),
    binary: Optional[str] = None,
    cwd: Optional[str] = None,
) -> BridgeConfig:
    if vendor not in SUPPORTED_VENDORS:
        raise ValueError(f"unsupported vendor: {vendor!r}")
    command = [
        sys.executable,
        "-m",
        "aiverse_brain.vendor_bridge",
        "--vendor",
        vendor,
        "--timeout",
        str(float(timeout_seconds)),
    ]
    if binary:
        command.extend(["--binary", binary])
    if model:
        command.extend(["--model", model])
    if provider:
        command.extend(["--provider", provider])
    return BridgeConfig(
        name=f"{vendor}-reasoner",
        command=tuple(command),
        timeout_seconds=min(600.0, float(timeout_seconds) + 15.0),
        env_names=tuple(env_names),
        model_id=f"{vendor}:cli" + (f":{model}" if model else ""),
        cwd=cwd,
    )


def vendor_reasoner(
    vendor: str,
    *,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    timeout_seconds: float = 120.0,
    env_names: Iterable[str] = (),
    binary: Optional[str] = None,
    cwd: Optional[str] = None,
) -> Tuple[BridgeReasonerAdapter, BridgeConfig]:
    config = vendor_bridge_config(
        vendor,
        model=model,
        provider=provider,
        timeout_seconds=timeout_seconds,
        env_names=env_names,
        binary=binary,
        cwd=cwd,
    )
    return BridgeReasonerAdapter(JSONSubprocessBridge(config)), config
