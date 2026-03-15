"""T-L.14 and T-L.15: Ask and answer tests."""

import asyncio

import pytest

from zchat_protocol import OperationType, ZChatEvent

from zchat_cli.api import ZChatCLI
from zchat_com.mock import MockComBackend
from zchat_acp.mock import MockAcpBackend


@pytest.fixture
def cli(mock_com: MockComBackend, mock_acp: MockAcpBackend) -> ZChatCLI:
    return ZChatCLI(com=mock_com, acp=mock_acp)


class TestAsk:
    """T-L.14: Ask a question and receive a delayed answer."""

    async def test_ask_with_delayed_answer(
        self, cli: ZChatCLI, mock_com: MockComBackend
    ) -> None:
        """Ask publishes an ASK event and waits for an ANSWER event."""

        async def delayed_answer() -> None:
            """Wait, then publish an answer referencing the ask event."""
            await asyncio.sleep(0.1)
            # Find the ask event
            events = mock_com._events.get("#general", [])
            ask_event = None
            for e in events:
                if e.type == OperationType.ASK:
                    ask_event = e
                    break
            assert ask_event is not None
            answer = ZChatEvent.create(
                room="#general",
                type=OperationType.ANSWER,
                from_="mock-user:ppt-maker@mocknet",
                content="42",
                content_type="text/plain",
                ref=ask_event.id,
            )
            await mock_com.publish(answer)

        task = asyncio.create_task(delayed_answer())
        result = await asyncio.wait_for(
            cli.ask(target="#general", question="What is the answer?", timeout=5.0),
            timeout=5.0,
        )
        await task

        assert result.type == OperationType.ANSWER
        assert result.content == "42"


class TestAnswer:
    """T-L.15: Answer a pending ask event."""

    async def test_answer_pending(
        self, cli: ZChatCLI, mock_com: MockComBackend
    ) -> None:
        """Answer publishes an ANSWER event referencing the ask."""
        # Create an ask event first
        ask_event = ZChatEvent.create(
            room="#general",
            type=OperationType.ASK,
            from_="other-user@mocknet",
            content="What is your name?",
            content_type="text/plain",
        )
        mock_com._events["#general"].append(ask_event)

        await cli.answer(ask_id=ask_event.id, text="I am ZChat")

        assert "publish" in mock_com.call_log
        events = mock_com._events["#general"]
        answer_event = events[-1]
        assert answer_event.type == OperationType.ANSWER
        assert answer_event.content == "I am ZChat"
        assert answer_event.ref == ask_event.id
