"""OperationType — enumeration of all ZChat operation types."""

from __future__ import annotations

from enum import StrEnum


class OperationType(StrEnum):
    """All recognized operation types in the ZChat protocol."""

    MSG = "MSG"
    TYPING = "TYPING"
    THINKING = "THINKING"
    TOOL_USE = "TOOL_USE"
    TOOL_RESULT = "TOOL_RESULT"
    ASK = "ASK"
    ANSWER = "ANSWER"
    JOIN = "JOIN"
    LEAVE = "LEAVE"
    PRESENCE = "PRESENCE"
    ANNOTATE = "ANNOTATE"
    REDACT = "REDACT"
    READ = "READ"
    DISCOVER = "DISCOVER"
    CARD = "CARD"
