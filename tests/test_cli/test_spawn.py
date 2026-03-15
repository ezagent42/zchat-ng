"""T-L.3 and T-L.4: Spawn agent tests."""

import pytest

from zchat_cli.api import ZChatCLI
from zchat_com.mock import MockComBackend
from zchat_acp.mock import MockAcpBackend


@pytest.fixture
def cli(mock_com: MockComBackend, mock_acp: MockAcpBackend) -> ZChatCLI:
    return ZChatCLI(com=mock_com, acp=mock_acp)


class TestSpawn:
    """T-L.3: Spawn a named agent."""

    async def test_spawn_agent(self, cli: ZChatCLI) -> None:
        """Spawning an agent returns an Identity with the agent label."""
        identity = await cli.spawn("ppt-maker")
        assert identity.label == "ppt-maker"
        assert identity.user == "mock-user"
        assert identity.network == "mocknet"

    async def test_spawn_logs_calls(
        self, cli: ZChatCLI, mock_acp: MockAcpBackend
    ) -> None:
        """Spawn calls prepare_spawn then confirm_spawn on acp backend."""
        await cli.spawn("ppt-maker")
        assert "prepare_spawn" in mock_acp.call_log
        assert "confirm_spawn" in mock_acp.call_log


class TestSpawnAdhoc:
    """T-L.4: Spawn an ad-hoc agent from a template."""

    async def test_spawn_adhoc(self, cli: ZChatCLI) -> None:
        """Spawning ad-hoc with template returns correct Identity."""
        identity = await cli.spawn_adhoc(template="researcher", name="my-researcher")
        assert identity.label == "my-researcher"
        assert identity.network == "mocknet"

    async def test_spawn_adhoc_logs(
        self, cli: ZChatCLI, mock_acp: MockAcpBackend
    ) -> None:
        """Ad-hoc spawn calls prepare_spawn with template and confirm_spawn."""
        await cli.spawn_adhoc(template="researcher", name="my-researcher")
        assert "prepare_spawn" in mock_acp.call_log
        assert "confirm_spawn" in mock_acp.call_log
