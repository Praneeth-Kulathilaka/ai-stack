"""
Project Context — detects tech stack and existing code structure.

Used in 'existing' mode to give the AI context about the current
codebase so generated code matches existing conventions.
"""

from __future__ import annotations
from pathlib import Path


class ProjectContext:
    def __init__(self, project_root: str) -> None:
        self.root = Path(project_root)

    def detect(self) -> dict:
        """
        Scan the project root and return a context dict for the AI prompt.
        """
        return {
            "mode": "existing",
            "tech_stack": self._detect_tech_stack(),
            "existing_files": self._list_source_files(),
            "conventions": self._detect_conventions(),
        }

    # ─── Detectors ────────────────────────────────────────────────────────────

    def _detect_tech_stack(self) -> str:
        indicators = []

        if (self.root / "requirements.txt").exists():
            indicators.append("Python (pip)")
        if (self.root / "pyproject.toml").exists():
            indicators.append("Python (pyproject)")
        if (self.root / "package.json").exists():
            indicators.append("Node.js")
        if (self.root / "Dockerfile").exists():
            indicators.append("Docker")
        if (self.root / ".github" / "workflows").exists():
            indicators.append("GitHub Actions")
        if (self.root / "pytest.ini").exists() or (self.root / "setup.cfg").exists():
            indicators.append("pytest")

        return ", ".join(indicators) if indicators else "Unknown"

    def _list_source_files(self, max_files: int = 50) -> list[str]:
        """List Python source files, capped to avoid huge prompts."""
        files = []
        for path in self.root.rglob("*.py"):
            relative = str(path.relative_to(self.root))
            # skip venv, __pycache__, .git
            if any(part.startswith((".","__")) or part == "venv"
                   for part in path.parts):
                continue
            files.append(relative)
            if len(files) >= max_files:
                break
        return files

    def _detect_conventions(self) -> str:
        conventions = []

        if (self.root / "pyproject.toml").exists():
            conventions.append("Uses pyproject.toml for configuration")
        if (self.root / "ruff.toml").exists() or (self.root / ".ruff.toml").exists():
            conventions.append("Uses ruff for linting")
        if any(self.root.glob("src/")):
            conventions.append("src/ layout")
        if any(self.root.glob("tests/")):
            conventions.append("tests/ directory")

        return "; ".join(conventions) if conventions else "No specific conventions detected"
