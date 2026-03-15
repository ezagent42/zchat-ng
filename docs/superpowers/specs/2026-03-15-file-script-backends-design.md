# FileComBackend + ScriptAcpBackend Design Spec

**Date:** 2026-03-15
**Status:** Approved (rev 2 — fixed against actual Protocol signatures)
**Goal:** Replace in-memory mocks with filesystem-backed implementations enabling cross-process multi-user E2E testing in Phase 0.

---

## 1. Motivation

Phase 0's MockComBackend/MockAcpBackend store all state in-memory. Each `zchat` CLI invocation creates fresh backends — no cross-process communication is possible. This prevents multi-user testing (e.g. alice and bob in separate terminals).

FileComBackend + ScriptAcpBackend solve this by using:
- JSONL files in `$ZCHAT_HOME/store/` as the event bus (cross-process IPC)
- watchdog (fsevents/inotify) for real-time event notification
- Shell script subprocesses as agent stand-ins (CC headless JSONL protocol)

These are the **first real implementations** of the ComBackend and AcpBackend Protocols. They serve as a stepping stone:

```
Phase 0:  FileComBackend (filesystem IPC)   → ScriptAcpBackend (shell scripts)
Phase 1:  ZenohComBackend (Zenoh P2P)       → HeadlessAcpBackend (CC headless)
```

---

## 2. Key Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Subscribe mechanism | watchdog (inotify/fsevents) | Near-instant event delivery, no polling latency |
| Identity source | `$ZCHAT_IDENTITY` env var only | "One way to do it" — no file fallback, crash if missing |
| Agent script protocol | JSONL (CC headless format) | Zero-change path to Phase 1 HeadlessAcpBackend |
| Agent lifecycle | Daemon (long-lived subprocess) | Aligns with Phase 1 process pool; enables session continuity |
| Runtime backend selection | FileComBackend is the only CLI runtime backend | MockComBackend demoted to test-only fixture |

---

## 3. Actual Protocol Signatures (Source of Truth)

These are the actual signatures from `backends.py` that FileComBackend and ScriptAcpBackend must implement.

### 3.1 ComBackend (18 methods)

```python
class ComBackend(Protocol):
    async def get_identity(self) -> Identity: ...
    async def get_network(self) -> NetworkInfo: ...
    async def get_peers(self) -> list[Identity]: ...
    async def setup_identity(self, user: str, network: str) -> Identity: ...

    async def room_create(self, name: str, topic: str = "") -> Room: ...
    async def room_invite(self, room: str, identity: Identity) -> None: ...
    async def room_leave(self, room: str) -> None: ...
    async def rooms(self) -> list[Room]: ...
    async def members(self, room: str) -> list[Identity]: ...

    async def publish(self, event: ZChatEvent) -> None: ...
    def subscribe(self, room: str) -> AsyncIterator[ZChatEvent]: ...  # NOT async def
    async def query_events(self, room: str, *, last: int | None = None) -> list[ZChatEvent]: ...
    async def get_event(self, event_id: str) -> ZChatEvent | None: ...
    async def is_handled(self, event_id: str) -> bool: ...
    async def mark_handled(self, event_id: str) -> None: ...

    async def doctor(self) -> DiagnosticReport: ...
    async def load_agent_config(self, name: str) -> AgentConfigInfo: ...
    async def load_template_config(self, name: str) -> TemplateInfo: ...
```

### 3.2 AcpBackend (11 methods)

```python
class AcpBackend(Protocol):
    async def prepare_spawn(self, agent_name: str, template: str | None = None) -> SpawnPreview: ...
    async def confirm_spawn(self, preview: SpawnPreview) -> Identity: ...
    async def cancel_spawn(self, preview: SpawnPreview) -> None: ...

    async def sessions(self) -> list[SessionInfo]: ...
    async def get_session(self, session_id: str) -> SessionInfo | None: ...
    async def kill_session(self, session_id: str) -> None: ...

    async def inject_message(self, session_id: str, content: str) -> None: ...
    def capture_output(self, session_id: str) -> AsyncIterator[ZChatOperation]: ...  # NOT async def

    async def attach(self, session_id: str) -> None: ...
    async def detach(self, session_id: str) -> None: ...
    async def get_status(self, session_id: str) -> SessionInfo: ...
```

