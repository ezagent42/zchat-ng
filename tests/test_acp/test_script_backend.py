"""Tests for ScriptAcpBackend — daemon agent scripts with JSONL protocol."""

from __future__ import annotations

import asyncio
import os
import signal
from pathlib import Path

import pytest

from zchat_protocol import Identity, OperationType, ZChatEvent
from zchat_protocol.config import ZChatConfig
from zchat_cli.types import (
    SessionInfo,
    SessionStatus,
    SpawnPreview,
    ZChatOperation,
)
from zchat_com.file import FileComBackend
from zchat_acp.script import ScriptAcpBackend

ECHO_AGENT = str(Path(__file__).parent.parent.parent / "scripts" / "echo-agent.sh")


@pytest.fixture
def backends(tmp_path, monkeypatch):
    """Create FileComBackend + ScriptAcpBackend with isolated tmp dirs."""
    home = tmp_path / "zchat_home"
    runtime = tmp_path / "zchat_runtime"
    monkeypatch.setenv("ZCHAT_HOME", str(home))
    monkeypatch.setenv("ZCHAT_RUNTIME", str(runtime))

    config = ZChatConfig(home=home, project=None, runtime=runtime)
    identity = Identity.parse("alice@testnet")
    com = FileComBackend(config=config, identity=identity)
    acp = ScriptAcpBackend(config=config, identity=identity, com=com)
    return {"config": config, "identity": identity, "com": com, "acp": acp}


async def _spawn_echo(acp: ScriptAcpBackend, agent_name: str = "echo") -> tuple[str, Identity]:
    """Helper: prepare + confirm spawn of echo-agent, return (session_id, identity)."""
    preview = SpawnPreview(
        agent_name=agent_name,
        template="",
        model=ECHO_AGENT,
        estimated_cost=0.0,
    )
    agent_id = await acp.confirm_spawn(preview)
    # Find session_id from sessions list
    sessions = await acp.sessions()
    for s in sessions:
        if str(s.agent) == str(agent_id):
            return s.session_id, agent_id
    raise RuntimeError("Spawned session not found")


# ── 1. test_spawn_starts_process ──


async def test_spawn_starts_process(backends):
    acp = backends["acp"]
    sid, _ = await _spawn_echo(acp)
    try:
        sessions = await acp.sessions()
        assert len(sessions) == 1
        assert sessions[0].status == SessionStatus.RUNNING
    finally:
        await acp.kill_session(sid)


# ── 2. test_spawn_reads_init_message ──


async def test_spawn_reads_init_message(backends):
    acp = backends["acp"]
    sid, _ = await _spawn_echo(acp)
    try:
        # session_id is "echo-<timestamp>-<pid>"
        assert sid.startswith("echo-")
        parts = sid.split("-")
        assert len(parts) >= 3  # echo, timestamp, pid
    finally:
        await acp.kill_session(sid)


# ── 3. test_spawn_returns_agent_identity ──


async def test_spawn_returns_agent_identity(backends):
    acp = backends["acp"]
    sid, agent_id = await _spawn_echo(acp, agent_name="echo")
    try:
        assert agent_id.label == "echo"
        assert agent_id.user == "alice"
        assert agent_id.network == "testnet"
    finally:
        await acp.kill_session(sid)


# ── 4. test_kill_terminates_process ──


async def test_kill_terminates_process(backends):
    acp = backends["acp"]
    sid, _ = await _spawn_echo(acp)
    await acp.kill_session(sid)
    sessions = await acp.sessions()
    # Session file removed or shows STOPPED
    running = [s for s in sessions if s.status == SessionStatus.RUNNING]
    assert len(running) == 0


# ── 5. test_get_session_returns_none_for_missing ──


async def test_get_session_returns_none_for_missing(backends):
    acp = backends["acp"]
    result = await acp.get_session("nonexistent-session-id")
    assert result is None


# ── 6. test_inject_and_capture ──


