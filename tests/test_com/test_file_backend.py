"""Tests for FileComBackend — file-based ComBackend implementation."""
from __future__ import annotations

import asyncio
import json

import pytest

from zchat_protocol import Identity, OperationType, ZChatEvent, SpawnConfig
from zchat_protocol.config import ZChatConfig
from zchat_cli.types import (
    AgentConfigInfo,
    DiagnosticReport,
    NetworkInfo,
    Room,
    TemplateInfo,
)
from zchat_com.file import FileComBackend


@pytest.fixture
def zchat_env(tmp_path, monkeypatch):
    home = tmp_path / "zchat_home"
    runtime = tmp_path / "zchat_runtime"
    monkeypatch.setenv("ZCHAT_HOME", str(home))
    monkeypatch.setenv("ZCHAT_RUNTIME", str(runtime))
    monkeypatch.setenv("ZCHAT_IDENTITY", "alice@testnet")
    return {"home": home, "runtime": runtime}


def _make_backend(zchat_env) -> FileComBackend:
    config = ZChatConfig.resolve()
    identity = Identity.parse("alice@testnet")
    return FileComBackend(config=config, identity=identity)


def _make_event(room: str, from_: str, content: str) -> ZChatEvent:
    return ZChatEvent.create(
        room=room,
        type=OperationType.MSG,
        from_=from_,
        content=content,
        content_type="text/plain",
    )


# ── 1. Identity ──


async def test_get_identity(zchat_env):
    backend = _make_backend(zchat_env)
    identity = await backend.get_identity()
    assert identity == Identity.parse("alice@testnet")


# ── 2. Network ──


async def test_get_network(zchat_env):
    backend = _make_backend(zchat_env)
    info = await backend.get_network()
    assert isinstance(info, NetworkInfo)
    assert info.name == "local"
    assert info.online is True


# ── 3. Peers ──


async def test_get_peers_from_rooms(zchat_env):
    backend = _make_backend(zchat_env)
    # Bootstrap creates #general with alice
    await backend.rooms()  # trigger bootstrap
    bob = Identity.parse("bob@testnet")
    await backend.room_invite("#general", bob)
    peers = await backend.get_peers()
    peer_strs = {str(p) for p in peers}
    assert "alice@testnet" in peer_strs
    assert "bob@testnet" in peer_strs


# ── 4. Setup identity ──


async def test_setup_identity_returns_current(zchat_env):
    backend = _make_backend(zchat_env)
    result = await backend.setup_identity("alice", "testnet")
    assert result == Identity.parse("alice@testnet")


# ── 5. Bootstrap ──


async def test_bootstrap_creates_general(zchat_env):
    backend = _make_backend(zchat_env)
    room_list = await backend.rooms()
    names = [r.name for r in room_list]
    assert "#general" in names


# ── 6. Room create ──


async def test_room_create(zchat_env):
    backend = _make_backend(zchat_env)
    room = await backend.room_create("#dev", topic="Development")
    assert room.name == "#dev"
    assert room.topic == "Development"
    room_list = await backend.rooms()
    names = [r.name for r in room_list]
    assert "#dev" in names


# ── 7. Room invite ──


async def test_room_invite_and_members(zchat_env):
    backend = _make_backend(zchat_env)
    await backend.rooms()  # bootstrap
    bob = Identity.parse("bob@testnet")
    await backend.room_invite("#general", bob)
    mems = await backend.members("#general")
    mem_strs = [str(m) for m in mems]
    assert "bob@testnet" in mem_strs
    # Check that a join event was published
    events = await backend.query_events("#general")
    join_events = [e for e in events if e.type == OperationType.JOIN]
    assert len(join_events) >= 1


# ── 8. Room leave ──


async def test_room_leave(zchat_env):
    backend = _make_backend(zchat_env)
    await backend.rooms()  # bootstrap
    await backend.room_leave("#general")
    mems = await backend.members("#general")
    mem_strs = [str(m) for m in mems]
    assert "alice@testnet" not in mem_strs


# ── 9. Rooms list ──


async def test_rooms_lists_from_file(zchat_env):
    backend = _make_backend(zchat_env)
    await backend.room_create("#alpha")
    await backend.room_create("#beta")
    room_list = await backend.rooms()
    names = {r.name for r in room_list}
    assert "#general" in names
    assert "#alpha" in names
    assert "#beta" in names


# ── 10. Members ──


async def test_members_reads_from_file(zchat_env):
    backend = _make_backend(zchat_env)
    await backend.rooms()  # bootstrap
    mems = await backend.members("#general")
    assert len(mems) >= 1
    assert any(str(m) == "alice@testnet" for m in mems)


# ── 11. Publish ──


async def test_publish_appends_to_jsonl(zchat_env):
    backend = _make_backend(zchat_env)
    await backend.rooms()  # bootstrap
    event = _make_event("#general", "alice@testnet", "hello")
    await backend.publish(event)
    config = ZChatConfig.resolve()
    events_file = config.room_events_file("#general")
    assert events_file.exists()
    lines = events_file.read_text().strip().split("\n")
    assert len(lines) >= 1
    parsed = json.loads(lines[-1])
    assert parsed["content"] == "hello"


# ── 12. Query events last N ──


async def test_query_events_last_n(zchat_env):
    backend = _make_backend(zchat_env)
    await backend.rooms()  # bootstrap
    for i in range(10):
        event = _make_event("#general", "alice@testnet", f"msg-{i}")
        await backend.publish(event)
    results = await backend.query_events("#general", last=3)
    assert len(results) == 3
    assert results[-1].content == "msg-9"


