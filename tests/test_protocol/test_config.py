"""Tests for zchat_protocol.config — path resolution and directory creation."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from zchat_protocol.config import ZChatConfig, _find_project_root


# ── Env-var resolution ──


def test_resolve_reads_zchat_home(tmp_path, monkeypatch):
    """ZCHAT_HOME env var sets home path."""
    home = tmp_path / "home"
    monkeypatch.setenv("ZCHAT_HOME", str(home))
    monkeypatch.setenv("ZCHAT_RUNTIME", str(tmp_path / "rt"))
    monkeypatch.delenv("ZCHAT_PROJECT", raising=False)
    cfg = ZChatConfig.resolve()
    assert cfg.home == home


def test_resolve_reads_zchat_runtime(tmp_path, monkeypatch):
    """ZCHAT_RUNTIME env var sets runtime path."""
    rt = tmp_path / "runtime"
    monkeypatch.setenv("ZCHAT_HOME", str(tmp_path / "h"))
    monkeypatch.setenv("ZCHAT_RUNTIME", str(rt))
    monkeypatch.delenv("ZCHAT_PROJECT", raising=False)
    cfg = ZChatConfig.resolve()
    assert cfg.runtime == rt


def test_resolve_default_home_when_unset(tmp_path, monkeypatch):
    """Without ZCHAT_HOME, defaults to ~/.zchat."""
    monkeypatch.delenv("ZCHAT_HOME", raising=False)
    monkeypatch.delenv("ZCHAT_PROJECT", raising=False)
    monkeypatch.setenv("ZCHAT_RUNTIME", str(tmp_path / "rt"))
    monkeypatch.setenv("HOME", str(tmp_path))
    cfg = ZChatConfig.resolve()
    assert cfg.home == tmp_path / ".zchat"


def test_resolve_default_runtime_when_unset(tmp_path, monkeypatch):
    """Without ZCHAT_RUNTIME, defaults to /tmp/zchat-{uid}."""
    monkeypatch.delenv("ZCHAT_RUNTIME", raising=False)
    monkeypatch.delenv("ZCHAT_PROJECT", raising=False)
    monkeypatch.setenv("ZCHAT_HOME", str(tmp_path / "h"))
    cfg = ZChatConfig.resolve()
    uid = os.getuid()
    assert cfg.runtime == Path(f"/tmp/zchat-{uid}")


# ── Home paths ──


def test_identity_file(tmp_path):
    cfg = ZChatConfig(home=tmp_path, project=None, runtime=tmp_path / "rt")
    assert cfg.identity_file == tmp_path / "identity.toml"


def test_network_file(tmp_path):
    cfg = ZChatConfig(home=tmp_path, project=None, runtime=tmp_path / "rt")
    assert cfg.network_file == tmp_path / "network.toml"


def test_store_dir(tmp_path):
    cfg = ZChatConfig(home=tmp_path, project=None, runtime=tmp_path / "rt")
    assert cfg.store_dir == tmp_path / "store"


def test_workspaces_dir(tmp_path):
    cfg = ZChatConfig(home=tmp_path, project=None, runtime=tmp_path / "rt")
    assert cfg.workspaces_dir == tmp_path / "workspaces"


# ── Room store paths ──


def test_room_store_dir_strips_hash(tmp_path):
    """room_store_dir('#general') strips the # prefix."""
    cfg = ZChatConfig(home=tmp_path, project=None, runtime=tmp_path / "rt")
    assert cfg.room_store_dir("#general") == tmp_path / "store" / "general"


def test_room_store_dir_replaces_slash(tmp_path):
    """room_store_dir('team/design') replaces / with _."""
    cfg = ZChatConfig(home=tmp_path, project=None, runtime=tmp_path / "rt")
    assert cfg.room_store_dir("team/design") == tmp_path / "store" / "team_design"


def test_room_events_file(tmp_path):
    cfg = ZChatConfig(home=tmp_path, project=None, runtime=tmp_path / "rt")
    expected = tmp_path / "store" / "general" / "events.jsonl"
    assert cfg.room_events_file("#general") == expected


# ── Project paths ──


def test_project_env_override(tmp_path, monkeypatch):
    """ZCHAT_PROJECT env var overrides filesystem detection."""
    proj = tmp_path / "myproject" / ".zchat"
    proj.mkdir(parents=True)
    monkeypatch.setenv("ZCHAT_HOME", str(tmp_path / "h"))
    monkeypatch.setenv("ZCHAT_PROJECT", str(proj))
    monkeypatch.setenv("ZCHAT_RUNTIME", str(tmp_path / "rt"))
    cfg = ZChatConfig.resolve()
    assert cfg.project == proj


