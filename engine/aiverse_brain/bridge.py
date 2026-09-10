from __future__ import annotations

"""Bridge façade adding host action-permission authorization to protocol v1."""

from typing import Any, Dict

from .bridge_legacy import *  # noqa: F401,F403
from .bridge_legacy import BridgeHostAdapter as _CoreBridgeHostAdapter


class BridgeHostAdapter(_CoreBridgeHostAdapter):
    """Bridge host adapter with the restrictive ``authorize_action`` operation."""

    def authorize_action(self, request: Dict[str, Any]) -> Dict[str, Any]:
        return self._object(self._call("authorize_action", {"request": request}), "authorize_action")