### 3.3 Key CLI Types (from types.py)

```python
@dataclass
class NetworkInfo:        name: str, peer_count: int = 0, online: bool = False
class Room:               name: str, topic: str = "", member_count: int = 0
class SpawnPreview:       agent_name: str, template: str = "", model: str = "", estimated_cost: float = 0.0
class SessionInfo:        session_id: str, agent: Identity, status: SessionStatus, attached: bool
class DiagnosticReport:   checks: dict[str, bool], messages: list[str], ok: property
class AgentConfigInfo:    name: str, template: str = "", model: str = ""
class TemplateInfo:       name: str, description: str = "", path: str = ""
class ZChatOperation:     event: ZChatEvent, source: str = "local", handled: bool = False
class SessionStatus(StrEnum): RUNNING, STOPPED, ERROR
```

### 3.4 SpawnConfig (from protocol)

```python
@dataclass(frozen=True)
class SpawnConfig:
    name: str
    model: str | None = None
    system_prompt: str | None = None
    skills: list[str] = field(default_factory=list)
```

---

## 4. ZChatConfig Additions

Add two new properties to `ZChatConfig`:

```python
@property
def rooms_file(self) -> Path:
    return self.home / "rooms.json"

@property
def handled_file(self) -> Path:
    return self.store_dir / ".handled.json"
```

---

## 5. FileComBackend

Implements all 18 `ComBackend` methods. All state persisted under `$ZCHAT_HOME/`.

### 5.1 Constructor

```python
class FileComBackend:
    def __init__(self, config: ZChatConfig, identity: Identity):
        self._config = config
        self._identity = identity
        config.ensure_home()
        config.ensure_store()
```

### 5.2 Identity + Network

```python
async def get_identity(self) -> Identity:
    return self._identity  # from $ZCHAT_IDENTITY

async def get_network(self) -> NetworkInfo:
    # Phase 0: single-machine filesystem, always "local"
    peers = await self.get_peers()
    return NetworkInfo(name="local", peer_count=len(peers), online=True)

async def get_peers(self) -> list[Identity]:
    # Read all unique identities from rooms.json members lists
    rooms_data = self._read_rooms()
    all_members: set[str] = set()
    for room_data in rooms_data.values():
        all_members.update(room_data.get("members", []))
    return [Identity.parse(m) for m in all_members]

async def setup_identity(self, user: str, network: str) -> Identity:
    # Phase 0: identity is env-var only, setup is a no-op that returns current
    # In Phase 1 this would write to identity.toml + gh auth
    return self._identity
```

### 5.3 Room Management

**Storage:** `$ZCHAT_HOME/rooms.json` (via `config.rooms_file`)

```json
{
  "#general": {
    "topic": "",
    "members": ["alice@onesyn", "bob@onesyn"],
    "created_at": 1710500000000
  }
}
```

**Concurrency:** `fcntl.flock(LOCK_EX)` for writes, `LOCK_SH` for reads.

**Bootstrap:** If `rooms.json` doesn't exist on first read, create with `#general` containing current identity.

```python
async def room_create(self, name: str, topic: str = "") -> Room:
    rooms = self._read_rooms()
    if name not in rooms:
        rooms[name] = {
            "topic": topic,
            "members": [str(self._identity)],
            "created_at": int(time.time() * 1000),
        }
        self._write_rooms(rooms)
    return Room(name=name, topic=topic, member_count=len(rooms[name]["members"]))

async def room_invite(self, room: str, identity: Identity) -> None:
    rooms = self._read_rooms()
    if room in rooms and str(identity) not in rooms[room]["members"]:
        rooms[room]["members"].append(str(identity))
        self._write_rooms(rooms)
    # Publish SystemEvent(join)
    evt = ZChatEvent.create(room=room, type="join", from_=str(identity),
                            content={"event_type": "join", "subject": str(identity)})
    await self.publish(evt)

async def room_leave(self, room: str) -> None:
    rooms = self._read_rooms()
    me = str(self._identity)
    if room in rooms and me in rooms[room]["members"]:
        rooms[room]["members"].remove(me)
        self._write_rooms(rooms)

async def rooms(self) -> list[Room]:
    rooms_data = self._read_rooms()
    return [Room(name=n, topic=d.get("topic", ""), member_count=len(d.get("members", [])))
            for n, d in rooms_data.items()]

async def members(self, room: str) -> list[Identity]:
    rooms_data = self._read_rooms()
    return [Identity.parse(m) for m in rooms_data.get(room, {}).get("members", [])]
```

