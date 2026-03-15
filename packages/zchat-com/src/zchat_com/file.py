"""FileComBackend — file-based ComBackend for local ZChat communication."""
from __future__ import annotations

import asyncio
import fcntl
import json
import threading
from pathlib import Path
from typing import Any, AsyncIterator

from watchdog.events import FileModifiedEvent, FileSystemEventHandler
from watchdog.observers import Observer

from zchat_protocol import Identity, OperationType, SpawnConfig, ZChatEvent
from zchat_protocol.config import ZChatConfig
from zchat_protocol.content_types.system_event import SystemEvent

from zchat_cli.types import (
    AgentConfigInfo,
    DiagnosticReport,
    NetworkInfo,
    Room,
    TemplateInfo,
)


class FileComBackend:
    """File-based implementation of ComBackend protocol.

    Uses JSON files for room registry and JSONL append-only logs for events.
    File locking via fcntl ensures safe concurrent access.
    """

    def __init__(self, config: ZChatConfig, identity: Identity) -> None:
        self._config = config
        self._identity = identity
        config.ensure_home()
        config.ensure_store()

    # ── Identity methods ──

    async def get_identity(self) -> Identity:
        return self._identity

    async def get_network(self) -> NetworkInfo:
        rooms_data = self._read_rooms()
        all_members: set[str] = set()
        for room_data in rooms_data:
            for m in room_data.get("members", []):
                all_members.add(m)
        return NetworkInfo(
            name="local",
            peer_count=len(all_members),
            online=True,
        )

    async def get_peers(self) -> list[Identity]:
        rooms_data = self._read_rooms()
        all_members: set[str] = set()
        for room_data in rooms_data:
            for m in room_data.get("members", []):
                all_members.add(m)
        return [Identity.parse(m) for m in sorted(all_members)]

    async def setup_identity(self, user: str, network: str) -> Identity:
        return self._identity

    # ── Room management ──

    async def room_create(self, name: str, topic: str = "") -> Room:
        rooms_data = self._read_rooms()
        me = str(self._identity)
        new_room = {
            "name": name,
            "topic": topic,
            "members": [me],
        }
        rooms_data.append(new_room)
        self._write_rooms(rooms_data)
        self._config.ensure_room_store(name)
        return Room(name=name, topic=topic, member_count=1)

    async def room_invite(self, room: str, identity: Identity) -> None:
        rooms_data = self._read_rooms()
        id_str = str(identity)
        for rd in rooms_data:
            if rd["name"] == room:
                if id_str not in rd["members"]:
                    rd["members"].append(id_str)
                break
        self._write_rooms(rooms_data)
        # Publish a JOIN system event
        join_event = ZChatEvent.create(
            room=room,
            type=OperationType.JOIN,
            from_=str(self._identity),
            content={"event_type": "join", "subject": str(identity)},
            content_type="application/vnd.zchat.system-event",
        )
        await self.publish(join_event)

    async def room_leave(self, room: str) -> None:
        rooms_data = self._read_rooms()
        me = str(self._identity)
        for rd in rooms_data:
            if rd["name"] == room:
                if me in rd["members"]:
                    rd["members"].remove(me)
                break
        self._write_rooms(rooms_data)

    async def rooms(self) -> list[Room]:
        rooms_data = self._read_rooms()
        return [
            Room(
                name=rd["name"],
                topic=rd.get("topic", ""),
                member_count=len(rd.get("members", [])),
            )
            for rd in rooms_data
        ]

    async def members(self, room: str) -> list[Identity]:
        rooms_data = self._read_rooms()
        for rd in rooms_data:
            if rd["name"] == room:
                return [Identity.parse(m) for m in rd.get("members", [])]
        return []

    # ── Events ──

    async def publish(self, event: ZChatEvent) -> None:
        self._config.ensure_room_store(event.room)
        events_file = self._config.room_events_file(event.room)
        line = json.dumps(event.to_dict()) + "\n"
        with open(events_file, "a") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                f.write(line)
                f.flush()
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def subscribe(self, room: str) -> AsyncIterator[ZChatEvent]:
        """Return an async iterator that yields new events via watchdog."""
        return _FileSubscription(self._config, room)

    async def query_events(
        self, room: str, *, last: int | None = None
    ) -> list[ZChatEvent]:
        events_file = self._config.room_events_file(room)
        if not events_file.exists():
            return []
        events: list[ZChatEvent] = []
        with open(events_file, "r") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            try:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                        events.append(ZChatEvent.from_dict(d))
                    except (json.JSONDecodeError, KeyError, ValueError):
                        continue
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        if last is not None:
            return events[-last:]
        return events

    async def get_event(self, event_id: str) -> ZChatEvent | None:
        store_dir = self._config.store_dir
        if not store_dir.exists():
            return None
        for room_dir in store_dir.iterdir():
            if not room_dir.is_dir():
                continue
            events_file = room_dir / "events.jsonl"
            if not events_file.exists():
                continue
            with open(events_file, "r") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                try:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            d = json.loads(line)
                            if d.get("id") == event_id:
                                return ZChatEvent.from_dict(d)
                        except (json.JSONDecodeError, KeyError, ValueError):
                            continue
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        return None

    # ── Storage markers ──

    async def is_handled(self, event_id: str) -> bool:
        handled = self._read_handled()
        return event_id in handled

    async def mark_handled(self, event_id: str) -> None:
        handled = self._read_handled()
        handled.add(event_id)
        self._write_handled(handled)

    # ── Doctor ──

    async def doctor(self) -> DiagnosticReport:
        checks: dict[str, bool] = {}
        messages: list[str] = []

        # Check identity is set
        checks["identity_set"] = self._identity is not None
        if checks["identity_set"]:
            messages.append(f"Identity: {self._identity}")
        else:
            messages.append("Identity not set")

        # Check ZCHAT_HOME writable
        try:
            test_file = self._config.home / ".doctor_probe"
            test_file.write_text("ok")
            test_file.unlink()
            checks["home_writable"] = True
            messages.append(f"Home writable: {self._config.home}")
        except OSError:
            checks["home_writable"] = False
            messages.append(f"Home NOT writable: {self._config.home}")

        # Check rooms.json readable
        try:
            self._read_rooms()
            checks["rooms_readable"] = True
            messages.append("rooms.json readable")
        except OSError:
            checks["rooms_readable"] = False
            messages.append("rooms.json NOT readable")

        return DiagnosticReport(checks=checks, messages=messages)

    # ── Config loading ──

    async def load_agent_config(self, name: str) -> AgentConfigInfo:
        agents_dir = self._config.agents_dir
        if agents_dir is None:
            return AgentConfigInfo(name=name)
        toml_path = agents_dir / f"{name}.toml"
        if not toml_path.exists():
            return AgentConfigInfo(name=name)
        sc = SpawnConfig.from_toml_file(toml_path)
        return AgentConfigInfo(
            name=sc.name or name,
            template="",
            model=sc.model or "",
        )

    async def load_template_config(self, name: str) -> TemplateInfo:
        templates_dir = self._config.templates_dir
        if templates_dir is None:
            return TemplateInfo(name=name)
        toml_path = templates_dir / f"{name}.toml"
        if not toml_path.exists():
            return TemplateInfo(name=name)
        sc = SpawnConfig.from_toml_file(toml_path)
        return TemplateInfo(
            name=sc.name or name,
            description=sc.system_prompt or "",
            path=str(toml_path),
        )

    # ── Private helpers ──

    def _read_rooms(self) -> list[dict[str, Any]]:
        """Read rooms.json with shared lock, bootstrapping if needed."""
        rooms_file = self._config.rooms_file
        if not rooms_file.exists():
            self._bootstrap_rooms()
        with open(rooms_file, "r") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            try:
                return json.load(f)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def _write_rooms(self, data: list[dict[str, Any]]) -> None:
        """Write rooms.json with exclusive lock."""
        rooms_file = self._config.rooms_file
        with open(rooms_file, "w") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                json.dump(data, f, indent=2)
                f.flush()
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def _bootstrap_rooms(self) -> None:
        """Create initial rooms.json with #general room."""
        me = str(self._identity)
        data = [
            {
                "name": "#general",
                "topic": "General chat",
                "members": [me],
            }
        ]
        self._write_rooms(data)
        self._config.ensure_room_store("#general")

    def _read_handled(self) -> set[str]:
        """Read handled event IDs from .handled.json."""
        handled_file = self._config.handled_file
        if not handled_file.exists():
            return set()
        with open(handled_file, "r") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            try:
                data = json.load(f)
                return set(data)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def _write_handled(self, handled: set[str]) -> None:
        """Write handled event IDs to .handled.json."""
        handled_file = self._config.handled_file
        with open(handled_file, "w") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                json.dump(sorted(handled), f)
                f.flush()
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)


