"""Multi-user E2E tests — cross-process communication via shared ZCHAT_HOME."""
import os
import subprocess
import sys
import tempfile

import pytest


@pytest.fixture
def shared_home():
    with tempfile.TemporaryDirectory(prefix="zchat-multi-") as d:
        yield d


def run_as(identity, *args, home):
    env = {
        **os.environ,
        "ZCHAT_IDENTITY": identity,
        "ZCHAT_HOME": home,
        "ZCHAT_RUNTIME": os.path.join(home, "runtime"),
    }
    return subprocess.run(
        [sys.executable, "-m", "zchat_cli", *args],
        capture_output=True, text=True, timeout=15, env=env,
    )


class TestMultiUser:
    def test_alice_sends_bob_sees(self, shared_home):
        r = run_as("alice@testnet", "send", "#general", "hello from alice", home=shared_home)
        assert r.returncode == 0
        r = run_as("bob@testnet", "watch", "#general", "--no-follow", home=shared_home)
        assert r.returncode == 0
        assert "hello from alice" in r.stdout

    def test_two_users_in_room(self, shared_home):
        r = run_as("alice@testnet", "room", "create", "#workshop", home=shared_home)
        assert r.returncode == 0
        r = run_as("alice@testnet", "send", "#workshop", "design discussion", home=shared_home)
        assert r.returncode == 0
        r = run_as("bob@testnet", "watch", "#workshop", "--no-follow", home=shared_home)
        assert r.returncode == 0
        assert "design discussion" in r.stdout

    def test_session_operations(self, shared_home):
        r = run_as("alice@testnet", "sessions", home=shared_home)
        assert r.returncode == 0
