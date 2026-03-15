"""ZChatEvent — the core event envelope for the ZChat protocol."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from ulid import ULID

from zchat_protocol.operation_types import OperationType


@dataclass
class ZChatEvent:
    """A single event in the ZChat protocol."""

    id: str
    room: str
    type: OperationType
    from_: str
    timestamp: int
    content: Any
    content_type: str
    reply_to: str | None = None
    thread: str | None = None
    ephemeral: bool = False
    redacts: str | None = None
    ref: str | None = None

    @classmethod
    def create(
        cls,
        room: str,
        type: OperationType,
        from_: str,
        content: Any,
        content_type: str,
        reply_to: str | None = None,
        thread: str | None = None,
        ephemeral: bool = False,
        redacts: str | None = None,
        ref: str | None = None,
    ) -> ZChatEvent:
        """Create a new event with auto-generated id and timestamp."""
        return cls(
            id=str(ULID()),
            room=room,
            type=type,
            from_=from_,
            timestamp=int(time.time() * 1000),
            content=content,
            content_type=content_type,
            reply_to=reply_to,
            thread=thread,
            ephemeral=ephemeral,
            redacts=redacts,
            ref=ref,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dict. Maps from_ → 'from', reply_to → 'replyTo'."""
        d: dict[str, Any] = {
            "id": self.id,
            "room": self.room,
            "type": str(self.type),
            "from": self.from_,
            "timestamp": self.timestamp,
            "content": self.content,
            "contentType": self.content_type,
        }
        if self.reply_to is not None:
            d["replyTo"] = self.reply_to
        if self.thread is not None:
            d["thread"] = self.thread
        if self.ephemeral:
            d["ephemeral"] = True
        if self.redacts is not None:
            d["redacts"] = self.redacts
        if self.ref is not None:
            d["ref"] = self.ref
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ZChatEvent:
        """Deserialize from a dict."""
        return cls(
            id=d["id"],
            room=d["room"],
            type=OperationType(d["type"]),
            from_=d["from"],
            timestamp=d["timestamp"],
            content=d["content"],
            content_type=d["contentType"],
            reply_to=d.get("replyTo"),
            thread=d.get("thread"),
            ephemeral=d.get("ephemeral", False),
            redacts=d.get("redacts"),
            ref=d.get("ref"),
        )