### 5.4 Event Persistence

**Storage:** `$ZCHAT_HOME/store/{room}/events.jsonl` (via `config.room_events_file()`)

```python
async def publish(self, event: ZChatEvent) -> None:
    path = self._config.room_events_file(event.room)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(event.to_dict()) + "\n")

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
    for room_dir in self._config.store_dir.iterdir():
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
```

### 5.5 Subscribe (watchdog)

`subscribe(room)` is a sync method returning `AsyncIterator[ZChatEvent]` (matches Protocol — NOT `async def`).

**Race condition fix:** Start observer BEFORE recording offset. Protect offset with `threading.Lock`. Buffer incomplete lines.

```python
def subscribe(self, room: str) -> AsyncIterator[ZChatEvent]:
    return self._subscribe_impl(room)

async def _subscribe_impl(self, room: str) -> AsyncIterator[ZChatEvent]:
    path = self._config.room_events_file(room)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)

    queue: asyncio.Queue[ZChatEvent] = asyncio.Queue()
    lock = threading.Lock()
    buffer = ""  # incomplete line buffer
    loop = asyncio.get_running_loop()

    class Handler(FileSystemEventHandler):
        def __init__(self):
            self.offset = 0

        def on_modified(self, fs_event):
            nonlocal buffer
            with lock:
                with open(path) as f:
                    f.seek(self.offset)
                    new_data = f.read()
                    self.offset = f.tell()
                data = buffer + new_data
                lines = data.split("\n")
                buffer = lines[-1]  # retain incomplete last line
                for line in lines[:-1]:
                    if line.strip():
                        try:
                            event = ZChatEvent.from_dict(json.loads(line))
                            loop.call_soon_threadsafe(queue.put_nowait, event)
                        except json.JSONDecodeError:
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
```

### 5.6 Storage Markers

Simple boolean per event (matches Protocol — no `handler_name` param):

```python
async def is_handled(self, event_id: str) -> bool:
    handled = self._read_handled()
    return event_id in handled

async def mark_handled(self, event_id: str) -> None:
    handled = self._read_handled()
    handled.add(event_id)
    self._write_handled(handled)
```

Storage: `config.handled_file` — JSON set of event IDs.

### 5.7 Config Loading

```python
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

### 5.8 Doctor

```python
async def doctor(self) -> DiagnosticReport:
    checks = {}
    messages = []

    # Check ZCHAT_IDENTITY
    checks["identity"] = self._identity is not None
    if not checks["identity"]:
        messages.append("ZCHAT_IDENTITY not set")

    # Check ZCHAT_HOME writable
    try:
        self._config.ensure_home()
        checks["home"] = True
    except OSError as e:
        checks["home"] = False
        messages.append(f"ZCHAT_HOME not writable: {e}")

    # Check rooms.json
    try:
        self._read_rooms()
        checks["rooms"] = True
    except Exception as e:
        checks["rooms"] = False
        messages.append(f"rooms.json error: {e}")

    return DiagnosticReport(checks=checks, messages=messages)
```

---

## 6. ScriptAcpBackend

Implements all 11 `AcpBackend` methods. Manages agent script subprocesses as daemons.

### 6.1 Constructor

```python
class ScriptAcpBackend:
    def __init__(self, config: ZChatConfig, identity: Identity, com: FileComBackend):
        self._config = config
        self._identity = identity
        self._com = com  # needed for event watcher to publish agent responses
        self._watchers: dict[str, asyncio.Task] = {}  # session_id → watcher task
        self._processes: dict[str, subprocess.Popen] = {}  # session_id → process
        config.ensure_sessions()