def test_templates_dir_with_project(tmp_path):
    proj = tmp_path / ".zchat"
    cfg = ZChatConfig(home=tmp_path / "h", project=proj, runtime=tmp_path / "rt")
    assert cfg.templates_dir == proj / "templates"


def test_agents_dir_with_project(tmp_path):
    proj = tmp_path / ".zchat"
    cfg = ZChatConfig(home=tmp_path / "h", project=proj, runtime=tmp_path / "rt")
    assert cfg.agents_dir == proj / "agents"


def test_templates_dir_none_without_project(tmp_path):
    cfg = ZChatConfig(home=tmp_path, project=None, runtime=tmp_path / "rt")
    assert cfg.templates_dir is None


def test_agents_dir_none_without_project(tmp_path):
    cfg = ZChatConfig(home=tmp_path, project=None, runtime=tmp_path / "rt")
    assert cfg.agents_dir is None


# ── Runtime paths ──


def test_sessions_dir(tmp_path):
    cfg = ZChatConfig(home=tmp_path, project=None, runtime=tmp_path / "rt")
    assert cfg.sessions_dir == tmp_path / "rt" / "sessions"


def test_locks_dir(tmp_path):
    cfg = ZChatConfig(home=tmp_path, project=None, runtime=tmp_path / "rt")
    assert cfg.locks_dir == tmp_path / "rt" / "locks"


def test_pid_file(tmp_path):
    cfg = ZChatConfig(home=tmp_path, project=None, runtime=tmp_path / "rt")
    assert cfg.pid_file == tmp_path / "rt" / "pid"


# ── Directory creation (ensure_*) ──


def test_ensure_home_creates_dir(tmp_path):
    home = tmp_path / "new_home"
    cfg = ZChatConfig(home=home, project=None, runtime=tmp_path / "rt")
    result = cfg.ensure_home()
    assert result == home
    assert home.is_dir()


def test_ensure_store_creates_dir(tmp_path):
    home = tmp_path / "h"
    cfg = ZChatConfig(home=home, project=None, runtime=tmp_path / "rt")
    result = cfg.ensure_store()
    assert result == home / "store"
    assert (home / "store").is_dir()


def test_ensure_room_store_creates_nested_dirs(tmp_path):
    home = tmp_path / "h"
    cfg = ZChatConfig(home=home, project=None, runtime=tmp_path / "rt")
    result = cfg.ensure_room_store("#workshop")
    expected = home / "store" / "workshop"
    assert result == expected
    assert expected.is_dir()


def test_ensure_runtime_creates_dir(tmp_path):
    rt = tmp_path / "new_runtime"
    cfg = ZChatConfig(home=tmp_path, project=None, runtime=rt)
    result = cfg.ensure_runtime()
    assert result == rt
    assert rt.is_dir()


def test_ensure_sessions_creates_dir(tmp_path):
    rt = tmp_path / "rt"
    cfg = ZChatConfig(home=tmp_path, project=None, runtime=rt)
    result = cfg.ensure_sessions()
    assert result == rt / "sessions"
    assert (rt / "sessions").is_dir()


# ── _find_project_root ──


def test_find_project_root_finds_zchat_dir(tmp_path, monkeypatch):
    """_find_project_root locates .zchat/ in a parent directory."""
    project_root = tmp_path / "project"
    zchat_dir = project_root / ".zchat"
    zchat_dir.mkdir(parents=True)
    sub = project_root / "src" / "deep"
    sub.mkdir(parents=True)
    monkeypatch.chdir(sub)
    result = _find_project_root()
    assert result == zchat_dir


def test_find_project_root_returns_none(tmp_path, monkeypatch):
    """_find_project_root returns None when no .zchat/ exists."""
    bare = tmp_path / "bare"
    bare.mkdir()
    monkeypatch.chdir(bare)
    result = _find_project_root()
    assert result is None


def test_resolve_finds_project_via_filesystem(tmp_path, monkeypatch):
    """resolve() auto-detects project from .zchat/ in parent."""
    proj = tmp_path / "proj"
    zchat_dir = proj / ".zchat"
    zchat_dir.mkdir(parents=True)
    monkeypatch.chdir(proj)
    monkeypatch.setenv("ZCHAT_HOME", str(tmp_path / "h"))
    monkeypatch.setenv("ZCHAT_RUNTIME", str(tmp_path / "rt"))
    monkeypatch.delenv("ZCHAT_PROJECT", raising=False)
    cfg = ZChatConfig.resolve()
    assert cfg.project == zchat_dir


# ── Frozen dataclass ──


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


# ── Frozen dataclass ──


def test_config_is_frozen(tmp_path):
    """ZChatConfig is immutable."""
    cfg = ZChatConfig(home=tmp_path, project=None, runtime=tmp_path / "rt")
    with pytest.raises(AttributeError):
        cfg.home = tmp_path / "other"  # type: ignore[misc]
