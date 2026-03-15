"""ExtensionManifest — extension metadata parsed from TOML."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from typing import Any

from zchat_protocol.hook import Hook
from zchat_protocol.index import Index


@dataclass(frozen=True)
class ExtensionManifest:
    """Manifest describing a ZChat extension."""

    name: str
    version: str = ""
    description: str = ""
    requires_core: str = ""
    content_types: list[str] = field(default_factory=list)
    hooks: list[Hook] = field(default_factory=list)
    indexes: list[Index] = field(default_factory=list)

    @classmethod
    def from_toml(cls, toml_str: str) -> ExtensionManifest:
        """Parse a TOML string into an ExtensionManifest."""
        data = tomllib.loads(toml_str)
        hooks = [
            Hook(
                trigger=h["trigger"],
                handler=h["handler"],
                runtime=h["runtime"],
                priority=h.get("priority", 100),
                source=h.get("source", "user"),
                can_block=h.get("can_block", False),
            )
            for h in data.get("hooks", [])
        ]
        indexes = [
            Index(
                pattern=i["pattern"],
                queryable=i.get("queryable", False),
                retention=i.get("retention", "none"),
                ttl=i.get("ttl"),
            )
            for i in data.get("indexes", [])
        ]
        return cls(
            name=data.get("name", ""),
            version=data.get("version", ""),
            description=data.get("description", ""),
            requires_core=data.get("requires_core", ""),
            content_types=data.get("content_types", []),
            hooks=hooks,
            indexes=indexes,
        )
