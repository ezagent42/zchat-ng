"""T-L.16: Session attach and detach tests."""

import pytest

from zchat_cli.api import ZChatCLI
from zchat_com.mock import MockComBackend
from zchat_acp.mock import MockAcpBackend


@pytest.fixture
def cli(mock_com: MockComBackend, mock_acp: MockAcpBackend) -> ZChatCLI:
    return ZChatCLI(com=mock_com, acp=mock_acp)


class TestSessionAttachDetach:
    """T-L.16: Attach to and detach from an agent session."""

    async def test_attach(
        self, cli: ZChatCLI, mock_acp: MockAcpBackend
    ) -> None:
        """Attaching to a session calls acp.attach and marks session attached."""
        # Spawn an agent first to get a session
        identity = await cli.spawn("helper")
        sessions = await mock_acp.sessions()
        assert len(sessions) == 1
        session_id = sessions[0].session_id

        await cli.session_attach(session_id)
        assert "attach" in mock_acp.call_log

        session = await mock_acp.get_session(session_id)
        assert session is not None
        assert session.attached is True

    async def test_detach(
        self, cli: ZChatCLI, mock_acp: MockAcpBackend
    ) -> None:
        """Detaching from a session calls acp.detach and marks session detached."""
        identity = await cli.spawn("helper")
        sessions = await mock_acp.sessions()
        session_id = sessions[0].session_id

        await cli.session_attach(session_id)
        await cli.session_detach(session_id)
        assert "detach" in mock_acp.call_log

        session = await mock_acp.get_session(session_id)
        assert session is not None
        assert session.attached is False
