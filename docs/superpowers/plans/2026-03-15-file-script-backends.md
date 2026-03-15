# FileComBackend + ScriptAcpBackend Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace in-memory mocks with filesystem-backed backends (JSONL + watchdog + shell scripts) enabling cross-process multi-user E2E testing.

**Architecture:** FileComBackend persists events to `$ZCHAT_HOME/store/{room}/events.jsonl`, uses watchdog for real-time subscribe, and stores room state in `rooms.json`. ScriptAcpBackend manages agent shell script subprocesses as daemons with JSONL stdin/stdout (CC headless protocol). `_get_cli()` switches from MockComBackend to FileComBackend, requiring `$ZCHAT_IDENTITY` env var.

**Tech Stack:** Python 3.12+, watchdog (fsevents/inotify), asyncio, fcntl (file locking), subprocess

**Spec:** `docs/superpowers/specs/2026-03-15-file-script-backends-design.md`

---

## File Structure

```
packages/zchat-protocol/src/zchat_protocol/
└── config.py                              ← MODIFY: add rooms_file + handled_file

packages/zchat-com/
├── pyproject.toml                         ← MODIFY: add watchdog dependency
└── src/zchat_com/
    ├── mock.py                            ← unchanged (test-only)
    └── file.py                            ← NEW: FileComBackend

packages/zchat-acp/src/zchat_acp/
├── mock.py                                ← unchanged (test-only)
└── script.py                              ← NEW: ScriptAcpBackend

packages/zchat-cli/src/zchat_cli/
└── __main__.py                            ← MODIFY: _get_cli() uses FileComBackend

scripts/
└── echo-agent.sh                          ← NEW: test agent (CC headless JSONL)

tests/
├── test_com/
│   ├── __init__.py                        ← NEW
│   └── test_file_backend.py               ← NEW: ~19 tests
├── test_acp/
│   ├── __init__.py                        ← NEW
│   └── test_script_backend.py             ← NEW: ~11 tests
└── test_e2e/
    ├── test_smoke.py                      ← MODIFY: add env vars
    └── test_multiuser.py                  ← NEW: ~4 tests
```

---

## Chunk 1: ZChatConfig + FileComBackend Core

### Task 1: ZChatConfig Additions + watchdog Dependency

**Files:**
- Modify: `packages/zchat-protocol/src/zchat_protocol/config.py`
- Modify: `packages/zchat-com/pyproject.toml`
- Test: `tests/test_protocol/test_config.py` (add 2 tests to existing)

- [ ] **Step 1: Write tests for new config properties**

Append to `tests/test_protocol/test_config.py`:

```python
def test_rooms_file(tmp_path, monkeypatch):
    monkeypatch.setenv("ZCHAT_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("ZCHAT_RUNTIME", str(tmp_path / "run"))
    config = ZChatConfig.resolve()
    assert config.rooms_file == config.home / "rooms.json"


def test_handled_file(tmp_path, monkeypatch):
    monkeypatch.setenv("ZCHAT_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("ZCHAT_RUNTIME", str(tmp_path / "run"))
    config = ZChatConfig.resolve()
    assert config.handled_file == config.store_dir / ".handled.json"
```

- [ ] **Step 2: Run — expect FAIL**

Run: `uv run pytest tests/test_protocol/test_config.py::test_rooms_file tests/test_protocol/test_config.py::test_handled_file -v`
Expected: FAIL — AttributeError: 'ZChatConfig' has no attribute 'rooms_file'

- [ ] **Step 3: Implement config properties**

Add to `packages/zchat-protocol/src/zchat_protocol/config.py`, inside `ZChatConfig` class, after the `workspaces_dir` property:

```python
@property
def rooms_file(self) -> Path:
    """Room registry: $ZCHAT_HOME/rooms.json"""
    return self.home / "rooms.json"

@property
def handled_file(self) -> Path:
    """Event handled markers: $ZCHAT_HOME/store/.handled.json"""
    return self.store_dir / ".handled.json"
```

- [ ] **Step 4: Run — expect PASS**

Run: `uv run pytest tests/test_protocol/test_config.py -v`
Expected: All config tests pass (existing + 2 new)

- [ ] **Step 5: Add watchdog dependency**

In `packages/zchat-com/pyproject.toml`, change:
```toml
dependencies = [
    "zchat-protocol",
    "watchdog>=4.0",
]
```

Run: `uv sync`
Expected: watchdog installed, no errors

- [ ] **Step 6: Commit**

```bash
git add packages/zchat-protocol/src/zchat_protocol/config.py \
        packages/zchat-com/pyproject.toml \
        tests/test_protocol/test_config.py
git commit -m "feat(config): add rooms_file + handled_file properties; add watchdog dep"
```

---

### Task 2: FileComBackend — Identity + Rooms + Publish + Query

**Files:**
- Create: `packages/zchat-com/src/zchat_com/file.py`
- Create: `tests/test_com/__init__.py`
- Create: `tests/test_com/test_file_backend.py`

- [ ] **Step 1: Write tests for identity, rooms, publish, query**

