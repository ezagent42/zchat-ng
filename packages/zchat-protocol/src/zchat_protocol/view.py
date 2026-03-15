"""View — a filtered, sorted view over events."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class View:
    """A view specification over a scope of events."""

    scope: str
    filter: dict[str, Any] | None
    sort: str = "ts"
    group: str | None = None
    fold: str | None = None
    entries: list[dict[str, Any]] = field(default_factory=list)
    gaps: list[dict[str, Any]] = field(default_factory=list)
    last_seen_ts: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict. entries and gaps are runtime-only, not included."""
        d: dict[str, Any] = {"scope": self.scope}
        if self.filter is not None:
            d["filter"] = self.filter
        d["sort"] = self.sort
        if self.group is not None:
            d["group"] = self.group
        if self.fold is not None:
            d["fold"] = self.fold
        if self.last_seen_ts is not None:
            d["lastSeenTs"] = self.last_seen_ts
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> View:
        """Deserialize from dict."""
        return cls(
            scope=d["scope"],
            filter=d.get("filter"),
            sort=d.get("sort", "ts"),
            group=d.get("group"),
            fold=d.get("fold"),
            last_seen_ts=d.get("lastSeenTs"),
        )
