"""E2E smoke tests — all CLI commands runnable with FileComBackend."""
import os
import subprocess
import sys
import tempfile

import pytest


@pytest.fixture(scope="module")
def zchat_home():
    with tempfile.TemporaryDirectory(prefix="zchat-smoke-") as d:
        yield d


def run_zchat(*args, zchat_home, identity="smoke@testnet"):
    env = {
        **os.environ,
        "ZCHAT_IDENTITY": identity,
        "ZCHAT_HOME": zchat_home,
        "ZCHAT_RUNTIME": os.path.join(zchat_home, "runtime"),
    }
    return subprocess.run(
        [sys.executable, "-m", "zchat_cli", *args],
        capture_output=True, text=True, timeout=10, env=env,
    )


class TestPhase0Smoke:
    def test_doctor(self, zchat_home):
        r = run_zchat("doctor", zchat_home=zchat_home)
        assert r.returncode == 0

    def test_status(self, zchat_home):
        r = run_zchat("status", zchat_home=zchat_home)
        assert r.returncode == 0

    def test_rooms(self, zchat_home):
        r = run_zchat("rooms", zchat_home=zchat_home)
        assert r.returncode == 0
        assert "#general" in r.stdout

    def test_send(self, zchat_home):
        r = run_zchat("send", "#general", "hello from smoke", zchat_home=zchat_home)
        assert r.returncode == 0

    def test_watch_no_follow(self, zchat_home):
        r = run_zchat("watch", "#general", "--no-follow", zchat_home=zchat_home)
        assert r.returncode == 0

    def test_watch_verbose(self, zchat_home):
        r = run_zchat("watch", "#general", "--verbose", "--no-follow", zchat_home=zchat_home)
        assert r.returncode == 0

    def test_ext_list(self, zchat_home):
        r = run_zchat("ext", "list", zchat_home=zchat_home)
        assert r.returncode == 0

    def test_sessions(self, zchat_home):
        r = run_zchat("sessions", zchat_home=zchat_home)
        assert r.returncode == 0

    def test_preflight(self, zchat_home):
        r = run_zchat("preflight", zchat_home=zchat_home)
        assert r.returncode == 0

    def test_missing_identity_crashes(self):
        env = {k: v for k, v in os.environ.items() if k != "ZCHAT_IDENTITY"}
        env["ZCHAT_HOME"] = "/tmp/zchat-noident"
        r = subprocess.run(
            [sys.executable, "-m", "zchat_cli", "doctor"],
            capture_output=True, text=True, timeout=10, env=env,
        )
        assert r.returncode != 0
        assert "ZCHAT_IDENTITY" in r.stderr
