"""Tests for Identity parsing, display, and equality."""

import pytest
from zchat_protocol.identity import Identity


def test_parse_human():
    """Parse a simple user@network identity."""
    ident = Identity.parse("alice@onesyn")
    assert ident.user == "alice"
    assert ident.network == "onesyn"
    assert ident.label is None
    assert str(ident) == "alice@onesyn"


def test_parse_labeled():
    """Parse user:label@network identity."""
    ident = Identity.parse("alice:ppt-maker@onesyn")
    assert ident.user == "alice"
    assert ident.label == "ppt-maker"
    assert ident.network == "onesyn"
    assert str(ident) == "alice:ppt-maker@onesyn"


def test_is_labeled():
    """is_labeled is True only when label is set."""
    human = Identity.parse("bob@lan")
    labeled = Identity.parse("bob:helper@lan")
    assert human.is_labeled is False
    assert labeled.is_labeled is True


def test_equality():
    """Two identities with same fields are equal."""
    a = Identity.parse("alice@onesyn")
    b = Identity(user="alice", network="onesyn")
    assert a == b


def test_invalid_identity():
    """Malformed identity strings raise ValueError."""
    with pytest.raises(ValueError):
        Identity.parse("no-at-sign")
    with pytest.raises(ValueError):
        Identity.parse("@missing-user")
    with pytest.raises(ValueError):
        Identity.parse("bad spaces@net")
