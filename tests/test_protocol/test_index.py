"""Tests for Index factory class methods."""

from zchat_protocol.index import Index


def test_room_events_index():
    """Index.room_events() creates correct pattern."""
    idx = Index.room_events()
    assert idx.pattern == "room:*:events"
    assert idx.queryable is True


def test_presence_index():
    """Index.presence() creates correct pattern."""
    idx = Index.presence()
    assert idx.pattern == "presence:*"
    assert idx.retention == "ephemeral"


def test_network_announce_index():
    """Index.network_announce() creates correct pattern."""
    idx = Index.network_announce()
    assert idx.pattern == "network:announce"
    assert idx.queryable is True
