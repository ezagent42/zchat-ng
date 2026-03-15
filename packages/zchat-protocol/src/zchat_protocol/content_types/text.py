"""TextContent — simple plain-text content type."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TextContent:
    """Plain text message content."""

    text: str
    CONTENT_TYPE: str = "text/plain"
