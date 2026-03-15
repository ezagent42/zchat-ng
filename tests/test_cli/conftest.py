"""Shared fixtures for CLI tests."""

import pytest

from zchat_com.mock import MockComBackend
from zchat_acp.mock import MockAcpBackend


@pytest.fixture
def mock_com() -> MockComBackend:
    """Create a fresh MockComBackend instance."""
    return MockComBackend()


@pytest.fixture
def mock_acp() -> MockAcpBackend:
    """Create a fresh MockAcpBackend instance."""
    return MockAcpBackend()