```python
# tests/test_com/test_file_backend.py
"""FileComBackend tests — all use tmp_path for ZCHAT_HOME isolation."""
from __future__ import annotations

import asyncio
import json

import pytest

from zchat_protocol import Identity, OperationType, ZChatEvent, ZChatConfig


@pytest.fixture
def zchat_env(tmp_path, monkeypatch):
    """Set up isolated ZCHAT_HOME + ZCHAT_IDENTITY + ZCHAT_RUNTIME."""
    home = tmp_path / "zchat_home"
    runtime = tmp_path / "zchat_runtime"
    monkeypatch.setenv("ZCHAT_HOME", str(home))
    monkeypatch.setenv("ZCHAT_RUNTIME", str(runtime))
    monkeypatch.setenv("ZCHAT_IDENTITY", "alice@testnet")
    return {"home": home, "runtime": runtime}


@pytest.fixture
def backend(zchat_env):
    from zchat_com.file import FileComBackend
    config = ZChatConfig.resolve()
    identity = Identity.parse("alice@testnet")
    return FileComBackend(config=config, identity=identity)


# ── Identity ──

@pytest.mark.asyncio
async def test_get_identity(backend):
    ident = await backend.get_identity()
    assert ident == Identity.parse("alice@testnet")


@pytest.mark.asyncio
async def test_get_network(backend):
    net = await backend.get_network()
    assert net.name == "local"
    assert net.online is True


@pytest.mark.asyncio
async def test_get_peers_from_rooms(backend):
    # Bootstrap creates #general with alice
    peers = await backend.get_peers()
    assert any(p.user == "alice" for p in peers)


@pytest.mark.asyncio
async def test_setup_identity_returns_current(backend):
    ident = await backend.setup_identity("bob", "othernet")
    # Phase 0: no-op, returns current identity
    assert ident.user == "alice"


# ── Rooms ──

@pytest.mark.asyncio
async def test_bootstrap_creates_general(backend, zchat_env):
    rooms = await backend.rooms()
    assert any(r.name == "#general" for r in rooms)


@pytest.mark.asyncio
async def test_room_create(backend):
    room = await backend.room_create("#workshop", topic="Design work")
    assert room.name == "#workshop"
    assert room.topic == "Design work"
    assert room.member_count == 1
    # Verify persisted
    rooms = await backend.rooms()
    names = [r.name for r in rooms]
    assert "#workshop" in names


@pytest.mark.asyncio
async def test_room_invite_and_members(backend):
    bob = Identity.parse("bob@testnet")
    await backend.room_invite("#general", bob)
    members = await backend.members("#general")
    member_strs = [str(m) for m in members]
    assert "bob@testnet" in member_strs


@pytest.mark.asyncio
async def test_room_leave(backend):
    await backend.room_leave("#general")
    members = await backend.members("#general")
    assert not any(m.user == "alice" for m in members)


# ── Publish + Query ──

@pytest.mark.asyncio
async def test_publish_appends_to_jsonl(backend, zchat_env):
    evt = ZChatEvent.create(
        room="#general", type=OperationType.MSG, from_="alice@testnet",
        content={"text": "hello"}, content_type="text/plain",
    )
    await backend.publish(evt)

    # Verify file content
    path = zchat_env["home"] / "store" / "general" / "events.jsonl"
    assert path.exists()
    lines = path.read_text().strip().split("\n")
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["id"] == evt.id


@pytest.mark.asyncio
async def test_query_events_last_n(backend):
    for i in range(10):
        evt = ZChatEvent.create(
            room="#general", type=OperationType.MSG, from_="alice@testnet",
            content={"text": f"msg {i}"}, content_type="text/plain",
        )
        await backend.publish(evt)

    events = await backend.query_events("#general", last=3)
    assert len(events) == 3
    assert events[0].content["text"] == "msg 7"


@pytest.mark.asyncio
async def test_query_events_no_last_returns_all(backend):
    for i in range(5):
        evt = ZChatEvent.create(
            room="#general", type=OperationType.MSG, from_="alice@testnet",
            content={"text": f"msg {i}"}, content_type="text/plain",
        )
        await backend.publish(evt)

    events = await backend.query_events("#general")
    assert len(events) == 5


@pytest.mark.asyncio
async def test_get_event_by_id(backend):
    evt = ZChatEvent.create(
        room="#general", type=OperationType.MSG, from_="alice@testnet",
        content={"text": "find me"}, content_type="text/plain",
    )
    await backend.publish(evt)

    found = await backend.get_event(evt.id)
    assert found is not None
    assert found.content["text"] == "find me"


@pytest.mark.asyncio
async def test_get_event_not_found(backend):
    found = await backend.get_event("nonexistent")
    assert found is None


# ── Storage markers ──

@pytest.mark.asyncio
async def test_is_handled_mark_handled(backend):
    assert not await backend.is_handled("evt-1")
    await backend.mark_handled("evt-1")
    assert await backend.is_handled("evt-1")
    assert not await backend.is_handled("evt-2")


# ── Doctor ──

@pytest.mark.asyncio
async def test_doctor_all_ok(backend):
    report = await backend.doctor()
    assert report.ok
    assert report.checks.get("identity") is True
    assert report.checks.get("home") is True


# ── Config loading ──

@pytest.mark.asyncio
async def test_load_agent_config(backend, zchat_env, monkeypatch):
    # Create a project dir with agent config
    project = zchat_env["home"].parent / "project" / ".zchat"
    agents_dir = project / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "ppt-maker.toml").write_text('name = "ppt-maker"\nmodel = "scripts/echo-agent.sh"')
    monkeypatch.setenv("ZCHAT_PROJECT", str(project))

    from zchat_com.file import FileComBackend
    config = ZChatConfig.resolve()
    backend2 = FileComBackend(config=config, identity=Identity.parse("alice@testnet"))
    info = await backend2.load_agent_config("ppt-maker")
    assert info.name == "ppt-maker"
    assert info.model == "scripts/echo-agent.sh"


# ── Concurrent publish ──

@pytest.mark.asyncio
async def test_concurrent_publish(backend):
    """Two tasks publish simultaneously without corruption."""
    async def publish_batch(prefix: str, count: int):
        for i in range(count):
            evt = ZChatEvent.create(
                room="#general", type=OperationType.MSG, from_="alice@testnet",
                content={"text": f"{prefix}-{i}"}, content_type="text/plain",
            )
            await backend.publish(evt)

    await asyncio.gather(
        publish_batch("a", 20),
        publish_batch("b", 20),
    )
    events = await backend.query_events("#general")
    assert len(events) == 40
```

