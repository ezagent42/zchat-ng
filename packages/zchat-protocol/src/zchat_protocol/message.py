"""Message — high-level message abstraction."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from zchat_protocol.annotation import Annotation
from zchat_protocol.identity import Identity


@dataclass
class Target:
    """The target of a message (room, identity, or both)."""

    room: str | None = None
    identity: Identity | None = None


@dataclass
class Message:
    """A chat message with sender, target, content and annotations."""

    id: str
    ts: int
    sender: Identity
    target: Target
    content: Any
    content_type: str
    annotations: list[Annotation] = field(default_factory=list)
