"""CLI-specific dataclasses for ZChat operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from zchat_protocol import Identity, ZChatEvent


@dataclass(slots=True)
class NetworkInfo:
    """Information about a network."""

    name: str
    peer_count: int = 0
    online: bool = False


@dataclass(slots=True)
class Room:
    """A chat room."""

    name: str
    topic: str = ""
    member_count: int = 0


@dataclass(slots=True)
class SpawnPreview:
    """Preview of an agent spawn before confirmation."""

    agent_name: str
    template: str = ""
    model: str = ""
    estimated_cost: float = 0.0


class SessionStatus(StrEnum):
    """Status of an agent session."""

    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass(slots=True)
class SessionInfo:
    """Information about an agent session."""

    session_id: str
    agent: Identity
    status: SessionStatus = SessionStatus.RUNNING
    attached: bool = False


class NetworkStatus(StrEnum):
    """Overall network status."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    OFFLINE = "offline"


@dataclass(slots=True)
class DiagnosticReport:
    """Results from a doctor/diagnostic check."""

    checks: dict[str, bool] = field(default_factory=dict)
    messages: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when all checks pass."""
        return all(self.checks.values()) if self.checks else True


@dataclass(slots=True)
class TemplateInfo:
    """Metadata about an agent template."""

    name: str
    description: str = ""
    path: str = ""


@dataclass(slots=True)
class AgentConfigInfo:
    """Metadata about an agent configuration."""

    name: str
    template: str = ""
    model: str = ""


@dataclass(slots=True)
class ExtensionInfo:
    """Metadata about an installed extension."""

    name: str
    version: str = ""
    enabled: bool = True


@dataclass(slots=True)
class ZChatOperation:
    """A CLI operation result wrapping a ZChatEvent."""

    event: ZChatEvent
    source: str = "local"
    handled: bool = False