```

**Known coupling:** ScriptAcpBackend holds a reference to FileComBackend so the event watcher can publish events. Phase 1 should eliminate this by injecting a publish callback instead.

### 6.2 Spawn

```python
async def prepare_spawn(self, agent_name: str, template: str | None = None) -> SpawnPreview:
    # Load agent config to get model (= script path in Phase 0)
    config_info = await self._com.load_agent_config(agent_name)
    model = config_info.model or "scripts/echo-agent.sh"
    return SpawnPreview(
        agent_name=agent_name,
        template=template or config_info.template,
        model=model,
    )

async def confirm_spawn(self, preview: SpawnPreview) -> Identity:
    script_path = preview.model  # In Phase 0, model = script path
    # Start subprocess
    proc = subprocess.Popen(
        [script_path],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        text=True, bufsize=1,  # line-buffered
    )
    # Read init message
    init_line = proc.stdout.readline()
    init_data = json.loads(init_line)
    session_id = init_data.get("session_id", str(ULID()))

    # Agent identity: owner:agent_name@network
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

    # Start event watcher background task
    watcher = asyncio.create_task(
        self._event_watcher(session_id, proc, preview.agent_name, "#general")
    )
    self._watchers[session_id] = watcher

    return agent_identity

async def cancel_spawn(self, preview: SpawnPreview) -> None:
    pass
```

### 6.3 Event Watcher (per agent, background asyncio task)

```python
async def _event_watcher(self, session_id: str, proc: subprocess.Popen,
                          agent_name: str, room: str):
    """Watch room events, detect @mentions, inject into agent, publish responses."""
    async for event in self._com.subscribe(room):
        if event.type != "msg":
            continue
        mentions = event.content.get("mentions", []) if isinstance(event.content, dict) else []
        if agent_name not in mentions and f"@{agent_name}" not in str(event.content):
            continue

        # Construct enriched message (simplified [zchat] format)
        text = event.content.get("text", "") if isinstance(event.content, dict) else str(event.content)
        user_msg = json.dumps({
            "type": "user",
            "message": {"role": "user", "content": text}
        })

        # Inject to stdin
        try:
            proc.stdin.write(user_msg + "\n")
            proc.stdin.flush()
        except (BrokenPipeError, OSError):
            break

        # Read responses until "result" event
        while True:
            line = await asyncio.to_thread(proc.stdout.readline)
            if not line:
                break
            data = json.loads(line)
            if data["type"] == "assistant":
                content_blocks = data["message"].get("content", [])
                for block in content_blocks:
                    if block["type"] == "text":
                        agent_identity = f"{self._identity.user}:{agent_name}@{self._identity.network}"
                        response_event = ZChatEvent.create(
                            room=room, type="msg", from_=agent_identity,
                            content={"text": block["text"]},
                        )
                        await self._com.publish(response_event)
            elif data["type"] == "result":
                break
```

### 6.4 Session Management

```python
async def sessions(self) -> list[SessionInfo]:
    result = []
    for f in self._config.sessions_dir.glob("*.json"):
        meta = json.loads(f.read_text())
        pid = meta["pid"]
        alive = _pid_alive(pid)
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
    f = self._config.sessions_dir / f"{session_id}.json"
    if not f.exists():
        return
    meta = json.loads(f.read_text())
    pid = meta["pid"]
    # Cancel watcher
    if session_id in self._watchers:
        self._watchers[session_id].cancel()
        del self._watchers[session_id]
    # Terminate process (graceful then force)
    try:
        os.kill(pid, signal.SIGTERM)
        await asyncio.to_thread(os.waitpid, pid, 0)
    except (ProcessLookupError, ChildProcessError):
        pass
    if session_id in self._processes:
        del self._processes[session_id]
    f.unlink(missing_ok=True)

async def get_status(self, session_id: str) -> SessionInfo:
    info = await self.get_session(session_id)
    if info is None:
        return SessionInfo(session_id=session_id, agent=self._identity, status=SessionStatus.STOPPED)
    return info


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False
```

### 6.5 Attach/Detach (Simplified)

```python
async def attach(self, session_id: str) -> None:
    # Pause event watcher
    if session_id in self._watchers:
        self._watchers[session_id].cancel()
        del self._watchers[session_id]

