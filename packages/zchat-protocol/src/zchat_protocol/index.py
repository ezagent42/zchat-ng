"""Index — data index pattern definitions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Index:
    """An index definition with pattern matching and retention policy."""

    pattern: str
    queryable: bool = False
    retention: str = "none"
    ttl: int | None = None

    @classmethod
    def room_events(cls) -> Index:
        return cls(pattern="room:*:events", queryable=True)

    @classmethod
    def room_state(cls) -> Index:
        return cls(pattern="room:*:state", queryable=True)

    @classmethod
    def room_ephemeral(cls) -> Index:
        return cls(pattern="room:*:ephemeral", retention="ephemeral")

    @classmethod
    def presence(cls) -> Index:
        return cls(pattern="presence:*", retention="ephemeral")

    @classmethod
    def network_announce(cls) -> Index:
        return cls(pattern="network:announce", queryable=True)

    @classmethod
    def network_join(cls) -> Index:
        return cls(pattern="network:join", queryable=True)
