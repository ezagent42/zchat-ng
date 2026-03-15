"""T-L.9 and T-L.10: Status and doctor tests."""

import pytest

from zchat_cli.api import ZChatCLI
from zchat_cli.types import NetworkStatus
from zchat_com.mock import MockComBackend
from zchat_acp.mock import MockAcpBackend


@pytest.fixture
def cli(mock_com: MockComBackend, mock_acp: MockAcpBackend) -> ZChatCLI:
    return ZChatCLI(com=mock_com, acp=mock_acp)


class TestStatus:
    """T-L.9: Network status."""

    async def test_status(self, cli: ZChatCLI) -> None:
        """Status returns a NetworkStatus value."""
        status = await cli.status()
        assert isinstance(status, NetworkStatus)
        assert status == NetworkStatus.HEALTHY


class TestDoctor:
    """T-L.10: Doctor diagnostic check."""

    async def test_doctor(
        self, cli: ZChatCLI, mock_com: MockComBackend
    ) -> None:
        """Doctor returns a DiagnosticReport with ok=True."""
        report = await cli.doctor()
        assert report.ok is True
        assert "network" in report.checks
        assert "doctor" in mock_com.call_log