async def detach(self, session_id: str) -> None:
    # Resume event watcher
    f = self._config.sessions_dir / f"{session_id}.json"
    if not f.exists() or session_id not in self._processes:
        return
    meta = json.loads(f.read_text())
    proc = self._processes[session_id]
    watcher = asyncio.create_task(
        self._event_watcher(session_id, proc, meta["agent_name"], meta.get("room", "#general"))
    )
    self._watchers[session_id] = watcher
```

### 6.6 inject_message / capture_output

```python
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
                    room="#general", type="msg", from_="agent",
                    content={"text": block.get("text", "")},
                )
                yield ZChatOperation(event=evt, source="agent")
        elif data["type"] == "result":
            break
```

---

## 7. Echo Agent Script

`scripts/echo-agent.sh` — bash script implementing CC headless JSONL protocol:

```bash
#!/usr/bin/env bash
# Echo agent — reads JSONL stdin, echoes back JSONL stdout
# Implements CC headless protocol: system/init → user/assistant/result loop

SESSION_ID="echo-$(date +%s)"

# Init message
echo "{\"type\":\"system\",\"subtype\":\"init\",\"session_id\":\"$SESSION_ID\",\"model\":\"echo\"}"

# Read-reply loop
while IFS= read -r line; do
    # Extract text content from JSONL user message
    text=$(echo "$line" | python3 -c "
import sys, json
try:
    msg = json.load(sys.stdin)
    content = msg.get('message', {}).get('content', '')
    print(content if isinstance(content, str) else json.dumps(content))
except: print('')
" 2>/dev/null)

    # Assistant response
    escaped=$(echo "$text" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read().strip()))")
    echo "{\"type\":\"assistant\",\"message\":{\"role\":\"assistant\",\"content\":[{\"type\":\"text\",\"text\":$escaped}]}}"

    # Result
    echo "{\"type\":\"result\",\"result\":$escaped,\"session_id\":\"$SESSION_ID\",\"cost_usd\":0,\"duration_ms\":50}"
done
```

---

## 8. `_get_cli()` Modification

```python
def _get_cli() -> ZChatCLI:
    identity_str = os.environ.get("ZCHAT_IDENTITY")
    if not identity_str:
        typer.echo("Error: ZCHAT_IDENTITY not set.\n"
                   "Run: export ZCHAT_IDENTITY=alice@onesyn", err=True)
        raise typer.Exit(1)

    config = ZChatConfig.resolve()
    config.ensure_home()
    config.ensure_runtime()

    identity = Identity.parse(identity_str)
    com = FileComBackend(config=config, identity=identity)
    acp = ScriptAcpBackend(config=config, identity=identity, com=com)
    cli = ZChatCLI(com=com, acp=acp)
    return cli
```

---

## 9. Dependency Changes

**zchat-com/pyproject.toml:** add `watchdog>=4.0`

**zchat-acp/pyproject.toml:** no new deps (subprocess is stdlib)

---

## 10. File Structure

```
packages/zchat-com/src/zchat_com/
├── __init__.py
├── mock.py              ← retained for unit tests only
└── file.py              ← NEW: FileComBackend

packages/zchat-acp/src/zchat_acp/
├── __init__.py
├── mock.py              ← retained for unit tests only
└── script.py            ← NEW: ScriptAcpBackend

packages/zchat-protocol/src/zchat_protocol/
└── config.py            ← MODIFY: add rooms_file + handled_file properties

scripts/
└── echo-agent.sh        ← NEW: built-in test agent

tests/
├── test_com/
│   ├── __init__.py
│   └── test_file_backend.py      ← NEW
├── test_acp/
│   ├── __init__.py
│   └── test_script_backend.py    ← NEW
└── test_e2e/
    ├── test_smoke.py              ← MODIFY: add ZCHAT_IDENTITY + ZCHAT_HOME env vars
    └── test_multiuser.py          ← NEW: cross-process E2E
