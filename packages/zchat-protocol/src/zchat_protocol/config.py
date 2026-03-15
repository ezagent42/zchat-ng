"""ZChat path configuration.

All paths resolved from environment variables with sensible defaults.
Directories are created on first access via ensure_*() methods.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _default_home() -> Path:
    return Path(os.environ.get("ZCHAT_HOME", Path.home() / ".zchat"))


def _default_runtime() -> Path:
    uid = os.getuid()
    return Path(os.environ.get("ZCHAT_RUNTIME", f"/tmp/zchat-{uid}"))


def _find_project_root() -> Path | None:
    """Walk up from cwd to find a directory containing .zchat/"""
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        candidate = parent / ".zchat"
        if candidate.is_dir():
            return candidate
    return None


@dataclass(frozen=True)
class ZChatConfig:
    """Resolved ZChat paths. Immutable after creation."""

    home: Path
    project: Path | None
    runtime: Path

    @classmethod
    def resolve(cls) -> ZChatConfig:
        """Resolve config from environment + filesystem."""
        home = _default_home()

        project_env = os.environ.get("ZCHAT_PROJECT")
        if project_env:
            project = Path(project_env)
        else:
            project = _find_project_root()

        runtime = _default_runtime()

        return cls(home=home, project=project, runtime=runtime)

    # ── Home paths ──

    @property
    def identity_file(self) -> Path:
        return self.home / "identity.toml"

    @property
    def network_file(self) -> Path:
        return self.home / "network.toml"

    @property
    def store_dir(self) -> Path:
        return self.home / "store"

    @property
    def workspaces_dir(self) -> Path:
        return self.home / "workspaces"

    # ── Project paths ──

    @property
    def templates_dir(self) -> Path | None:
        return self.project / "templates" if self.project else None

    @property
    def agents_dir(self) -> Path | None:
        return self.project / "agents" if self.project else None

    # ── Runtime paths ──

    @property
    def sessions_dir(self) -> Path:
        return self.runtime / "sessions"

    @property
    def locks_dir(self) -> Path:
        return self.runtime / "locks"

    @property
    def pid_file(self) -> Path:
        return self.runtime / "pid"

    # ── Room store paths ──

    def room_store_dir(self, room: str) -> Path:
        """Path to a room's event store directory."""
        safe_name = room.lstrip("#").replace("/", "_")
        return self.store_dir / safe_name

    def room_events_file(self, room: str) -> Path:
        """Path to a room's events JSONL file."""
        return self.room_store_dir(room) / "events.jsonl"

    # ── Directory creation ──

    def ensure_home(self) -> Path:
        self.home.mkdir(parents=True, exist_ok=True)
        return self.home

    def ensure_store(self) -> Path:
        self.store_dir.mkdir(parents=True, exist_ok=True)
        return self.store_dir

    def ensure_room_store(self, room: str) -> Path:
        d = self.room_store_dir(room)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def ensure_runtime(self) -> Path:
        self.runtime.mkdir(parents=True, exist_ok=True)
        return self.runtime

    def ensure_sessions(self) -> Path:
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        return self.sessions_dir
