"""T-L.7 and T-L.8: Room listing and membership tests."""

import pytest

from zchat_protocol import Identity

from zchat_cli.api import ZChatCLI
from zchat_com.mock import MockComBackend
from zchat_acp.mock import MockAcpBackend


@pytest.fixture
def cli(mock_com: MockComBackend, mock_acp: MockAcpBackend) -> ZChatCLI:
    return ZChatCLI(com=mock_com, acp=mock_acp)


class TestRooms:
    """T-L.7: List rooms."""

    async def test_rooms(
        self, cli: ZChatCLI, mock_com: MockComBackend
    ) -> None:
        """Listing rooms returns the mock rooms including #general."""
        rooms = await cli.rooms()
        assert len(rooms) >= 1
        names = [r.name for r in rooms]
        assert "#general" in names
        assert "rooms" in mock_com.call_log


class TestMembers:
    """T-L.8: List members of a room."""

    async def test_members(
        self, cli: ZChatCLI, mock_com: MockComBackend
    ) -> None:
        """Listing members of #general returns the mock identity."""
        members = await cli.members("#general")
        assert len(members) >= 1
        assert any(m.user == "mock-user" for m in members)
        assert "members" in mock_com.call_log