```

---

## 11. Testing Strategy

### 11.1 FileComBackend Unit Tests (`test_com/test_file_backend.py`)

All tests use `tmp_path` + `monkeypatch.setenv("ZCHAT_HOME", ...)` + `monkeypatch.setenv("ZCHAT_IDENTITY", ...)`:

- `test_get_identity_from_env` — returns parsed $ZCHAT_IDENTITY
- `test_missing_identity_crashes` — error when env var not set
- `test_publish_appends_to_jsonl` — publish event, verify file content
- `test_query_events_reads_last_n` — seed file, query last 5
- `test_query_events_returns_all_when_no_last` — last=None returns everything
- `test_subscribe_yields_new_events` — publish after subscribe starts, verify yield
- `test_subscribe_handles_partial_lines` — seed corrupted line, verify skip
- `test_room_create_writes_rooms_json` — create room, verify file
- `test_room_invite_adds_member_and_publishes_join` — invite, check rooms.json + events
- `test_rooms_lists_from_file` — verify rooms() reads file
- `test_members_reads_from_file` — verify members() for specific room
- `test_get_network_returns_local` — returns NetworkInfo with name="local"
- `test_get_peers_from_rooms` — peers are all unique members across rooms
- `test_doctor_checks_all` — verify all diagnostic checks
- `test_concurrent_publish` — two tasks publish simultaneously, no corruption
- `test_bootstrap_creates_general` — first access creates #general
- `test_is_handled_mark_handled` — round-trip handled markers
- `test_load_agent_config_from_toml` — reads .zchat/agents/*.toml
- `test_load_template_config_from_toml` — reads .zchat/templates/*.toml

### 11.2 ScriptAcpBackend Unit Tests (`test_acp/test_script_backend.py`)

- `test_spawn_starts_process` — confirm_spawn starts echo-agent, PID file exists
- `test_spawn_reads_init_message` — verify session_id from init JSONL
- `test_spawn_returns_agent_identity` — confirm_spawn returns Identity with label
- `test_kill_terminates_process` — kill, verify PID gone + session file deleted
- `test_sessions_lists_active` — spawn 2 agents, sessions() returns 2
- `test_sessions_detects_dead` — spawn, manually kill PID, sessions() marks STOPPED
- `test_get_session_returns_none_for_missing` — unknown session_id returns None
- `test_inject_and_capture` — inject message, capture echo reply
- `test_event_watcher_detects_mention` — write @agent event to file, verify agent responds
- `test_attach_pauses_watcher` — attach, send @mention, verify no auto-response
- `test_detach_resumes_watcher` — detach after attach, verify auto-response resumes

### 11.3 Multi-User E2E (`test_e2e/test_multiuser.py`)

Subprocess-based tests sharing a common `$ZCHAT_HOME` in `/tmp`:

- `test_alice_sends_bob_sees` — alice sends to #general, bob query_events sees it
- `test_spawn_and_mention` — alice spawns echo-agent, sends @echo-agent "hello", query shows echo reply
- `test_two_users_in_room` — alice creates room, invites bob, both see messages
- `test_session_kill` — spawn then kill, verify session gone

### 11.4 Existing Test Modifications

- `test_cli/` — **unchanged**, still uses MockComBackend/MockAcpBackend via conftest.py
- `test_e2e/test_smoke.py` — **modified**: each `run_zchat()` call sets `ZCHAT_IDENTITY` and `ZCHAT_HOME` env vars pointing to a per-test tmp dir

---

## 12. Multi-User E2E Demo

```bash
export ZCHAT_HOME=/tmp/zchat-demo

# Terminal 1: Alice
export ZCHAT_IDENTITY=alice@onesyn
zchat rooms                                    # → #general
zchat spawn echo-agent --yes                   # → starts scripts/echo-agent.sh
zchat send '@echo-agent' '做一个 Q3 PPT'       # → event in store

# Terminal 2: Bob
export ZCHAT_IDENTITY=bob@onesyn
zchat watch '#general'                         # → sees alice's message + echo reply
zchat send '#general' '配色要改'               # → alice's watch sees this

# Terminal 1: cleanup
zchat session kill <session_id>                # → SIGTERM + cleanup
```
