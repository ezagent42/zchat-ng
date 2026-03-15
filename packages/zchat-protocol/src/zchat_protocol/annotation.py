"""Annotation — metadata attached to events."""

from __future__ import annotations

from dataclasses import dataclass

from zchat_protocol.identity import Identity


@dataclass(frozen=True)
class Annotation:
    """An annotation targeting an identity with a key-value pair."""

    target: Identity
    key: str
    value: str
    stage: str
