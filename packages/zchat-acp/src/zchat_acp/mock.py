"""MockAcpBackend — in-memory AcpBackend for testing."""

from __future__ import annotations

from typing import AsyncIterator
from ulid import ULID

from zchat_protocol import Identity, OperationType, ZChatEvent

from zchat_cli.types import (
    SessionInfo,
    SessionStatus,
    SpawnPreview,
    ZChatOperation,
)


class MockAcpBackend:
    """In-memory implementation of AcpBackend for testing."""

    def __init__(self) -> None:
        self._sessions: dict[str, SessionInfo] = {}
        self.call_log: list[str] = []

    async def prepare_spawn(
        self, agent_name: str, template: str | None = None
    ) -> SpawnPreview:
        self.call_log.append("prepare_spawn")
        return SpawnPreview(
            agent_name=agent_name,
            template=template or "default",
            model="mock-model",
            estimated_cost=0.0,
        )

    async def confirm_spawn(self, preview: SpawnPreview) -> Identity:
        self.call_log.append("confirm_spawn")
        agent_identity = Identity(
            user="mock-user", label=preview.agent_name, network="mocknet"
        )
        session_id = str(ULID())
        self._sessions[session_id] = SessionInfo(
            session_id=session_id,
            agent=agent_identity,
            status=SessionStatus.RUNNING,
        )
        return agent_identity

    async def cancel_spawn(self, preview: SpawnPreview) -> None:
        self.call_log.append("cancel_spawn")

    async def sessions(self) -> list[SessionInfo]:
        self.call_log.append("sessions")
        return list(self._sessions.values())

    async def get_session(self, session_id: str) -> SessionInfo | None:
        self.call_log.append("get_session")
        return self._sessions.get(session_id)

    async def kill_session(self, session_id: str) -> None:
        self.call_log.append("kill_session")
        if session_id in self._sessions:
            self._sessions[session_id] = SessionInfo(
                session_id=session_id,
                agent=self._sessions[session_id].agent,
                status=SessionStatus.STOPPED,
            )

    async def inject_message(self, session_id: str, content: str) -> None:
        self.call_log.append("inject_message")

    async def capture_output(
        self, session_id: str
    ) -> AsyncIterator[ZChatOperation]:
        self.call_log.append("capture_output")
        event = ZChatEvent.create(
            room="#general",
            type=OperationType.MSG,
            from_="mock-user:agent@mocknet",
            content="mock output",
            content_type="text/plain",
        )
        yield ZChatOperation(event=event, source="agent")

    async def attach(self, session_id: str) -> None:
        self.call_log.append("attach")
        if session_id in self._sessions:
            session = self._sessions[session_id]
            self._sessions[session_id] = SessionInfo(
                session_id=session.session_id,
                agent=session.agent,
                status=session.status,
                attached=True,
            )

    async def detach(self, session_id: str) -> None:
        self.call_log.append("detach")
        if session_id in self._sessions:
            session = self._sessions[session_id]
            self._sessions[session_id] = SessionInfo(
                session_id=session.session_id,
                agent=session.agent,
                status=session.status,
                attached=False,
            )

    async def get_status(self, session_id: str) -> SessionInfo:
        self.call_log.append("get_status")
        if session_id in self._sessions:
            return self._sessions[session_id]
        return SessionInfo(
            session_id=session_id,
            agent=Identity(user="unknown", network="mocknet"),
            status=SessionStatus.STOPPED,
        )
