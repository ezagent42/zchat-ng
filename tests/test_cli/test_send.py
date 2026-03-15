"""T-L.5 and T-L.6: Send message tests."""

import pytest

from zchat_protocol import Identity, OperationType

from zchat_cli.api import ZChatCLI
from zchat_com.mock import MockComBackend
from zchat_acp.mock import MockAcpBackend


@pytest.fixture
def cli(mock_com: MockComBackend, mock_acp: MockAcpBackend) -> ZChatCLI:
    return ZChatCLI(com=mock_com, acp=mock_acp)


class TestSendToAgent:
    """T-L.5: Send a message to a specific agent."""

    async def test_send_to_agent(
        self, cli: ZChatCLI, mock_com: MockComBackend
    ) -> None:
        """Sending to an agent publishes a MSG event to #general."""
        target = Identity(user="mock-user", label="ppt-maker", network="mocknet")
        await cli.send(target=str(target), content="Hello agent")

        assert "publish" in mock_com.call_log
        events = mock_com._events["#general"]
        assert len(events) == 1
        assert events[0].type == OperationType.MSG
        assert events[0].content == "Hello agent"

    async def test_send_to_agent_from(
        self, cli: ZChatCLI, mock_com: MockComBackend
    ) -> None:
        """Send event from_ field contains the CLI identity."""
        target = Identity(user="mock-user", label="ppt-maker", network="mocknet")
        await cli.send(target=str(target), content="Hello")

        events = mock_com._events["#general"]
        assert events[0].from_ == "mock-user@mocknet"


class TestSendToRoom:
    """T-L.6: Send a message to a room."""

    async def test_send_to_room(
        self, cli: ZChatCLI, mock_com: MockComBackend
    ) -> None:
        """Sending to a room publishes a MSG event to that room."""
        await cli.send(target="#general", content="Hello room")

        assert "publish" in mock_com.call_log
        events = mock_com._events["#general"]
        assert len(events) == 1
        assert events[0].type == OperationType.MSG
        assert events[0].content == "Hello room"
        assert events[0].room == "#general"

    async def test_send_to_room_content_type(
        self, cli: ZChatCLI, mock_com: MockComBackend
    ) -> None:
        """Send events default to text/plain content type."""
        await cli.send(target="#general", content="Hello")

        events = mock_com._events["#general"]
        assert events[0].content_type == "text/plain"