# ── 13. Query events no last ──


async def test_query_events_no_last_returns_all(zchat_env):
    backend = _make_backend(zchat_env)
    await backend.rooms()  # bootstrap
    for i in range(5):
        event = _make_event("#general", "alice@testnet", f"msg-{i}")
        await backend.publish(event)
    results = await backend.query_events("#general")
    assert len(results) == 5


# ── 14. Get event by ID ──


async def test_get_event_by_id(zchat_env):
    backend = _make_backend(zchat_env)
    await backend.rooms()  # bootstrap
    event = _make_event("#general", "alice@testnet", "findme")
    await backend.publish(event)
    found = await backend.get_event(event.id)
    assert found is not None
    assert found.id == event.id
    assert found.content == "findme"


# ── 15. Get event not found ──


async def test_get_event_not_found(zchat_env):
    backend = _make_backend(zchat_env)
    result = await backend.get_event("nonexistent-id")
    assert result is None


# ── 16. Handled markers ──


async def test_is_handled_mark_handled(zchat_env):
    backend = _make_backend(zchat_env)
    assert await backend.is_handled("evt-1") is False
    await backend.mark_handled("evt-1")
    assert await backend.is_handled("evt-1") is True


# ── 17. Doctor ──


async def test_doctor_all_ok(zchat_env):
    backend = _make_backend(zchat_env)
    report = await backend.doctor()
    assert isinstance(report, DiagnosticReport)
    assert report.ok is True
    assert report.checks.get("identity_set") is True


# ── 18. Load agent config ──


async def test_load_agent_config(zchat_env):
    config = ZChatConfig.resolve()
    # Create a project dir with agents
    project = zchat_env["home"].parent / "project" / ".zchat"
    agents_dir = project / "agents"
    agents_dir.mkdir(parents=True)
    toml_content = 'name = "test-agent"\nmodel = "gpt-4"\n'
    (agents_dir / "test-agent.toml").write_text(toml_content)
    config_with_project = ZChatConfig(
        home=config.home,
        project=project,
        runtime=config.runtime,
    )
    config_with_project.ensure_home()
    config_with_project.ensure_store()
    identity = Identity.parse("alice@testnet")
    backend = FileComBackend(config=config_with_project, identity=identity)
    info = await backend.load_agent_config("test-agent")
    assert isinstance(info, AgentConfigInfo)
    assert info.name == "test-agent"
    assert info.model == "gpt-4"


# ── 19. Load template config ──


async def test_load_template_config(zchat_env):
    config = ZChatConfig.resolve()
    project = zchat_env["home"].parent / "project" / ".zchat"
    templates_dir = project / "templates"
    templates_dir.mkdir(parents=True)
    toml_content = 'name = "my-template"\n'
    (templates_dir / "my-template.toml").write_text(toml_content)
    config_with_project = ZChatConfig(
        home=config.home,
        project=project,
        runtime=config.runtime,
    )
    config_with_project.ensure_home()
    config_with_project.ensure_store()
    identity = Identity.parse("alice@testnet")
    backend = FileComBackend(config=config_with_project, identity=identity)
    info = await backend.load_template_config("my-template")
    assert isinstance(info, TemplateInfo)
    assert info.name == "my-template"


# ── 20. Concurrent publish ──


async def test_concurrent_publish(zchat_env):
    backend = _make_backend(zchat_env)
    await backend.rooms()  # bootstrap

    async def pub(i: int):
        event = _make_event("#general", "alice@testnet", f"concurrent-{i}")
        await backend.publish(event)

    await asyncio.gather(*(pub(i) for i in range(20)))
    events = await backend.query_events("#general")
    assert len(events) == 20
    contents = {e.content for e in events}
    for i in range(20):
        assert f"concurrent-{i}" in contents


# ── 21. Subscribe yields new events ──


async def test_subscribe_yields_new_events(zchat_env):
    backend = _make_backend(zchat_env)
    await backend.rooms()  # bootstrap
    config = ZChatConfig.resolve()
    config.ensure_room_store("#general")

    received: list[ZChatEvent] = []

    async def consumer():
        async for event in backend.subscribe("#general"):
            received.append(event)
            if len(received) >= 2:
                break

    async def publisher():
        await asyncio.sleep(0.3)
        for i in range(2):
            event = _make_event("#general", "alice@testnet", f"sub-{i}")
            await backend.publish(event)

    await asyncio.wait_for(
        asyncio.gather(consumer(), publisher()),
        timeout=10,
    )
    assert len(received) == 2
    assert received[0].content == "sub-0"
    assert received[1].content == "sub-1"


# ── 22. Subscribe handles partial lines ──


async def test_subscribe_handles_partial_lines(zchat_env):
    backend = _make_backend(zchat_env)
    await backend.rooms()  # bootstrap
    config = ZChatConfig.resolve()
    config.ensure_room_store("#general")

    received: list[ZChatEvent] = []

    async def consumer():
        async for event in backend.subscribe("#general"):
            received.append(event)
            if len(received) >= 1:
                break

    async def publisher():
        await asyncio.sleep(0.3)
        # Write a partial/corrupt line followed by a valid one
        events_file = config.room_events_file("#general")
        with open(events_file, "a") as f:
            f.write("this is not valid json\n")
        await asyncio.sleep(0.1)
        event = _make_event("#general", "alice@testnet", "after-corrupt")
        await backend.publish(event)

    await asyncio.wait_for(
        asyncio.gather(consumer(), publisher()),
        timeout=10,
    )
    assert len(received) == 1
    assert received[0].content == "after-corrupt"
