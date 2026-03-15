"""E2E smoke tests — exercise the CLI via subprocess."""

import subprocess
import sys

import pytest


def run_zchat(*args: str) -> subprocess.CompletedProcess:
    """Run ``python -m zchat_cli`` with the given arguments."""
    return subprocess.run(
        [sys.executable, "-m", "zchat_cli", *args],
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_doctor():
    result = run_zchat("doctor")
    assert result.returncode == 0
    output = result.stdout.lower()
    assert "ok" in output


def test_status():
    result = run_zchat("status")
    assert result.returncode == 0
    assert "Sessions" in result.stdout


def test_spawn():
    result = run_zchat("spawn", "ppt-maker", "--yes")
    assert result.returncode == 0
    assert "ppt-maker" in result.stdout


def test_send():
    result = run_zchat("send", "@ppt-maker", "做一个 Q3 PPT")
    assert result.returncode == 0


def test_watch_no_follow():
    result = run_zchat("watch", "#general", "--no-follow")
    assert result.returncode == 0


def test_watch_verbose():
    result = run_zchat("watch", "#general", "--verbose", "--no-follow")
    assert result.returncode == 0


def test_ext_list():
    result = run_zchat("ext", "list")
    assert result.returncode == 0
    assert "No extensions" in result.stdout


def test_rooms():
    result = run_zchat("rooms")
    assert result.returncode == 0
    assert "#general" in result.stdout


def test_preflight():
    result = run_zchat("preflight")
    # May fail if gh/claude not installed, but should still run
    output = result.stdout.lower()
    assert "python" in output


def test_sessions():
    result = run_zchat("sessions")
    assert result.returncode == 0
