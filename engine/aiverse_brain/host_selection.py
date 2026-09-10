from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .bridge import BridgeConfig, BridgeHostAdapter, JSONSubprocessBridge
from .errors import ValidationError
from .local_host import ReadOnlyContextHost

REQUIRED_HOST_READ_OPERATIONS: Tuple[str, ...] = (
    "read_context",
    "retrieve_history",
    "list_capabilities",
    "list_connections",
)


@dataclass(frozen=True)
class HostSelection:
    """One explicit host choice for a Brain runtime invocation."""

    host: Any
    mode: str
    real_host: bool
    adapter_id: str
    operations: Tuple[str, ...]
    idempotency_supported: bool = False
    config_name: Optional[str] = None
    config_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "real_host": self.real_host,
            "adapter_id": self.adapter_id,
            "operations": list(self.operations),
            "idempotency_supported": self.idempotency_supported,
            "config_name": self.config_name,
            "config_path": self.config_path,
        }


def validate_host_selection_options(
    *,
    host_adapter_config: Optional[str],
    read_only_context: bool,
    context_file: Optional[str] = None,
) -> None:
    has_adapter = bool(host_adapter_config and str(host_adapter_config).strip())
    has_read_only = bool(read_only_context)
    if has_adapter == has_read_only:
        raise ValidationError(
            "select exactly one host mode: --host-adapter CONFIG for a real host, "
            "or --read-only-context for the explicit limited fallback"
        )
    if has_adapter and context_file:
        raise ValidationError("--context-file is valid only with --read-only-context")


def select_host(
    root: str,
    *,
    host_adapter_config: Optional[str] = None,
    read_only_context: bool = False,
    context_file: Optional[str] = None,
) -> HostSelection:
    """Select and live-validate the exact host used for this invocation.

    A requested real host is never silently replaced with ReadOnlyContextHost.
    Bridge loading, process startup, protocol, or operation failures propagate
    fail-closed to the caller.
    """

    validate_host_selection_options(
        host_adapter_config=host_adapter_config,
        read_only_context=read_only_context,
        context_file=context_file,
    )

    if read_only_context:
        host = ReadOnlyContextHost(root, context_file=context_file)
        return HostSelection(
            host=host,
            mode="read-only-context",
            real_host=False,
            adapter_id="builtin:read-only-context",
            operations=("read_context",),
        )

    assert host_adapter_config is not None
    config_path = Path(host_adapter_config).expanduser().resolve()
    config = BridgeConfig.load(str(config_path))
    host = BridgeHostAdapter(JSONSubprocessBridge(config))
    description = host.description
    missing = sorted(set(REQUIRED_HOST_READ_OPERATIONS) - set(description.operations))
    if missing:
        raise ValidationError(
            "selected host adapter is incomplete; missing required runtime read operations: "
            + ", ".join(missing)
        )
    return HostSelection(
        host=host,
        mode="bridge-host",
        real_host=True,
        adapter_id=description.adapter_id,
        operations=description.operations,
        idempotency_supported=description.idempotency_supported,
        config_name=config.name,
        config_path=str(config_path),
    )
