"""T-L.1 and T-L.2: Backend protocol conformance tests."""

import inspect

import pytest

from zchat_cli.backends import AcpBackend, ComBackend
from zchat_com.mock import MockComBackend
from zchat_acp.mock import MockAcpBackend


class TestComBackendProtocol:
    """T-L.1: MockComBackend satisfies ComBackend protocol."""

    def test_isinstance(self, mock_com: MockComBackend) -> None:
        """MockComBackend is a ComBackend."""
        assert isinstance(mock_com, ComBackend)

    def test_get_identity_params(self, mock_com: MockComBackend) -> None:
        sig = inspect.signature(mock_com.get_identity)
        assert list(sig.parameters.keys()) == []

    def test_get_network_params(self, mock_com: MockComBackend) -> None:
        sig = inspect.signature(mock_com.get_network)
        assert list(sig.parameters.keys()) == []

    def test_get_peers_params(self, mock_com: MockComBackend) -> None:
        sig = inspect.signature(mock_com.get_peers)
        assert list(sig.parameters.keys()) == []

    def test_setup_identity_params(self, mock_com: MockComBackend) -> None:
        sig = inspect.signature(mock_com.setup_identity)
        assert list(sig.parameters.keys()) == ["user", "network"]

    def test_room_create_params(self, mock_com: MockComBackend) -> None:
        sig = inspect.signature(mock_com.room_create)
        assert "name" in sig.parameters
        assert "topic" in sig.parameters

    def test_publish_params(self, mock_com: MockComBackend) -> None:
        sig = inspect.signature(mock_com.publish)
        assert list(sig.parameters.keys()) == ["event"]

    def test_subscribe_params(self, mock_com: MockComBackend) -> None:
        sig = inspect.signature(mock_com.subscribe)
        assert list(sig.parameters.keys()) == ["room"]

    def test_query_events_params(self, mock_com: MockComBackend) -> None:
        sig = inspect.signature(mock_com.query_events)
        assert "room" in sig.parameters
        assert "last" in sig.parameters

    def test_doctor_params(self, mock_com: MockComBackend) -> None:
        sig = inspect.signature(mock_com.doctor)
        assert list(sig.parameters.keys()) == []


class TestAcpBackendProtocol:
    """T-L.2: MockAcpBackend satisfies AcpBackend protocol."""

    def test_isinstance(self, mock_acp: MockAcpBackend) -> None:
        """MockAcpBackend is an AcpBackend."""
        assert isinstance(mock_acp, AcpBackend)

    def test_prepare_spawn_params(self, mock_acp: MockAcpBackend) -> None:
        sig = inspect.signature(mock_acp.prepare_spawn)
        assert "agent_name" in sig.parameters
        assert "template" in sig.parameters

    def test_confirm_spawn_params(self, mock_acp: MockAcpBackend) -> None:
        sig = inspect.signature(mock_acp.confirm_spawn)
        assert list(sig.parameters.keys()) == ["preview"]

    def test_cancel_spawn_params(self, mock_acp: MockAcpBackend) -> None:
        sig = inspect.signature(mock_acp.cancel_spawn)
        assert list(sig.parameters.keys()) == ["preview"]

    def test_sessions_params(self, mock_acp: MockAcpBackend) -> None:
        sig = inspect.signature(mock_acp.sessions)
        assert list(sig.parameters.keys()) == []

    def test_inject_message_params(self, mock_acp: MockAcpBackend) -> None:
        sig = inspect.signature(mock_acp.inject_message)
        assert "session_id" in sig.parameters
        assert "content" in sig.parameters

    def test_capture_output_params(self, mock_acp: MockAcpBackend) -> None:
        sig = inspect.signature(mock_acp.capture_output)
        assert list(sig.parameters.keys()) == ["session_id"]

    def test_attach_params(self, mock_acp: MockAcpBackend) -> None:
        sig = inspect.signature(mock_acp.attach)
        assert list(sig.parameters.keys()) == ["session_id"]

    def test_detach_params(self, mock_acp: MockAcpBackend) -> None:
        sig = inspect.signature(mock_acp.detach)
        assert list(sig.parameters.keys()) == ["session_id"]

    def test_get_status_params(self, mock_acp: MockAcpBackend) -> None:
        sig = inspect.signature(mock_acp.get_status)
        assert list(sig.parameters.keys()) == ["session_id"]
