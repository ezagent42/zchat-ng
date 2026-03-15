"""ScriptAcpBackend — daemon agent scripts with CC headless JSONL protocol."""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
from pathlib import Path
from typing import AsyncIterator

from zchat_protocol import Identity, OperationType, ZChatEvent
from zchat_protocol.config import ZChatConfig

from zchat_cli.types import (
    SessionInfo,
    SessionStatus,
    SpawnPreview,
    ZChatOperation,
)

# Import at runtime to avoid circular deps; type only for annotation
from zchat_com.file import FileComBackend


class ScriptAcpBackend:
    """AcpBackend that launches shell scripts speaking CC headless JSONL."""

    def __init__(
        self,
        config: ZChatConfig,
        identity: Identity,
        com: FileComBackend,
    ) -> None:
        self._config = config
        self._identity = identity
        self._com = com
        # session_id -> running state
        self._processes: dict[str, subprocess.Popen[str]] = {}
        self._sessions: dict[str, SessionInfo] = {}
        self._watcher_tasks: dict[str, asyncio.Task[None]] = {}
        self._watcher_ready: dict[str, asyncio.Event] = {}
        self._subscriptions: dict[str, object] = {}  # session_id -> _FileSubscription
        config.ensure_sessions()

    # ── Spawn lifecycle ──

    async def prepare_spawn(
        self, agent_name: str, template: str | None = None
    ) -> SpawnPreview:
        config_info = await self._com.load_agent_config(agent_name)
        script = config_info.model or "scripts/echo-agent.sh"
        return SpawnPreview(
            agent_name=agent_name,
            template=template or "",
            model=script,
            estimated_cost=0.0,
        )

    async def confirm_spawn(self, preview: SpawnPreview) -> Identity:
        script = preview.model or "scripts/echo-agent.sh"
        proc = subprocess.Popen(
            [script],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        # Read init JSONL from stdout
        init_line = await asyncio.to_thread(proc.stdout.readline)
        init_data = json.loads(init_line.strip())
        base_session_id = init_data.get("session_id", f"session-{proc.pid}")

        # Disambiguate with PID to avoid collisions from date +%s
        session_id = f"{base_session_id}-{proc.pid}"

        agent_identity = Identity(
            user=self._identity.user,
            label=preview.agent_name,
            network=self._identity.network,
        )

        # Write session JSON
        session_file = self._config.sessions_dir / f"{session_id}.json"
        session_meta = {
            "session_id": session_id,
            "pid": proc.pid,
            "agent": str(agent_identity),
            "script": script,
        }
        session_file.write_text(json.dumps(session_meta))

        session_info = SessionInfo(
            session_id=session_id,
            agent=agent_identity,
            status=SessionStatus.RUNNING,
        )
        self._processes[session_id] = proc
        self._sessions[session_id] = session_info

        # Start background event watcher with a ready signal
        ready = asyncio.Event()
        self._watcher_ready[session_id] = ready
        task = asyncio.create_task(self._event_watcher(session_id, ready))
        self._watcher_tasks[session_id] = task
        # Wait for the watcher to be subscribed before returning
        await ready.wait()

        return agent_identity

    async def cancel_spawn(self, preview: SpawnPreview) -> None:
        pass

    # ── Session queries ──

    async def sessions(self) -> list[SessionInfo]:
        result: list[SessionInfo] = []
        sessions_dir = self._config.sessions_dir
        if not sessions_dir.exists():
            return result
        for f in sessions_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            sid = data["session_id"]
            pid = data.get("pid")
            alive = _pid_alive(pid) if pid else False
            agent = Identity.parse(data["agent"])
            status = SessionStatus.RUNNING if alive else SessionStatus.STOPPED
            result.append(
                SessionInfo(session_id=sid, agent=agent, status=status)
            )
        return result

    async def get_session(self, session_id: str) -> SessionInfo | None:
        session_file = self._config.sessions_dir / f"{session_id}.json"
        if not session_file.exists():
            return None
        try:
            data = json.loads(session_file.read_text())
        except (json.JSONDecodeError, OSError):
            return None
        pid = data.get("pid")
        alive = _pid_alive(pid) if pid else False
        agent = Identity.parse(data["agent"])
        status = SessionStatus.RUNNING if alive else SessionStatus.STOPPED
        return SessionInfo(session_id=session_id, agent=agent, status=status)

    async def kill_session(self, session_id: str) -> None:
        # Cancel watcher task and clean up subscription
        task = self._watcher_tasks.pop(session_id, None)
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._stop_subscription(session_id)

        # Terminate process
        proc = self._processes.pop(session_id, None)
        if proc is not None:
            try:
                proc.terminate()
                try:
                    await asyncio.to_thread(proc.wait, timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    await asyncio.to_thread(proc.wait, timeout=3)
            except OSError:
                pass
        else:
            # Try to kill by PID from session file
            session_file = self._config.sessions_dir / f"{session_id}.json"
            if session_file.exists():
                try:
                    data = json.loads(session_file.read_text())
                    pid = data.get("pid")
                    if pid and _pid_alive(pid):
                        os.kill(pid, signal.SIGTERM)
                except (json.JSONDecodeError, OSError):
                    pass

        # Remove session file
        session_file = self._config.sessions_dir / f"{session_id}.json"
        if session_file.exists():
            session_file.unlink()

        self._sessions.pop(session_id, None)

    # ── Attach/Detach ──

    def _stop_subscription(self, session_id: str) -> None:
        """Stop and remove a subscription's watchdog observer."""
        sub = self._subscriptions.pop(session_id, None)
        if sub is not None and hasattr(sub, '_observer') and sub._observer is not None:
            try:
                sub._observer.stop()
                sub._observer.join(timeout=2)
            except Exception:
                pass
            sub._observer = None

    async def attach(self, session_id: str) -> None:
        task = self._watcher_tasks.pop(session_id, None)
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._stop_subscription(session_id)

    async def detach(self, session_id: str) -> None:
        # Restart watcher if process still exists
        if session_id in self._processes:
            ready = asyncio.Event()
            self._watcher_ready[session_id] = ready
            task = asyncio.create_task(self._event_watcher(session_id, ready))
            self._watcher_tasks[session_id] = task
            await ready.wait()

    # ── Message I/O ──

    async def inject_message(self, session_id: str, content: str) -> None:
        proc = self._processes.get(session_id)
        if proc is None or proc.stdin is None:
            return
        jsonl_msg = json.dumps({
            "type": "user",
            "message": {"role": "user", "content": content},
        })
        await asyncio.to_thread(self._write_stdin, proc, jsonl_msg + "\n")

    def capture_output(self, session_id: str) -> AsyncIterator[ZChatOperation]:
        return _CaptureIterator(self, session_id)

    async def get_status(self, session_id: str) -> SessionInfo:
        session = await self.get_session(session_id)
        if session is not None:
            return session
        return SessionInfo(
            session_id=session_id,
            agent=Identity(user="unknown", network=self._identity.network),
            status=SessionStatus.STOPPED,
        )

    # ── Private helpers ──

    @staticmethod
    def _write_stdin(proc: subprocess.Popen[str], data: str) -> None:
        if proc.stdin is not None:
            proc.stdin.write(data)
            proc.stdin.flush()

    async def _event_watcher(
        self, session_id: str, ready: asyncio.Event | None = None
    ) -> None:
        """Watch room events for @mentions and relay to the agent subprocess."""
        proc = self._processes.get(session_id)
        session_info = self._sessions.get(session_id)
        if proc is None or session_info is None:
            if ready is not None:
                ready.set()
            return

        agent_name = session_info.agent.label or ""
        # Find which room to watch — default to #general
        rooms = await self._com.rooms()
        room_name = rooms[0].name if rooms else "#general"

        subscription = self._com.subscribe(room_name)
        self._subscriptions[session_id] = subscription
        # Prime the subscription so watchdog is running before we signal ready
        # The first __anext__ call triggers _start() which sets up watchdog
        if hasattr(subscription, '_start'):
            await subscription._start()
        if ready is not None:
            ready.set()

        async for event in subscription:
            if event.type != OperationType.MSG:
                continue
            # Check for @mention of the agent
            content_str = (
                event.content
                if isinstance(event.content, str)
                else json.dumps(event.content)
            )
            if f"@{agent_name}" not in content_str:
                continue
            # Don't respond to own messages
            if event.from_ == str(session_info.agent):
                continue

            # Write to subprocess stdin
            jsonl_msg = json.dumps({
                "type": "user",
                "message": {"role": "user", "content": content_str},
            })
            try:
                await asyncio.to_thread(
                    self._write_stdin, proc, jsonl_msg + "\n"
                )
            except OSError:
                break

            # Read responses from stdout
            while True:
                try:
                    line = await asyncio.to_thread(proc.stdout.readline)
                except OSError:
                    return
                if not line:
                    return
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                msg_type = data.get("type", "")

                if msg_type == "assistant":
                    # Extract text from assistant message
                    msg = data.get("message", {})
                    msg_content = msg.get("content", "")
                    if isinstance(msg_content, list):
                        # Extract text blocks
                        texts = [
                            b.get("text", "")
                            for b in msg_content
                            if b.get("type") == "text"
                        ]
                        text = " ".join(texts)
                    else:
                        text = str(msg_content)

                    # Publish reply to room
                    reply_event = ZChatEvent.create(
                        room=room_name,
                        type=OperationType.MSG,
                        from_=str(session_info.agent),
                        content=text,
                        content_type="text/plain",
                    )
                    await self._com.publish(reply_event)

                if msg_type == "result":
                    break


class _CaptureIterator:
    """Async iterator that reads JSONL output from a subprocess."""

    def __init__(self, backend: ScriptAcpBackend, session_id: str) -> None:
        self._backend = backend
        self._session_id = session_id
        self._done = False

    def __aiter__(self) -> AsyncIterator[ZChatOperation]:
        return self

    async def __anext__(self) -> ZChatOperation:
        if self._done:
            raise StopAsyncIteration

        proc = self._backend._processes.get(self._session_id)
        if proc is None or proc.stdout is None:
            raise StopAsyncIteration

        while True:
            line = await asyncio.to_thread(proc.stdout.readline)
            if not line:
                raise StopAsyncIteration
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg_type = data.get("type", "")
            if msg_type == "result":
                self._done = True

            # Build event from the JSONL data
            msg = data.get("message", {})
            msg_content = msg.get("content", "")
            if isinstance(msg_content, list):
                texts = [
                    b.get("text", "")
                    for b in msg_content
                    if b.get("type") == "text"
                ]
                text = " ".join(texts)
            else:
                text = str(msg_content) if msg_content else data.get("result", "")

            session_info = self._backend._sessions.get(self._session_id)
            from_str = (
                str(session_info.agent) if session_info else "unknown@local"
            )

            event = ZChatEvent.create(
                room="#general",
                type=OperationType.MSG,
                from_=from_str,
                content=text,
                content_type="text/plain",
            )
            return ZChatOperation(event=event, source="agent")


def _pid_alive(pid: int) -> bool:
    """Check if a process with the given PID is alive."""
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False
