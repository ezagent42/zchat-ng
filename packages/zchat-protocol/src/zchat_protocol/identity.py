"""Identity — user:label@network addressing primitive."""

from __future__ import annotations

import re
from dataclasses import dataclass

_IDENTITY_RE = re.compile(
    r"^(?P<user>[a-zA-Z0-9_-]+)(?::(?P<label>[a-zA-Z0-9_-]+))?@(?P<network>[a-zA-Z0-9_-]+)$"
)


@dataclass(frozen=True)
class Identity:
    """A chat identity: user[:label]@network."""

    user: str
    network: str
    label: str | None = None

    @classmethod
    def parse(cls, s: str) -> Identity:
        """Parse an identity string like ``alice:ppt-maker@onesyn``."""
        m = _IDENTITY_RE.match(s)
        if not m:
            raise ValueError(f"Invalid identity string: {s!r}")
        return cls(
            user=m.group("user"),
            network=m.group("network"),
            label=m.group("label"),
        )

    @property
    def is_labeled(self) -> bool:
        """True when this identity has a label component."""
        return self.label is not None

    def __str__(self) -> str:
        if self.label:
            return f"{self.user}:{self.label}@{self.network}"
        return f"{self.user}@{self.network}"
