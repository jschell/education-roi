"""Cross-platform project path configuration."""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectPaths:
    """Resolved paths used by commands without creating them implicitly."""

    root: Path

    @classmethod
    def from_environment(cls, root: Path | None = None) -> "ProjectPaths":
        """Resolve an explicit root, EDU_ROI_ROOT, or the current directory."""
        configured = root or Path(os.environ.get("EDU_ROI_ROOT", Path.cwd()))
        return cls(root=configured.expanduser().resolve())

    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def results(self) -> Path:
        return self.root / "results"
