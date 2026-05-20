"""
Spec Intake — loads and validates the feature specification.

Supports YAML, JSON, and Markdown (with YAML front-matter).
Fails loudly with clear error messages if required fields are missing.
"""

from __future__ import annotations
import json
from pathlib import Path

import yaml
from pydantic import ValidationError

from .models import FeatureSpec


class SpecIntakeError(Exception):
    """Raised when spec loading or validation fails."""
    pass


def load_spec(spec_path: str) -> FeatureSpec:
    """
    Load and validate a feature spec from a YAML, JSON, or Markdown file.
    Returns a validated FeatureSpec or raises SpecIntakeError.
    """
    path = Path(spec_path)

    if not path.exists():
        raise SpecIntakeError(f"Spec file not found: {spec_path}")

    suffix = path.suffix.lower()

    try:
        raw = path.read_text(encoding="utf-8")

        if suffix in (".yaml", ".yml"):
            data = _load_yaml(raw, spec_path)
        elif suffix == ".json":
            data = _load_json(raw, spec_path)
        elif suffix == ".md":
            data = _load_markdown(raw, spec_path)
        else:
            raise SpecIntakeError(
                f"Unsupported spec format '{suffix}'. "
                "Use .yaml, .yml, .json, or .md"
            )

        return _validate(data)

    except SpecIntakeError:
        raise
    except Exception as e:
        raise SpecIntakeError(f"Failed to read spec file: {e}") from e


# ─── Format Loaders ───────────────────────────────────────────────────────────

def _load_yaml(raw: str, path: str) -> dict:
    try:
        data = yaml.safe_load(raw)
        if not isinstance(data, dict):
            raise SpecIntakeError(f"YAML spec must be a mapping (dict), got: {type(data)}")
        return data
    except yaml.YAMLError as e:
        raise SpecIntakeError(f"Invalid YAML in {path}: {e}") from e


def _load_json(raw: str, path: str) -> dict:
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise SpecIntakeError(f"JSON spec must be an object, got: {type(data)}")
        return data
    except json.JSONDecodeError as e:
        raise SpecIntakeError(f"Invalid JSON in {path}: {e}") from e


def _load_markdown(raw: str, path: str) -> dict:
    """
    Supports Markdown files with YAML front-matter:
    ---
    feature_objective: ...
    ---
    """
    if not raw.startswith("---"):
        raise SpecIntakeError(
            f"Markdown spec must start with YAML front-matter (--- block): {path}"
        )
    parts = raw.split("---", 2)
    if len(parts) < 3:
        raise SpecIntakeError(f"Could not parse YAML front-matter in: {path}")
    return _load_yaml(parts[1], path)


# ─── Validation ───────────────────────────────────────────────────────────────

def _validate(data: dict) -> FeatureSpec:
    try:
        return FeatureSpec(**data)
    except ValidationError as e:
        missing = []
        invalid = []
        for err in e.errors():
            field = ".".join(str(x) for x in err["loc"])
            if err["type"] == "missing":
                missing.append(field)
            else:
                invalid.append(f"{field}: {err['msg']}")

        parts = []
        if missing:
            parts.append(f"Missing required fields: {', '.join(missing)}")
        if invalid:
            parts.append(f"Invalid values: {'; '.join(invalid)}")

        raise SpecIntakeError(
            "Spec validation failed:\n  " + "\n  ".join(parts)
        ) from e