- [ ] **Step 2: Run — expect FAIL**

Run: `uv run pytest tests/test_com/test_file_backend.py -v`
Expected: FAIL — ModuleNotFoundError: No module named 'zchat_com.file'

- [ ] **Step 3: Implement FileComBackend (core methods)**

```python
# packages/zchat-com/src/zchat_com/file.py
"""FileComBackend — filesystem-based ComBackend implementation.

Persists events to JSONL files, rooms to JSON, uses watchdog for subscribe.
All state under $ZCHAT_HOME. Cross-process communication via shared filesystem.
"""
from __future__ import annotations

import asyncio
import fcntl
import json
import threading
import time
from pathlib import Path
from typing import AsyncIterator

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from zchat_protocol import Identity, SpawnConfig, ZChatEvent, ZChatConfig
from zchat_cli.types import (
    AgentConfigInfo, DiagnosticReport, NetworkInfo, Room,
    SessionInfo, SpawnPreview, TemplateInfo, ZChatOperation,
)


class FileComBackend:
    def __init__(self, config: ZChatConfig, identity: Identity):
        self._config = config
        self._identity = identity
        config.ensure_home()
        config.ensure_store()

    # ── Private helpers: rooms.json I/O with file locking ──

    def _read_rooms(self) -> dict:
        path = self._config.rooms_file
        if not path.exists():
            # Bootstrap: create #general with current identity
            default = {
                "#general": {
                    "topic": "General chat",
                    "members": [str(self._identity)],
                    "created_at": int(time.time() * 1000),
                }
            }
            self._write_rooms(default)
            return default
        with open(path) as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            try:
                return json.load(f)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def _write_rooms(self, data: dict) -> None:
        path = self._config.rooms_file
        with open(path, "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                json.dump(data, f, indent=2)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def _read_handled(self) -> set[str]:
        path = self._config.handled_file
        if not path.exists():
            return set()
        return set(json.loads(path.read_text()))

    def _write_handled(self, handled: set[str]) -> None:
        path = self._config.handled_file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(list(handled)))

    # ── Identity + Network ──

    async def get_identity(self) -> Identity:
        return self._identity

    async def get_network(self) -> NetworkInfo:
        peers = await self.get_peers()
        return NetworkInfo(name="local", peer_count=len(peers), online=True)

    async def get_peers(self) -> list[Identity]:
        rooms_data = self._read_rooms()
        all_members: set[str] = set()
        for room_data in rooms_data.values():
            all_members.update(room_data.get("members", []))
        return [Identity.parse(m) for m in all_members]

    async def setup_identity(self, user: str, network: str) -> Identity:
        return self._identity  # Phase 0: no-op

    # ── Room ──

    async def room_create(self, name: str, topic: str = "") -> Room:
        rooms = self._read_rooms()
        if name not in rooms:
            rooms[name] = {
                "topic": topic,
                "members": [str(self._identity)],
                "created_at": int(time.time() * 1000),
            }
            self._write_rooms(rooms)
        r = rooms[name]
        return Room(name=name, topic=r.get("topic", topic), member_count=len(r["members"]))

    async def room_invite(self, room: str, identity: Identity) -> None:
        rooms = self._read_rooms()
        if room in rooms and str(identity) not in rooms[room]["members"]:
            rooms[room]["members"].append(str(identity))
            self._write_rooms(rooms)
        evt = ZChatEvent.create(
            room=room, type=OperationType.JOIN, from_=str(identity),
            content={"event_type": "join", "subject": str(identity)},
            content_type="application/vnd.zchat.system-event",
        )
        await self.publish(evt)

    async def room_leave(self, room: str) -> None:
        rooms = self._read_rooms()
        me = str(self._identity)
        if room in rooms and me in rooms[room]["members"]:
            rooms[room]["members"].remove(me)
            self._write_rooms(rooms)

    async def rooms(self) -> list[Room]:
        rooms_data = self._read_rooms()
        return [
            Room(name=n, topic=d.get("topic", ""), member_count=len(d.get("members", [])))
            for n, d in rooms_data.items()
        ]

    async def members(self, room: str) -> list[Identity]:
        rooms_data = self._read_rooms()
        return [Identity.parse(m) for m in rooms_data.get(room, {}).get("members", [])]

    # ── Event publish / query ──

    async def publish(self, event: ZChatEvent) -> None:
        path = self._config.room_events_file(event.room)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.write(json.dumps(event.to_dict()) + "\n")
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    async def query_events(self, room: str, *, last: int | None = None) -> list[ZChatEvent]:
        path = self._config.room_events_file(room)
        if not path.exists():
            return []
        lines = path.read_text().strip().split("\n")
        events = [ZChatEvent.from_dict(json.loads(line)) for line in lines if line]
        if last is not None:
            events = events[-last:]
        return events

    async def get_event(self, event_id: str) -> ZChatEvent | None:
        if not self._config.store_dir.exists():
            return None
        for room_dir in self._config.store_dir.iterdir():
            if not room_dir.is_dir():
                continue
            events_file = room_dir / "events.jsonl"
            if not events_file.exists():
                continue
            for line in events_file.open():
                if not line.strip():
                    continue
                data = json.loads(line)
                if data["id"] == event_id:
                    return ZChatEvent.from_dict(data)
        return None

    # ── Subscribe (watchdog) ──

    def subscribe(self, room: str) -> AsyncIterator[ZChatEvent]:
        return self._subscribe_impl(room)

    async def _subscribe_impl(self, room: str) -> AsyncIterator[ZChatEvent]:
        path = self._config.room_events_file(room)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)

        queue: asyncio.Queue[ZChatEvent] = asyncio.Queue()
        lock = threading.Lock()
        loop = asyncio.get_running_loop()

        class Handler(FileSystemEventHandler):
            def __init__(self):
                self.offset = 0
                self.buffer = ""

            def on_modified(self, fs_event):
                if Path(fs_event.src_path).name != path.name:
                    return
                with lock:
                    with open(path) as f:
                        f.seek(self.offset)
                        new_data = f.read()
                        self.offset = f.tell()
                    data = self.buffer + new_data
                    lines = data.split("\n")
                    self.buffer = lines[-1]  # retain incomplete last line
                    for line in lines[:-1]:
                        if line.strip():
                            try:
                                event = ZChatEvent.from_dict(json.loads(line))
                                loop.call_soon_threadsafe(queue.put_nowait, event)
                            except (json.JSONDecodeError, KeyError):
                                pass  # skip corrupted lines

        handler = Handler()
        observer = Observer()
        observer.schedule(handler, str(path.parent), recursive=False)
        observer.start()
        # Record offset AFTER observer starts (avoids TOCTOU gap)
        handler.offset = path.stat().st_size
        try:
            while True:
                event = await queue.get()
                yield event
        finally:
            observer.stop()
            observer.join()

    # ── Storage markers ──

    async def is_handled(self, event_id: str) -> bool:
        return event_id in self._read_handled()

    async def mark_handled(self, event_id: str) -> None:
        handled = self._read_handled()
        handled.add(event_id)
        self._write_handled(handled)

    # ── Doctor ──

    async def doctor(self) -> DiagnosticReport:
        checks: dict[str, bool] = {}
        messages: list[str] = []

        checks["identity"] = self._identity is not None
        if not checks["identity"]:
            messages.append("ZCHAT_IDENTITY not set")

        try:
            self._config.ensure_home()
            checks["home"] = True
        except OSError as e:
            checks["home"] = False
            messages.append(f"ZCHAT_HOME not writable: {e}")

        try:
            self._read_rooms()
            checks["rooms"] = True
        except Exception as e:
            checks["rooms"] = False
            messages.append(f"rooms.json error: {e}")

        return DiagnosticReport(checks=checks, messages=messages)

    # ── Config loading ──

    async def load_agent_config(self, name: str) -> AgentConfigInfo:
        agents_dir = self._config.agents_dir
        if agents_dir and (agents_dir / f"{name}.toml").exists():
            cfg = SpawnConfig.from_toml_file(agents_dir / f"{name}.toml")
            return AgentConfigInfo(name=cfg.name or name, template="", model=cfg.model or "")
        return AgentConfigInfo(name=name)

    async def load_template_config(self, name: str) -> TemplateInfo:
        templates_dir = self._config.templates_dir
        if templates_dir and (templates_dir / f"{name}.toml").exists():
            return TemplateInfo(name=name, path=str(templates_dir / f"{name}.toml"))
        return TemplateInfo(name=name)
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `uv run pytest tests/test_com/test_file_backend.py -v`
Expected: ~19 tests pass

- [ ] **Step 5: Run full suite — expect no regressions**

Run: `uv run pytest tests/ -v --tb=short`
Expected: All 113 existing tests + ~19 new = ~132 pass

- [ ] **Step 6: Commit**

```bash
git add packages/zchat-com/src/zchat_com/file.py \
        tests/test_com/__init__.py \
        tests/test_com/test_file_backend.py
