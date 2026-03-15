"""Tests for ZChatEvent, Annotation, Hook, Message."""

import pytest
from zchat_protocol.zchat_event import ZChatEvent
from zchat_protocol.operation_types import OperationType
from zchat_protocol.annotation import Annotation
from zchat_protocol.hook import Hook
from zchat_protocol.message import Message, Target
from zchat_protocol.identity import Identity


# --- ZChatEvent ---

def test_zchat_event_roundtrip():
    """ZChatEvent create() → to_dict() → from_dict() preserves fields."""
    ev = ZChatEvent.create(
        room="general",
        type=OperationType.MSG,
        from_="alice@onesyn",
        content={"text": "hello"},
        content_type="text/plain",
    )
    assert ev.room == "general"
    assert ev.type == OperationType.MSG
    assert ev.from_ == "alice@onesyn"
    assert ev.id is not None
    assert ev.timestamp > 0

    d = ev.to_dict()
    assert d["from"] == "alice@onesyn"  # from_ → "from"
    assert "from_" not in d

    restored = ZChatEvent.from_dict(d)
    assert restored.id == ev.id
    assert restored.room == ev.room
    assert restored.from_ == ev.from_


def test_zchat_event_ref():
    """ZChatEvent with ref field roundtrips."""
    ev = ZChatEvent.create(
        room="general",
        type=OperationType.ANNOTATE,
        from_="bob@onesyn",
        content={"key": "priority", "value": "high"},
        content_type="annotation",
        ref="evt_123",
    )
    d = ev.to_dict()
    assert d["ref"] == "evt_123"
    restored = ZChatEvent.from_dict(d)
    assert restored.ref == "evt_123"


def test_zchat_event_reply_to():
    """ZChatEvent with reply_to uses camelCase in dict."""
    ev = ZChatEvent.create(
        room="general",
        type=OperationType.MSG,
        from_="alice@onesyn",
        content={"text": "reply"},
        content_type="text/plain",
        reply_to="evt_000",
    )
    d = ev.to_dict()
    assert d["replyTo"] == "evt_000"
    assert "reply_to" not in d
    restored = ZChatEvent.from_dict(d)
    assert restored.reply_to == "evt_000"


def test_zchat_event_ephemeral():
    """ZChatEvent with ephemeral flag roundtrips."""
    ev = ZChatEvent.create(
        room="general",
        type=OperationType.TYPING,
        from_="alice@onesyn",
        content={},
        content_type="typing",
        ephemeral=True,
    )
    d = ev.to_dict()
    assert d["ephemeral"] is True
    restored = ZChatEvent.from_dict(d)
    assert restored.ephemeral is True


# --- Annotation ---

def test_annotation_construction():
    """Annotation frozen dataclass constructs correctly."""
    target = Identity.parse("alice@onesyn")
    ann = Annotation(target=target, key="priority", value="high", stage="draft")
    assert ann.target == target
    assert ann.key == "priority"
    assert ann.value == "high"
    assert ann.stage == "draft"


# --- Hook ---

def test_hook_construction():
    """Hook frozen dataclass with defaults."""
    h = Hook(trigger="on_msg", handler="log_handler", runtime="python")
    assert h.trigger == "on_msg"
    assert h.priority == 100
    assert h.source == "user"
    assert h.can_block is False


# --- Message ---

def test_message_construction():
    """Message dataclass with Target."""
    sender = Identity.parse("alice@onesyn")
    target = Target(room="general")
    msg = Message(
        id="msg_1",
        ts=1000,
        sender=sender,
        target=target,
        content={"text": "hi"},
        content_type="text/plain",
    )
    assert msg.sender == sender
    assert msg.target.room == "general"
    assert msg.annotations == []