class _FileSubscription:
    """AsyncIterator that watches a room's events.jsonl for new lines."""

    def __init__(self, config: ZChatConfig, room: str) -> None:
        self._config = config
        self._room = room
        self._queue: asyncio.Queue[ZChatEvent] = asyncio.Queue()
        self._observer: Observer | None = None
        self._lock = threading.Lock()
        self._offset: int = 0
        self._buffer: str = ""
        self._loop: asyncio.AbstractEventLoop | None = None

    def __aiter__(self) -> AsyncIterator[ZChatEvent]:
        return self

    async def __anext__(self) -> ZChatEvent:
        if self._observer is None:
            await self._start()
        return await self._queue.get()

    async def _start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._config.ensure_room_store(self._room)
        events_file = self._config.room_events_file(self._room)

        # Start observer BEFORE recording offset to avoid TOCTOU race
        handler = _EventFileHandler(self)
        self._observer = Observer()
        watch_dir = str(events_file.parent)
        self._observer.schedule(handler, watch_dir, recursive=False)
        self._observer.daemon = True
        self._observer.start()

        # Record current offset
        with self._lock:
            if events_file.exists():
                self._offset = events_file.stat().st_size
            else:
                self._offset = 0

    def _on_file_modified(self) -> None:
        """Called from watchdog thread on file modification."""
        events_file = self._config.room_events_file(self._room)
        if not events_file.exists():
            return

        with self._lock:
            try:
                with open(events_file, "r") as f:
                    f.seek(self._offset)
                    new_data = f.read()
                    self._offset = f.tell()
            except OSError:
                return

            if not new_data:
                return

            # Buffer incomplete last lines
            self._buffer += new_data
            lines = self._buffer.split("\n")
            # If buffer doesn't end with newline, last element is incomplete
            if not self._buffer.endswith("\n"):
                self._buffer = lines[-1]
                lines = lines[:-1]
            else:
                self._buffer = ""

        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                event = ZChatEvent.from_dict(d)
                if self._loop is not None:
                    self._loop.call_soon_threadsafe(self._queue.put_nowait, event)
            except (json.JSONDecodeError, KeyError, ValueError):
                # Skip corrupted lines
                continue


class _EventFileHandler(FileSystemEventHandler):
    """Watchdog handler that delegates to _FileSubscription."""

    def __init__(self, subscription: _FileSubscription) -> None:
        self._subscription = subscription

    def on_modified(self, event: FileModifiedEvent | Any) -> None:
        if hasattr(event, "is_directory") and event.is_directory:
            return
        events_filename = self._subscription._config.room_events_file(
            self._subscription._room
        ).name
        src = getattr(event, "src_path", "")
        if src.endswith(events_filename):
            self._subscription._on_file_modified()
