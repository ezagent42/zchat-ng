"""AcpPayload — JSON-RPC 2.0 dataclass for Agent Communication Protocol."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

_SENTINEL = object()


@dataclass
class AcpPayload:
    """JSON-RPC 2.0 payload for ACP messages."""

    jsonrpc: str = "2.0"
    method: str | None = None
    params: dict[str, Any] | None = None
    id: str | None = None
    result: Any = None
    error_data: dict[str, Any] | None = None

    @classmethod
    def request(
        cls,
        method: str,
        params: dict[str, Any] | None = None,
        id: str | None = None,
    ) -> AcpPayload:
        """Create a JSON-RPC request payload."""
        return cls(method=method, params=params, id=id)

    @classmethod
    def response(
        cls,
        result: Any,
        id: str | None = None,
    ) -> AcpPayload:
        """Create a JSON-RPC response payload."""
        return cls(result=result, id=id)

    @classmethod
    def error(
        cls,
        code: int,
        message: str,
        id: str | None = None,
        data: Any = None,
    ) -> AcpPayload:
        """Create a JSON-RPC error payload."""
        err: dict[str, Any] = {"code": code, "message": message}
        if data is not None:
            err["data"] = data
        return cls(error_data=err, id=id)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        d: dict[str, Any] = {"jsonrpc": self.jsonrpc}
        if self.method is not None:
            d["method"] = self.method
        if self.params is not None:
            d["params"] = self.params
        if self.id is not None:
            d["id"] = self.id
        if self.result is not None:
            d["result"] = self.result
        if self.error_data is not None:
            d["error"] = self.error_data
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AcpPayload:
        """Deserialize from a dict."""
        return cls(
            jsonrpc=d.get("jsonrpc", "2.0"),
            method=d.get("method"),
            params=d.get("params"),
            id=d.get("id"),
            result=d.get("result"),
            error_data=d.get("error"),
        )

    def to_json(self) -> str:
        """Serialize to a JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, s: str) -> AcpPayload:
        """Deserialize from a JSON string."""
        return cls.from_dict(json.loads(s))
