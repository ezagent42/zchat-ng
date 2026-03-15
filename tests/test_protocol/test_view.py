"""Tests for View dataclass."""

from zchat_protocol.view import View


def test_view_roundtrip():
    """View to_dict/from_dict roundtrip (entries/gaps excluded)."""
    v = View(scope="room:general", filter={"type": "MSG"}, sort="ts")
    v.entries = [{"id": "1"}]
    v.gaps = [{"start": 0, "end": 100}]

    d = v.to_dict()
    assert "entries" not in d  # runtime-only
    assert "gaps" not in d
    assert d["scope"] == "room:general"

    restored = View.from_dict(d)
    assert restored.scope == "room:general"
    assert restored.entries == []  # default, not serialized


def test_view_defaults():
    """View has sensible defaults."""
    v = View(scope="room:general", filter=None)
    assert v.sort == "ts"
    assert v.entries == []
    assert v.gaps == []
    assert v.last_seen_ts is None
