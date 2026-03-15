"""SpawnConfig — agent spawn configuration parsed from TOML."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _from_dict(data: dict[str, Any]) -> SpawnConfig:
    """Build a SpawnConfig from a parsed TOML dict."""
    skills_table = data.get("skills", {})
    return SpawnConfig(
        name=data.get("name", ""),
        model=data.get("model"),
        system_prompt=data.get("system_prompt"),
        skills=skills_table.get("enabled", []),
    )


@dataclass(frozen=True)
class SpawnConfig:
    """Configuration for spawning an agent."""

    name: str
    model: str | None = None
    system_prompt: str | None = None
    skills: list[str] = field(default_factory=list)

    @classmethod
    def from_toml(cls, toml_str: str) -> SpawnConfig:
        """Parse a TOML string into a SpawnConfig."""
        data = tomllib.loads(toml_str)
        return _from_dict(data)

    @classmethod
    def from_toml_file(cls, path: str | Path) -> SpawnConfig:
        """Parse a TOML file into a SpawnConfig."""
        with open(path, "rb") as f:
            data = tomllib.load(f)
        return _from_dict(data)
