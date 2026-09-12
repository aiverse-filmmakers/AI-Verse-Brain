from __future__ import annotations

"""Bridge façade adding host action-permission authorization to protocol v1."""

from typing import Any, Dict

from .bridge_legacy import *  # noqa: F401,F403
from .bridge_legacy import BridgeHostAdapter as _CoreBridgeHostAdapter


class BridgeHostAdapter(_CoreBridgeHostAdapter):
    """Bridge host adapter with restrictive authorization and optional Data reads."""

    def query_data(self, request: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(request, dict):
            raise TypeError("query_data request must be an object")
        return self._object(self._call("query_data", request), "query_data")

    def authorize_action(self, request: Dict[str, Any]) -> Dict[str, Any]:
        return self._object(self._call("authorize_action", {"request": request}), "authorize_action")
