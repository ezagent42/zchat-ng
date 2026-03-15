"""ExtensionRegistry — skeleton for managing CLI extensions."""

from __future__ import annotations

from zchat_cli.types import ExtensionInfo


class ExtensionRegistry:
    """Registry for managing ZChat CLI extensions."""

    def __init__(self) -> None:
        self._extensions: dict[str, ExtensionInfo] = {}

    def install(self, name: str) -> ExtensionInfo:
        """Install an extension (stub)."""
        info = ExtensionInfo(name=name)
        self._extensions[name] = info
        return info

    def uninstall(self, name: str) -> None:
        """Uninstall an extension (stub)."""
        self._extensions.pop(name, None)

    def list(self) -> list[ExtensionInfo]:
        """List installed extensions."""
        return list(self._extensions.values())
