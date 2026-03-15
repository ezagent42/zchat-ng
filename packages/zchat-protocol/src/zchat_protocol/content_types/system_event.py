"""SystemEvent — system-level lifecycle events."""

from __future__ import annotations

from dataclasses import dataclass

from zchat_protocol.identity import Identity

_VALID_EVENT_TYPES = frozenset({"join", "leave", "offline", "online", "closed"})


@dataclass(frozen=True)
class SystemEvent:
    """A system event such as join, leave, or presence change."""

    event_type: str
    subject: Identity
    detail: str | None = None

    def __post_init__(self) -> None:
        if self.event_type not in _VALID_EVENT_TYPES:
            raise ValueError(
                f"Invalid event_type {self.event_type!r}; "
                f"must be one of {sorted(_VALID_EVENT_TYPES)}"
            )
