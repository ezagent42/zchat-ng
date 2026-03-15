"""ZChatCLI — high-level API binding together Com and Acp backends."""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator

from zchat_protocol import Identity, OperationType, ZChatEvent

from zchat_cli.backends import AcpBackend, ComBackend
from zchat_cli.types import (
    DiagnosticReport,
    ExtensionInfo,
    NetworkStatus,
    Room,
    SpawnPreview,
    TemplateInfo,
    AgentConfigInfo,
    ZChatOperation,
)

# Default event types shown in watch
_DEFAULT_TYPES = frozenset({
    OperationType.MSG,
    OperationType.ASK,
    OperationType.ANSWER,
    OperationType.JOIN,
    OperationType.LEAVE,
    OperationType.PRESENCE,
})

_VERBOSE_TYPES = _DEFAULT_TYPES | {
    OperationType.TOOL_USE,
    OperationType.TOOL_RESULT,
}


class ZChatCLI:
    """High-level CLI operations layer."""

    def __init__(self, com: ComBackend, acp: AcpBackend) -> None:
        self.com = com
        self.acp = acp

    # ── Send ───────────────────────────────────────────────────────────

    async def send(self, target: str, content: str) -> None:
        """Send a message to a target (room name or identity string)."""
        identity = await self.com.get_identity()
        # Determine room: if target starts with #, it's a room; otherwise
        # it's an identity and we send to #general
        if target.startswith("#"):
            room = target
        else:
            room = "#general"

        event = ZChatEvent.create(
            room=room,
            type=OperationType.MSG,
            from_=str(identity),
            content=content,
            content_type="text/plain",
        )
        await self.com.publish(event)

    # ── Watch ──────────────────────────────────────────────────────────

    async def watch(
        self,
        room: str,
        *,
        last: int | None = None,
        no_follow: bool = False,
        verbose: bool = False,
        thinking: bool = False,
        show_all: bool = False,
    ) -> AsyncIterator[ZChatEvent]:
        """Watch events in a room, with filtering.

        Yields events matching the filter criteria. In no_follow mode,
        returns existing events and terminates. Otherwise streams live.
        """
        # Build the set of allowed types
        if show_all:
            allowed = None  # no filter
        elif thinking:
            allowed = _DEFAULT_TYPES | {OperationType.THINKING}
        elif verbose:
            allowed = _VERBOSE_TYPES
        else:
            allowed = _DEFAULT_TYPES

        if no_follow:
            # Return historical events
            events = await self.com.query_events(room, last=last)
            for event in events:
                if allowed is None or event.type in allowed:
                    yield event
            return

        # Realtime streaming
        async for event in self.com.subscribe(room):
            if allowed is None or event.type in allowed:
                yield event

    # ── Ask / Answer ───────────────────────────────────────────────────

    async def ask(
        self, target: str, question: str, timeout: float = 30.0
    ) -> ZChatEvent:
        """Publish an ASK event and wait for an ANSWER referencing it."""
        identity = await self.com.get_identity()
        room = target if target.startswith("#") else "#general"

        ask_event = ZChatEvent.create(
            room=room,
            type=OperationType.ASK,
            from_=str(identity),
            content=question,
            content_type="text/plain",
        )
        await self.com.publish(ask_event)

        # Subscribe and wait for an answer referencing our ask
        async for event in self.com.subscribe(room):
            if (
                event.type == OperationType.ANSWER
                and event.ref == ask_event.id
            ):
                return event

        # Should not reach here in normal usage
        raise TimeoutError("No answer received")

    async def answer(self, ask_id: str, text: str) -> None:
        """Publish an ANSWER event referencing a pending ASK."""
        identity = await self.com.get_identity()
        # Find the original ask event to get the room
        ask_event = await self.com.get_event(ask_id)
        room = ask_event.room if ask_event else "#general"

        answer_event = ZChatEvent.create(
            room=room,
            type=OperationType.ANSWER,
            from_=str(identity),
            content=text,
            content_type="text/plain",
            ref=ask_id,
        )
        await self.com.publish(answer_event)

    # ── Spawn ──────────────────────────────────────────────────────────

    async def spawn(self, agent_name: str) -> Identity:
        """Spawn a named agent."""
        preview = await self.acp.prepare_spawn(agent_name)
        return await self.acp.confirm_spawn(preview)

    async def spawn_adhoc(self, template: str, name: str) -> Identity:
        """Spawn an ad-hoc agent from a template."""
        preview = await self.acp.prepare_spawn(agent_name=name, template=template)
        return await self.acp.confirm_spawn(preview)

    async def spawn_confirm(self, preview: SpawnPreview) -> Identity:
        """Confirm a previously prepared spawn."""
        return await self.acp.confirm_spawn(preview)

    # ── Sessions ───────────────────────────────────────────────────────

    async def session_attach(self, agent_id: str) -> None:
        """Attach to an agent session."""
        await self.acp.attach(agent_id)

    async def session_detach(self, agent_id: str) -> None:
        """Detach from an agent session."""
        await self.acp.detach(agent_id)

    # ── Rooms ──────────────────────────────────────────────────────────

    async def rooms(self) -> list[Room]:
        """List available rooms."""
        return await self.com.rooms()

    async def members(self, room: str) -> list[Identity]:
        """List members of a room."""
        return await self.com.members(room)

    # ── Status / Doctor ────────────────────────────────────────────────

    async def status(self) -> NetworkStatus:
        """Get overall network status."""
        network = await self.com.get_network()
        if network.online:
            return NetworkStatus.HEALTHY
        return NetworkStatus.OFFLINE

    async def doctor(self) -> DiagnosticReport:
        """Run diagnostic checks."""
        return await self.com.doctor()

    # ── Stubs (not yet implemented) ────────────────────────────────────

    async def on_message(self, callback: Any) -> None:
        """Register a message callback (stub)."""

    async def on_session_update(self, callback: Any) -> None:
        """Register a session update callback (stub)."""

    async def on_permission_request(self, callback: Any) -> None:
        """Register a permission request callback (stub)."""

    async def ext_install(self, name: str) -> None:
        """Install an extension (stub)."""

    async def ext_uninstall(self, name: str) -> None:
        """Uninstall an extension (stub)."""

    async def ext_list(self) -> list[ExtensionInfo]:
        """List installed extensions (stub)."""
        return []

    async def template_init(self, name: str) -> None:
        """Initialize a template (stub)."""

    async def template_list(self) -> list[TemplateInfo]:
        """List available templates (stub)."""
        return []

    async def agent_init(self, name: str) -> None:
        """Initialize an agent config (stub)."""

    async def agent_list(self) -> list[AgentConfigInfo]:
        """List agent configs (stub)."""
        return []
