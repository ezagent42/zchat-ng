"""MockComBackend — in-memory ComBackend for testing."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import AsyncIterator

from zchat_protocol import Identity, ZChatEvent

from zchat_cli.types import (
    AgentConfigInfo,
    DiagnosticReport,
    NetworkInfo,
    Room,
    TemplateInfo,
)


class MockComBackend:
    """In-memory implementation of ComBackend for testing."""

    def __init__(self) -> None:
        self.identity = Identity(user="mock-user", network="mocknet")
        self.network = NetworkInfo(name="mocknet", peer_count=1, online=True)
        self._events: dict[str, list[ZChatEvent]] = defaultdict(list)
        self._subscribers: dict[str, list[asyncio.Queue[ZChatEvent]]] = defaultdict(list)
        self._rooms: list[Room] = [Room(name="#general", topic="General chat", member_count=1)]
        self._members: dict[str, list[Identity]] = {"#general": [self.identity]}
        self._handled: set[str] = set()
        self.call_log: list[str] = []

    async def get_identity(self) -> Identity:
        self.call_log.append("get_identity")
        return self.identity

    async def get_network(self) -> NetworkInfo:
        self.call_log.append("get_network")
        return self.network

    async def get_peers(self) -> list[Identity]:
        self.call_log.append("get_peers")
        return [self.identity]

    async def setup_identity(self, user: str, network: str) -> Identity:
        self.call_log.append("setup_identity")
        self.identity = Identity(user=user, network=network)
        return self.identity

    async def room_create(self, name: str, topic: str = "") -> Room:
        self.call_log.append("room_create")
        room = Room(name=name, topic=topic, member_count=1)
        self._rooms.append(room)
        self._members[name] = [self.identity]
        return room

    async def room_invite(self, room: str, identity: Identity) -> None:
        self.call_log.append("room_invite")
        if room in self._members:
            self._members[room].append(identity)

    async def room_leave(self, room: str) -> None:
        self.call_log.append("room_leave")

    async def rooms(self) -> list[Room]:
        self.call_log.append("rooms")
        return list(self._rooms)

    async def members(self, room: str) -> list[Identity]:
        self.call_log.append("members")
        return list(self._members.get(room, []))

    async def publish(self, event: ZChatEvent) -> None:
        self.call_log.append("publish")
        self._events[event.room].append(event)
        for q in self._subscribers.get(event.room, []):
            await q.put(event)

    async def subscribe(self, room: str) -> AsyncIterator[ZChatEvent]:
        self.call_log.append("subscribe")
        q: asyncio.Queue[ZChatEvent] = asyncio.Queue()
        self._subscribers[room].append(q)
        try:
            while True:
                event = await q.get()
                yield event
        finally:
            self._subscribers[room].remove(q)

    async def query_events(
        self, room: str, *, last: int | None = None
    ) -> list[ZChatEvent]:
        self.call_log.append("query_events")
        events = self._events.get(room, [])
        if last is not None:
            return events[-last:]
        return list(events)

    async def get_event(self, event_id: str) -> ZChatEvent | None:
        self.call_log.append("get_event")
        for room_events in self._events.values():
            for event in room_events:
                if event.id == event_id:
                    return event
        return None

    async def is_handled(self, event_id: str) -> bool:
        self.call_log.append("is_handled")
        return event_id in self._handled

    async def mark_handled(self, event_id: str) -> None:
        self.call_log.append("mark_handled")
        self._handled.add(event_id)

    async def doctor(self) -> DiagnosticReport:
        self.call_log.append("doctor")
        return DiagnosticReport(
            checks={"network": True, "identity": True},
            messages=["All systems operational"],
        )

    async def load_agent_config(self, name: str) -> AgentConfigInfo:
        self.call_log.append("load_agent_config")
        return AgentConfigInfo(name=name)

    async def load_template_config(self, name: str) -> TemplateInfo:
        self.call_log.append("load_template_config")
        return TemplateInfo(name=name)