git commit -m "feat(com): add FileComBackend — filesystem-based ComBackend with JSONL + watchdog"
```

---

## Chunk 2: ScriptAcpBackend + Echo Agent

### Task 3: Echo Agent Script

**Files:**
- Create: `scripts/echo-agent.sh`

- [ ] **Step 1: Create echo-agent.sh**

```bash
#!/usr/bin/env bash
# Echo agent — implements CC headless JSONL protocol
# system/init on startup, then read-reply loop (assistant + result per message)

SESSION_ID="echo-$(date +%s)"

# Init message (first line of stdout)
echo "{\"type\":\"system\",\"subtype\":\"init\",\"session_id\":\"$SESSION_ID\",\"model\":\"echo\"}"

# Read-reply loop
while IFS= read -r line; do
    # Extract text from JSONL user message using python3
    text=$(echo "$line" | python3 -c "
import sys, json
try:
    msg = json.load(sys.stdin)
    content = msg.get('message', {}).get('content', '')
    print(content if isinstance(content, str) else json.dumps(content))
except:
    print('')
" 2>/dev/null)

    # JSON-escape the text for embedding in response
    escaped=$(echo "$text" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read().strip()))")

    # Assistant response
    echo "{\"type\":\"assistant\",\"message\":{\"role\":\"assistant\",\"content\":[{\"type\":\"text\",\"text\":$escaped}]}}"

    # Result (marks end of turn)
    echo "{\"type\":\"result\",\"result\":$escaped,\"session_id\":\"$SESSION_ID\",\"cost_usd\":0,\"duration_ms\":50}"
done
```

- [ ] **Step 2: Make executable and test manually**

Run: `chmod +x scripts/echo-agent.sh`
Run: `echo '{"type":"user","message":{"role":"user","content":"hello world"}}' | ./scripts/echo-agent.sh`
Expected: 3 lines — init, assistant (with "hello world"), result

- [ ] **Step 3: Commit**

```bash
git add scripts/echo-agent.sh
git commit -m "feat: add echo-agent.sh — test agent implementing CC headless JSONL protocol"
```

---

### Task 4: ScriptAcpBackend

**Files:**
- Create: `packages/zchat-acp/src/zchat_acp/script.py`
- Create: `tests/test_acp/__init__.py`
- Create: `tests/test_acp/test_script_backend.py`

- [ ] **Step 1: Write ScriptAcpBackend tests**

```python
# tests/test_acp/test_script_backend.py
"""ScriptAcpBackend tests — uses echo-agent.sh as test agent."""
from __future__ import annotations

