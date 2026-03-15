"""Hook — event trigger definitions for extensions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Hook:
    """A hook that fires on a specific trigger."""

    trigger: str
    handler: str
    runtime: str
    priority: int = 100
    source: str = "user"
    can_block: bool = False