async def test_inject_and_capture(backends):
    acp = backends["acp"]
    sid, _ = await _spawn_echo(acp)
    try:
        # Pause the watcher so we can capture manually
        await acp.attach(sid)

        await acp.inject_message(sid, "hello world")

        ops: list[ZChatOperation] = []
        async for op in acp.capture_output(sid):
            ops.append(op)
            if len(ops) >= 2:
                break

        # echo-agent returns an assistant + result line
        assert len(ops) >= 1
        # The first op should contain the echoed content
        assert "hello world" in ops[0].event.content
    finally:
        await acp.kill_session(sid)


# ── 7. test_event_watcher_detects_mention ──


async def test_event_watcher_detects_mention(backends):
    acp = backends["acp"]
    com: FileComBackend = backends["com"]

    sid, agent_id = await _spawn_echo(acp, agent_name="echo")
    try:
        # Ensure the room exists
        await com.rooms()

        # Publish an @mention event to #general
        mention_event = ZChatEvent.create(
            room="#general",
            type=OperationType.MSG,
            from_="alice@testnet",
            content="hey @echo what's up?",
            content_type="text/plain",
        )
        await com.publish(mention_event)

        # Wait for the watcher to process and publish a reply
        await asyncio.sleep(2)

        events = await com.query_events("#general")
        agent_replies = [
            e for e in events
            if e.from_ == str(agent_id) and e.type == OperationType.MSG
        ]
        assert len(agent_replies) >= 1
    finally:
        await acp.kill_session(sid)


# ── 8. test_sessions_lists_active ──


async def test_sessions_lists_active(backends):
    acp = backends["acp"]
    sid1, _ = await _spawn_echo(acp, agent_name="echo1")
    sid2, _ = await _spawn_echo(acp, agent_name="echo2")
    try:
        sessions = await acp.sessions()
        running = [s for s in sessions if s.status == SessionStatus.RUNNING]
        assert len(running) == 2
    finally:
        await acp.kill_session(sid1)
        await acp.kill_session(sid2)


# ── 9. test_sessions_detects_dead ──


async def test_sessions_detects_dead(backends):
    acp = backends["acp"]
    sid, _ = await _spawn_echo(acp)
    try:
        # Get the PID and kill it externally
        proc = acp._processes[sid]
        pid = proc.pid
        os.kill(pid, signal.SIGKILL)
        # Wait for process to die
        await asyncio.to_thread(proc.wait)

        sessions = await acp.sessions()
        matched = [s for s in sessions if s.session_id == sid]
        assert len(matched) == 1
        assert matched[0].status == SessionStatus.STOPPED
    finally:
        await acp.kill_session(sid)


# ── 10. test_attach_pauses_watcher ──


async def test_attach_pauses_watcher(backends):
    acp = backends["acp"]
    com: FileComBackend = backends["com"]

    sid, agent_id = await _spawn_echo(acp, agent_name="echo")
    try:
        await com.rooms()

        # Attach pauses the watcher
        await acp.attach(sid)

        # Publish @mention — should NOT get auto-reply
        mention_event = ZChatEvent.create(
            room="#general",
            type=OperationType.MSG,
            from_="alice@testnet",
            content="hey @echo are you there?",
            content_type="text/plain",
        )
        await com.publish(mention_event)

        await asyncio.sleep(1.5)

        events = await com.query_events("#general")
        agent_replies = [
            e for e in events
            if e.from_ == str(agent_id) and e.type == OperationType.MSG
        ]
        assert len(agent_replies) == 0
    finally:
        await acp.kill_session(sid)


# ── 11. test_detach_resumes_watcher ──


async def test_detach_resumes_watcher(backends):
    acp = backends["acp"]
    com: FileComBackend = backends["com"]

    sid, agent_id = await _spawn_echo(acp, agent_name="echo")
    try:
        await com.rooms()

        # Attach then detach to resume
        await acp.attach(sid)
        await acp.detach(sid)

        # Publish @mention — should get auto-reply
        mention_event = ZChatEvent.create(
            room="#general",
            type=OperationType.MSG,
            from_="alice@testnet",
            content="hey @echo say something",
            content_type="text/plain",
        )
        await com.publish(mention_event)

        await asyncio.sleep(2)

        events = await com.query_events("#general")
        agent_replies = [
            e for e in events
            if e.from_ == str(agent_id) and e.type == OperationType.MSG
        ]
        assert len(agent_replies) >= 1
    finally:
        await acp.kill_session(sid)