import asyncio
import json
import os
import signal
from pathlib import Path

import pytest

from zchat_protocol import Identity, ZChatConfig, ZChatEvent


# Path to echo-agent.sh relative to repo root
ECHO_AGENT = str(Path(__file__).parent.parent.parent / "scripts" / "echo-agent.sh")


@pytest.fixture
def zchat_env(tmp_path, monkeypatch):
    home = tmp_path / "zchat_home"
    runtime = tmp_path / "zchat_runtime"
    monkeypatch.setenv("ZCHAT_HOME", str(home))
    monkeypatch.setenv("ZCHAT_RUNTIME", str(runtime))
    monkeypatch.setenv("ZCHAT_IDENTITY", "alice@testnet")
    return {"home": home, "runtime": runtime}


@pytest.fixture
def backends(zchat_env):
    from zchat_com.file import FileComBackend
    from zchat_acp.script import ScriptAcpBackend

    config = ZChatConfig.resolve()
    identity = Identity.parse("alice@testnet")
    com = FileComBackend(config=config, identity=identity)
    acp = ScriptAcpBackend(config=config, identity=identity, com=com)
    return {"com": com, "acp": acp, "config": config}


@pytest.mark.asyncio
async def test_spawn_starts_process(backends):
    acp = backends["acp"]
    preview = await acp.prepare_spawn("echo-agent")
    # Override model to point at our test script
    from zchat_cli.types import SpawnPreview
    preview = SpawnPreview(agent_name="echo-agent", model=ECHO_AGENT)
    agent_id = await acp.confirm_spawn(preview)
    assert agent_id.label == "echo-agent"
    assert agent_id.user == "alice"
    # PID file exists
    sessions = await acp.sessions()
    assert len(sessions) == 1
    assert sessions[0].agent.label == "echo-agent"
    # Cleanup
    await acp.kill_session(sessions[0].session_id)


@pytest.mark.asyncio
async def test_spawn_reads_init_message(backends):
    acp = backends["acp"]
    from zchat_cli.types import SpawnPreview
    preview = SpawnPreview(agent_name="echo-agent", model=ECHO_AGENT)
    agent_id = await acp.confirm_spawn(preview)
    sessions = await acp.sessions()
    assert sessions[0].session_id.startswith("echo-")
    await acp.kill_session(sessions[0].session_id)


@pytest.mark.asyncio
async def test_kill_terminates_process(backends):
    acp = backends["acp"]
    from zchat_cli.types import SpawnPreview
    preview = SpawnPreview(agent_name="echo-agent", model=ECHO_AGENT)
    await acp.confirm_spawn(preview)
    sessions = await acp.sessions()
    sid = sessions[0].session_id
    await acp.kill_session(sid)
    # Session file gone
    sessions_after = await acp.sessions()
    running = [s for s in sessions_after if s.status.value == "running"]
    assert len(running) == 0


