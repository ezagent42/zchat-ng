"""T-L.11, T-L.12, T-L.13: Watch tests."""

import asyncio

import pytest

from zchat_protocol import OperationType, ZChatEvent

from zchat_cli.api import ZChatCLI
from zchat_com.mock import MockComBackend
from zchat_acp.mock import MockAcpBackend


@pytest.fixture
def cli(mock_com: MockComBackend, mock_acp: MockAcpBackend) -> ZChatCLI:
    return ZChatCLI(com=mock_com, acp=mock_acp)


def _make_event(
    op: OperationType, room: str = "#general", content: str = "test"
) -> ZChatEvent:
    return ZChatEvent.create(
        room=room,
        type=op,
        from_="mock-user@mocknet",
        content=content,
        content_type="text/plain",
    )


class TestWatchRealtime:
    """T-L.11: Watch realtime events from a room."""

    async def test_watch_receives_published_event(
        self, cli: ZChatCLI, mock_com: MockComBackend
    ) -> None:
        """Watch yields events published to the room."""
        received: list[ZChatEvent] = []

        async def watcher() -> None:
            async for event in cli.watch(room="#general"):
                received.append(event)
                break  # stop after first event

        task = asyncio.create_task(watcher())
        # Give the watcher time to subscribe
        await asyncio.sleep(0.05)

        event = _make_event(OperationType.MSG)
        await mock_com.publish(event)

        await asyncio.wait_for(task, timeout=2.0)
        assert len(received) == 1
        assert received[0].type == OperationType.MSG


class TestWatchNoFollow:
    """T-L.12: Watch with no_follow returns historical events then stops."""

    async def test_watch_no_follow(
        self, cli: ZChatCLI, mock_com: MockComBackend
    ) -> None:
        """no_follow mode returns existing events and terminates."""
        # Pre-populate some events
        for i in range(3):
            event = _make_event(OperationType.MSG, content=f"msg-{i}")
            mock_com._events["#general"].append(event)

        events: list[ZChatEvent] = []
        async for event in cli.watch(room="#general", no_follow=True):
            events.append(event)

        assert len(events) == 3


class TestWatchVerbose:
    """T-L.13: Watch filtering: default, verbose, thinking, show_all."""

    async def test_default_filter_excludes_tool_use(
        self, cli: ZChatCLI, mock_com: MockComBackend
    ) -> None:
        """Default filter excludes TOOL_USE events."""
        mock_com._events["#general"] = [
            _make_event(OperationType.MSG, content="visible"),
            _make_event(OperationType.TOOL_USE, content="hidden"),
            _make_event(OperationType.ASK, content="visible-ask"),
        ]

        events: list[ZChatEvent] = []
        async for event in cli.watch(room="#general", no_follow=True):
            events.append(event)

        types = [e.type for e in events]
        assert OperationType.MSG in types
        assert OperationType.ASK in types
        assert OperationType.TOOL_USE not in types

    async def test_verbose_includes_tool_use(
        self, cli: ZChatCLI, mock_com: MockComBackend
    ) -> None:
        """Verbose mode includes TOOL_USE and TOOL_RESULT."""
        mock_com._events["#general"] = [
            _make_event(OperationType.MSG, content="msg"),
            _make_event(OperationType.TOOL_USE, content="tool"),
            _make_event(OperationType.TOOL_RESULT, content="result"),
        ]

        events: list[ZChatEvent] = []
        async for event in cli.watch(
            room="#general", no_follow=True, verbose=True
        ):
            events.append(event)

        types = [e.type for e in events]
        assert OperationType.TOOL_USE in types
        assert OperationType.TOOL_RESULT in types

    async def test_thinking_includes_thinking(
        self, cli: ZChatCLI, mock_com: MockComBackend
    ) -> None:
        """Thinking mode includes THINKING events."""
        mock_com._events["#general"] = [
            _make_event(OperationType.MSG, content="msg"),
            _make_event(OperationType.THINKING, content="thought"),
        ]

        events: list[ZChatEvent] = []
        async for event in cli.watch(
            room="#general", no_follow=True, thinking=True
        ):
            events.append(event)

        types = [e.type for e in events]
        assert OperationType.THINKING in types

    async def test_show_all_no_filter(
        self, cli: ZChatCLI, mock_com: MockComBackend
    ) -> None:
        """show_all disables all filtering."""
        mock_com._events["#general"] = [
            _make_event(OperationType.MSG, content="msg"),
            _make_event(OperationType.TOOL_USE, content="tool"),
            _make_event(OperationType.THINKING, content="thought"),
            _make_event(OperationType.TYPING, content="typing"),
            _make_event(OperationType.ANNOTATE, content="annotate"),
        ]

        events: list[ZChatEvent] = []
        async for event in cli.watch(
            room="#general", no_follow=True, show_all=True
        ):
            events.append(event)

        assert len(events) == 5
