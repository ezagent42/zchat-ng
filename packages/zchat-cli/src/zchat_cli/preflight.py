"""Preflight checks — verify required tools are available."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field


@dataclass
class PreflightResult:
    """Results of preflight checks."""

    checks: dict[str, bool] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return all(self.checks.values())


def run_preflight() -> PreflightResult:
    """Check that required tools are on PATH."""
    required = ["python3", "gh", "claude"]
    checks = {tool: shutil.which(tool) is not None for tool in required}
    return PreflightResult(checks=checks)