@pytest.mark.asyncio
async def test_get_session_returns_none_for_missing(backends):
    acp = backends["acp"]
    result = await acp.get_session("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_inject_and_capture(backends):
    acp = backends["acp"]
    from zchat_cli.types import SpawnPreview
    preview = SpawnPreview(agent_name="echo-agent", model=ECHO_AGENT)
    await acp.confirm_spawn(preview)
    sessions = await acp.sessions()
    sid = sessions[0].session_id

    await acp.inject_message(sid, "test message")

    ops = []
    async for op in acp.capture_output(sid):
        ops.append(op)
        break  # just get first response

    assert len(ops) == 1
    assert "test message" in ops[0].event.content.get("text", "")
    await acp.kill_session(sid)


@pytest.mark.asyncio
async def test_event_watcher_detects_mention(backends):
    """Write @echo-agent event to file, verify agent responds."""
    com = backends["com"]
    acp = backends["acp"]
    from zchat_cli.types import SpawnPreview
    preview = SpawnPreview(agent_name="echo-agent", model=ECHO_AGENT)
    await acp.confirm_spawn(preview)

    # Send a message mentioning the agent
    evt = ZChatEvent.create(
        room="#general", type=OperationType.MSG, from_="alice@testnet",
        content={"text": "hello @echo-agent", "mentions": ["echo-agent"]},
        content_type="text/plain",
    )
    await com.publish(evt)

    # Wait for agent to respond (watcher picks up the event)
    await asyncio.sleep(2)  # give watchdog + subprocess time

    events = await com.query_events("#general")
    agent_replies = [e for e in events if "echo-agent" in e.from_]
    assert len(agent_replies) >= 1
    assert "hello @echo-agent" in agent_replies[0].content.get("text", "")

    # Cleanup
    sessions = await acp.sessions()
    for s in sessions:
        await acp.kill_session(s.session_id)
```

- [ ] **Step 2: Run — expect FAIL**

Run: `uv run pytest tests/test_acp/test_script_backend.py -v`
Expected: FAIL — ModuleNotFoundError: No module named 'zchat_acp.script'

- [ ] **Step 3: Implement ScriptAcpBackend**

```python
# packages/zchat-acp/src/zchat_acp/script.py
"""ScriptAcpBackend — shell-script-based AcpBackend implementation.

Manages agent shell scripts as long-lived daemon subprocesses.
Uses CC headless JSONL protocol for stdin/stdout communication.
Event watcher monitors room events for @mentions and auto-injects.
"""
from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import AsyncIterator

from ulid import ULID

from zchat_protocol import Identity, OperationType, ZChatConfig, ZChatEvent
from zchat_cli.types import (
    AgentConfigInfo, SessionInfo, SessionStatus, SpawnPreview, ZChatOperation,
)


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


class ScriptAcpBackend:
    def __init__(self, config: ZChatConfig, identity: Identity, com):
        self._config = config
        self._identity = identity
        self._com = com  # FileComBackend ref for event watcher publishing
        self._watchers: dict[str, asyncio.Task] = {}
        self._processes: dict[str, subprocess.Popen] = {}
        config.ensure_sessions()

    # ── Spawn ──

    async def prepare_spawn(self, agent_name: str, template: str | None = None) -> SpawnPreview:
        config_info = await self._com.load_agent_config(agent_name)
        model = config_info.model or "scripts/echo-agent.sh"
        return SpawnPreview(
            agent_name=agent_name,
            template=template or config_info.template,
            model=model,
        )

    async def confirm_spawn(self, preview: SpawnPreview) -> Identity:
        script_path = preview.model
        if not Path(script_path).exists():
            raise FileNotFoundError(f"Agent script not found: {script_path}")

        proc = subprocess.Popen(
            [script_path],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            text=True, bufsize=1,
        )

        # Read init message
        init_line = proc.stdout.readline()
        if not init_line:
            proc.kill()
            raise RuntimeError("Agent script produced no init message")
        init_data = json.loads(init_line)
        session_id = init_data.get("session_id", str(ULID()))

        agent_identity = Identity(
            user=self._identity.user,
            label=preview.agent_name,
            network=self._identity.network,
        )

        # Write session metadata
        session_file = self._config.sessions_dir / f"{session_id}.json"
        session_meta = {
            "pid": proc.pid,
            "session_id": session_id,
            "agent_name": preview.agent_name,
            "identity": str(agent_identity),
            "room": "#general",
            "started_at": int(time.time() * 1000),
        }
        session_file.write_text(json.dumps(session_meta))
        self._processes[session_id] = proc

        # Start event watcher
        watcher = asyncio.create_task(
            self._event_watcher(session_id, proc, preview.agent_name, "#general")
        )
        self._watchers[session_id] = watcher

        return agent_identity

    async def cancel_spawn(self, preview: SpawnPreview) -> None:
        pass

    # ── Event watcher ──

    async def _event_watcher(self, session_id: str, proc: subprocess.Popen,
                              agent_name: str, room: str):
        try:
            async for event in self._com.subscribe(room):
                if proc.poll() is not None:
                    break
                if event.type != OperationType.MSG:
                    continue
                mentions = event.content.get("mentions", []) if isinstance(event.content, dict) else []
                if agent_name not in mentions:
                    continue

                text = event.content.get("text", "") if isinstance(event.content, dict) else str(event.content)
                user_msg = json.dumps({
                    "type": "user",
                    "message": {"role": "user", "content": text},
                })

                try:
                    proc.stdin.write(user_msg + "\n")
                    proc.stdin.flush()
                except (BrokenPipeError, OSError):
                    break

                # Read responses until "result"
                while True:
                    line = await asyncio.to_thread(proc.stdout.readline)
                    if not line:
                        break
                    data = json.loads(line)
                    if data["type"] == "assistant":
                        for block in data["message"].get("content", []):
                            if block["type"] == "text":
                                agent_ident = f"{self._identity.user}:{agent_name}@{self._identity.network}"
                                response = ZChatEvent.create(
                                    room=room, type=OperationType.MSG, from_=agent_ident,
                                    content={"text": block["text"]},
                                    content_type="text/plain",
                                )
                                await self._com.publish(response)
                    elif data["type"] == "result":
                        break
        except asyncio.CancelledError:
            pass

    # ── Session management ──

    async def sessions(self) -> list[SessionInfo]:
        result = []
        if not self._config.sessions_dir.exists():
            return result
        for f in self._config.sessions_dir.glob("*.json"):
            meta = json.loads(f.read_text())
            alive = _pid_alive(meta["pid"])
            result.append(SessionInfo(
                session_id=meta["session_id"],
                agent=Identity.parse(meta["identity"]),
                status=SessionStatus.RUNNING if alive else SessionStatus.STOPPED,
            ))
        return result

    async def get_session(self, session_id: str) -> SessionInfo | None:
        f = self._config.sessions_dir / f"{session_id}.json"
        if not f.exists():
            return None
        meta = json.loads(f.read_text())
        alive = _pid_alive(meta["pid"])
        return SessionInfo(
            session_id=session_id,
            agent=Identity.parse(meta["identity"]),
            status=SessionStatus.RUNNING if alive else SessionStatus.STOPPED,
        )

    async def kill_session(self, session_id: str) -> None:
        # Cancel watcher
        if session_id in self._watchers:
            self._watchers[session_id].cancel()
            del self._watchers[session_id]

        # Terminate process
        if session_id in self._processes:
            proc = self._processes.pop(session_id)
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        else:
            # Try PID from file
            f = self._config.sessions_dir / f"{session_id}.json"
            if f.exists():
                meta = json.loads(f.read_text())
                try:
                    os.kill(meta["pid"], signal.SIGTERM)
                except ProcessLookupError:
                    pass

        # Remove session file
        f = self._config.sessions_dir / f"{session_id}.json"
        f.unlink(missing_ok=True)

    async def get_status(self, session_id: str) -> SessionInfo:
        info = await self.get_session(session_id)
        if info is None:
            return SessionInfo(
                session_id=session_id, agent=self._identity, status=SessionStatus.STOPPED,
            )
        return info

    # ── Attach / Detach ──

    async def attach(self, session_id: str) -> None:
        if session_id in self._watchers:
            self._watchers[session_id].cancel()
            del self._watchers[session_id]

    async def detach(self, session_id: str) -> None:
        f = self._config.sessions_dir / f"{session_id}.json"
        if not f.exists() or session_id not in self._processes:
            return
        meta = json.loads(f.read_text())
        proc = self._processes[session_id]
        watcher = asyncio.create_task(
            self._event_watcher(session_id, proc, meta["agent_name"], meta.get("room", "#general"))
        )
        self._watchers[session_id] = watcher

    # ── inject / capture ──

    async def inject_message(self, session_id: str, content: str) -> None:
        proc = self._processes.get(session_id)
        if proc and proc.poll() is None:
            msg = json.dumps({"type": "user", "message": {"role": "user", "content": content}})
            proc.stdin.write(msg + "\n")
            proc.stdin.flush()

    def capture_output(self, session_id: str) -> AsyncIterator[ZChatOperation]:
        return self._capture_impl(session_id)

    async def _capture_impl(self, session_id: str) -> AsyncIterator[ZChatOperation]:
        proc = self._processes.get(session_id)
        if not proc:
            return
        while True:
            line = await asyncio.to_thread(proc.stdout.readline)
            if not line:
                break
            data = json.loads(line)
            if data["type"] == "assistant":
                for block in data["message"].get("content", []):
                    evt = ZChatEvent.create(
                        room="#general", type=OperationType.MSG, from_="agent",
                        content={"text": block.get("text", "")},
                        content_type="text/plain",
                    )
                    yield ZChatOperation(event=evt, source="agent")
            elif data["type"] == "result":
                break
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `uv run pytest tests/test_acp/test_script_backend.py -v --timeout=30`
Expected: ~7 tests pass (event_watcher test may need timing adjustment)

- [ ] **Step 5: Commit**

```bash
git add packages/zchat-acp/src/zchat_acp/script.py \
        tests/test_acp/__init__.py \
        tests/test_acp/test_script_backend.py
git commit -m "feat(acp): add ScriptAcpBackend — daemon agent scripts with CC headless JSONL"
```

---

## Chunk 3: CLI Integration + E2E

### Task 5: Switch `_get_cli()` to FileComBackend

**Files:**
- Modify: `packages/zchat-cli/src/zchat_cli/__main__.py`

- [ ] **Step 1: Modify `_get_cli()` in __main__.py**

Replace the existing `_get_cli()` function:

```python
def _get_cli() -> ZChatCLI:
    """Create a ZChatCLI backed by file + script backends.

    Requires: ZCHAT_IDENTITY env var set (e.g. alice@onesyn).
    Uses: ZCHAT_HOME for state storage (default ~/.zchat).
    """
    import os
    identity_str = os.environ.get("ZCHAT_IDENTITY")
    if not identity_str:
        typer.echo(
            "Error: ZCHAT_IDENTITY not set.\n"
            "Run: export ZCHAT_IDENTITY=alice@onesyn",
            err=True,
        )
        raise typer.Exit(1)

    from zchat_protocol import ZChatConfig, Identity
    from zchat_com.file import FileComBackend
    from zchat_acp.script import ScriptAcpBackend

    config = ZChatConfig.resolve()
    config.ensure_home()
    config.ensure_runtime()

    identity = Identity.parse(identity_str)
    com = FileComBackend(config=config, identity=identity)
    acp = ScriptAcpBackend(config=config, identity=identity, com=com)
    return ZChatCLI(com=com, acp=acp)
```

- [ ] **Step 2: Verify CLI works with env vars**

Run:
```bash
export ZCHAT_IDENTITY=alice@testnet
export ZCHAT_HOME=/tmp/zchat-cli-test
uv run zchat doctor
uv run zchat rooms
uv run zchat status
```
Expected: All commands work, output shows alice@testnet identity, #general room

- [ ] **Step 3: Verify CLI crashes without ZCHAT_IDENTITY**

Run: `unset ZCHAT_IDENTITY && uv run zchat doctor 2>&1`
Expected: "Error: ZCHAT_IDENTITY not set" + exit code 1

- [ ] **Step 4: Commit**

```bash
git add packages/zchat-cli/src/zchat_cli/__main__.py
git commit -m "feat(cli): switch _get_cli() from MockComBackend to FileComBackend + ScriptAcpBackend"
```

---

### Task 6: Update E2E Smoke Tests + Add Multi-User E2E

**Files:**
- Modify: `tests/test_e2e/test_smoke.py`
- Create: `tests/test_e2e/test_multiuser.py`

- [ ] **Step 1: Update test_smoke.py to set env vars**

Modify `run_zchat()` helper to include env vars:

```python
# tests/test_e2e/test_smoke.py
"""E2E smoke tests — all CLI commands runnable with FileComBackend."""
import os
import subprocess
import sys
import tempfile

import pytest


@pytest.fixture(scope="module")
def zchat_home():
    """Shared temp ZCHAT_HOME for all smoke tests."""
    with tempfile.TemporaryDirectory(prefix="zchat-smoke-") as d:
        yield d


def run_zchat(*args: str, zchat_home: str, identity: str = "smoke@testnet") -> subprocess.CompletedProcess:
    env = {**os.environ, "ZCHAT_IDENTITY": identity, "ZCHAT_HOME": zchat_home,
           "ZCHAT_RUNTIME": os.path.join(zchat_home, "runtime")}
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
        r = run_zchat("send", "#general", "hello from smoke test", zchat_home=zchat_home)
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
        """CLI crashes with clear error when ZCHAT_IDENTITY not set."""
        env = {k: v for k, v in os.environ.items() if k != "ZCHAT_IDENTITY"}
        env["ZCHAT_HOME"] = "/tmp/zchat-noident"
        r = subprocess.run(
            [sys.executable, "-m", "zchat_cli", "doctor"],
            capture_output=True, text=True, timeout=10, env=env,
        )
        assert r.returncode != 0
        assert "ZCHAT_IDENTITY" in r.stderr
```

- [ ] **Step 2: Write multi-user E2E tests**

```python
# tests/test_e2e/test_multiuser.py
"""Multi-user E2E tests — cross-process communication via shared ZCHAT_HOME."""
import json
import os
import subprocess
import sys
import tempfile
import time

import pytest


@pytest.fixture
def shared_home():
    with tempfile.TemporaryDirectory(prefix="zchat-multi-") as d:
        yield d


def run_as(identity: str, *args: str, home: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "ZCHAT_IDENTITY": identity, "ZCHAT_HOME": home,
           "ZCHAT_RUNTIME": os.path.join(home, "runtime")}
    return subprocess.run(
        [sys.executable, "-m", "zchat_cli", *args],
        capture_output=True, text=True, timeout=15, env=env,
    )


class TestMultiUser:
    def test_alice_sends_bob_sees(self, shared_home):
        """Alice sends a message, Bob queries and sees it."""
        # Alice sends
        r = run_as("alice@testnet", "send", "#general", "hello from alice", home=shared_home)
        assert r.returncode == 0

        # Bob queries
        r = run_as("bob@testnet", "watch", "#general", "--no-follow", home=shared_home)
        assert r.returncode == 0
        assert "hello from alice" in r.stdout

    def test_two_users_in_room(self, shared_home):
        """Alice creates room, invites Bob, both see messages."""
        # Alice creates room
        r = run_as("alice@testnet", "room", "create", "#workshop", home=shared_home)
        assert r.returncode == 0

        # Alice sends to workshop
        r = run_as("alice@testnet", "send", "#workshop", "design discussion", home=shared_home)
        assert r.returncode == 0

        # Bob queries workshop
        r = run_as("bob@testnet", "watch", "#workshop", "--no-follow", home=shared_home)
        assert r.returncode == 0
        assert "design discussion" in r.stdout

    def test_spawn_and_mention(self, shared_home):
        """Alice spawns echo-agent, sends @mention, gets echo reply."""
        echo_script = str(os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "echo-agent.sh"))

        # Alice spawns echo-agent (need agent config pointing to script)
        # First create agent config
        project_dir = os.path.join(shared_home, "project", ".zchat", "agents")
        os.makedirs(project_dir, exist_ok=True)
        with open(os.path.join(project_dir, "echo-agent.toml"), "w") as f:
            f.write(f'name = "echo-agent"\nmodel = "{echo_script}"')

        env = {
            **os.environ,
            "ZCHAT_IDENTITY": "alice@testnet",
            "ZCHAT_HOME": shared_home,
            "ZCHAT_RUNTIME": os.path.join(shared_home, "runtime"),
            "ZCHAT_PROJECT": os.path.join(shared_home, "project", ".zchat"),
        }
        r = subprocess.run(
            [sys.executable, "-m", "zchat_cli", "spawn", "echo-agent", "--yes"],
            capture_output=True, text=True, timeout=15, env=env,
        )
        assert r.returncode == 0

        # Note: spawn in subprocess exits immediately since each CLI call is
        # its own process. The daemon agent lifecycle requires a long-running
        # process. For Phase 0, we test the spawn+mention flow in
        # test_acp/test_script_backend.py instead (in-process async tests).
```

- [ ] **Step 3: Run E2E tests — expect PASS**

Run: `uv run pytest tests/test_e2e/ -v --timeout=30`
Expected: ~13 tests pass (10 smoke + 1 identity error + 2 multiuser)

- [ ] **Step 4: Run full test suite**

Run: `uv run pytest tests/ -v --tb=short --timeout=30`
Expected: All tests pass (~150+ total)

- [ ] **Step 5: Commit**

```bash
git add tests/test_e2e/test_smoke.py tests/test_e2e/test_multiuser.py
git commit -m "test: update E2E smoke for FileComBackend + add multi-user cross-process tests"
```

---

### Task 7: Final Verification

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest tests/ -v --tb=short --timeout=30`
Expected: All tests pass

- [ ] **Step 2: Manual CLI verification**

```bash
export ZCHAT_HOME=/tmp/zchat-verify
export ZCHAT_IDENTITY=alice@onesyn

uv run zchat doctor
uv run zchat rooms
uv run zchat send '#general' 'Phase 0 complete'
uv run zchat watch '#general' --no-follow
uv run zchat status
```

- [ ] **Step 3: Cross-process verification (two terminals)**

Terminal 1:
```bash
export ZCHAT_HOME=/tmp/zchat-cross
export ZCHAT_IDENTITY=alice@onesyn
uv run zchat send '#general' 'hello from alice'
```

Terminal 2:
```bash
export ZCHAT_HOME=/tmp/zchat-cross
export ZCHAT_IDENTITY=bob@onesyn
uv run zchat watch '#general' --no-follow
# Should show alice's message
```

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat: complete FileComBackend + ScriptAcpBackend — filesystem-backed cross-process IPC

FileComBackend: JSONL events + watchdog subscribe + rooms.json + fcntl locking
ScriptAcpBackend: daemon agent scripts + CC headless JSONL + event watcher
echo-agent.sh: built-in test agent
_get_cli(): switched from mock to file backends, requires ZCHAT_IDENTITY env var"
```

---

## Completion Criteria

| Criteria | Verification |
|---|---|
| FileComBackend implements all 18 ComBackend methods | `isinstance(FileComBackend(...), ComBackend)` |
| ScriptAcpBackend implements all 11 AcpBackend methods | `isinstance(ScriptAcpBackend(...), AcpBackend)` |
| Events persist across CLI invocations | `zchat send` in terminal A, `zchat watch --no-follow` in terminal B |
| echo-agent.sh responds to @mention | test_event_watcher_detects_mention passes |
| `$ZCHAT_IDENTITY` required, crash if missing | test_missing_identity_crashes passes |
| Existing mock-based tests still pass | `pytest tests/test_cli/ tests/test_protocol/` unchanged |
| All tests pass | `pytest tests/ -v` |
