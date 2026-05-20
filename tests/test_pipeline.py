"""
Pipeline unit tests — tests for spec intake, models, and core utilities.
These run without needing a real Gemini API key.
"""

from __future__ import annotations
import json
import tempfile
from pathlib import Path

import pytest
import yaml

from pipeline.intake import load_spec, SpecIntakeError
from pipeline.models import FeatureSpec, PlanOutput, Task, QualityReport, GateResult
from pipeline.audit import AuditLogger
from pipeline.codegen import _validate_paths, PathViolationError, GeneratedFile
from pipeline.context import ProjectContext


# ─── Fixtures ─────────────────────────────────────────────────────────────────

VALID_SPEC = {
    "feature_objective": "Add user authentication",
    "user_story": "As a user I want to log in",
    "business_rules": ["Password must be 8+ chars"],
    "acceptance_criteria": ["AC1: User can log in"],
    "non_functional_requirements": ["Response under 300ms"],
    "out_of_scope": ["OAuth"],
}


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def valid_yaml_spec(temp_dir):
    path = temp_dir / "spec.yaml"
    path.write_text(yaml.dump(VALID_SPEC), encoding="utf-8")
    return str(path)


@pytest.fixture
def valid_json_spec(temp_dir):
    path = temp_dir / "spec.json"
    path.write_text(json.dumps(VALID_SPEC), encoding="utf-8")
    return str(path)


@pytest.fixture
def valid_md_spec(temp_dir):
    content = "---\n" + yaml.dump(VALID_SPEC) + "\n---\n# Feature\n"
    path = temp_dir / "spec.md"
    path.write_text(content, encoding="utf-8")
    return str(path)


# ─── Spec Intake Tests ────────────────────────────────────────────────────────

class TestSpecIntake:
    def test_loads_valid_yaml(self, valid_yaml_spec):
        """AC: Pipeline accepts valid YAML spec."""
        spec = load_spec(valid_yaml_spec)
        assert isinstance(spec, FeatureSpec)
        assert spec.feature_objective == "Add user authentication"

    def test_loads_valid_json(self, valid_json_spec):
        """AC: Pipeline accepts valid JSON spec."""
        spec = load_spec(valid_json_spec)
        assert spec.user_story == "As a user I want to log in"

    def test_loads_valid_markdown(self, valid_md_spec):
        """AC: Pipeline accepts valid Markdown spec with YAML front-matter."""
        spec = load_spec(valid_md_spec)
        assert spec.acceptance_criteria == ["AC1: User can log in"]

    def test_raises_on_missing_file(self):
        """AC: Pipeline fails loudly when spec file does not exist."""
        with pytest.raises(SpecIntakeError, match="not found"):
            load_spec("nonexistent_spec.yaml")

    def test_raises_on_missing_required_field(self, temp_dir):
        """AC: Pipeline fails if required fields are missing from spec."""
        incomplete = {k: v for k, v in VALID_SPEC.items() if k != "user_story"}
        path = temp_dir / "bad.yaml"
        path.write_text(yaml.dump(incomplete))
        with pytest.raises(SpecIntakeError, match="user_story"):
            load_spec(str(path))

    def test_raises_on_empty_acceptance_criteria(self, temp_dir):
        """AC: Pipeline rejects specs with no acceptance criteria."""
        bad = {**VALID_SPEC, "acceptance_criteria": []}
        path = temp_dir / "bad.yaml"
        path.write_text(yaml.dump(bad))
        with pytest.raises(SpecIntakeError):
            load_spec(str(path))

    def test_raises_on_invalid_yaml(self, temp_dir):
        """AC: Pipeline fails on malformed YAML."""
        path = temp_dir / "bad.yaml"
        path.write_text("key: [unclosed bracket")
        with pytest.raises(SpecIntakeError, match="Invalid YAML"):
            load_spec(str(path))

    def test_raises_on_unsupported_format(self, temp_dir):
        """AC: Pipeline rejects unsupported file formats."""
        path = temp_dir / "spec.txt"
        path.write_text("some content")
        with pytest.raises(SpecIntakeError, match="Unsupported"):
            load_spec(str(path))


# ─── Model Tests ──────────────────────────────────────────────────────────────

class TestModels:
    def test_feature_spec_strips_whitespace(self):
        """Feature objective should be stripped of leading/trailing whitespace."""
        spec = FeatureSpec(
            feature_objective="  Add auth  ",
            user_story="  Story  ",
            business_rules=["rule"],
            acceptance_criteria=["AC1"],
            non_functional_requirements=["NFR"],
            out_of_scope=["item"],
        )
        assert spec.feature_objective == "Add auth"
        assert spec.user_story == "Story"

    def test_quality_report_overall_pass(self):
        """QualityReport passes only when all gates pass."""
        results = [
            GateResult(gate="lint", passed=True, output=""),
            GateResult(gate="type_check", passed=True, output=""),
        ]
        report = QualityReport.from_results(results)
        assert report.overall_passed is True

    def test_quality_report_overall_fail(self):
        """QualityReport fails when any gate fails."""
        results = [
            GateResult(gate="lint", passed=True, output=""),
            GateResult(gate="security", passed=False, output="Issue found"),
        ]
        report = QualityReport.from_results(results)
        assert report.overall_passed is False


# ─── Path Validation Tests ────────────────────────────────────────────────────

class TestPathValidation:
    def test_allows_file_in_allowed_dir(self):
        """Codegen accepts files inside allowed directories."""
        files = [GeneratedFile(
            filepath="src/auth/models.py",
            content="# code",
            description="Models",
        )]
        # Should not raise
        _validate_paths(files, allowed_dirs=["src/", "tests/"])

    def test_rejects_file_outside_allowed_dir(self):
        """Codegen rejects files outside allowed directories — safety gate."""
        files = [GeneratedFile(
            filepath="config/secrets.py",
            content="# malicious",
            description="Bad file",
        )]
        with pytest.raises(PathViolationError):
            _validate_paths(files, allowed_dirs=["src/", "tests/"])

    def test_allows_test_file(self):
        """Codegen accepts test files in tests/ directory."""
        files = [GeneratedFile(
            filepath="tests/test_auth.py",
            content="# tests",
            description="Tests",
        )]
        _validate_paths(files, allowed_dirs=["src/", "tests/"])


# ─── Audit Logger Tests ───────────────────────────────────────────────────────

class TestAuditLogger:
    def test_creates_log_file(self, temp_dir):
        """Audit logger creates a JSON log file on init."""
        logger = AuditLogger("run_test_001", str(temp_dir))
        assert (temp_dir / "run_test_001.json").exists()

    def test_logs_stage(self, temp_dir):
        """Stage results are persisted to the log file."""
        logger = AuditLogger("run_test_002", str(temp_dir))
        logger.log_stage("intake", "passed", artifacts=["spec.yaml"])

        with open(temp_dir / "run_test_002.json") as f:
            data = json.load(f)

        assert len(data["stages"]) == 1
        assert data["stages"][0]["stage"] == "intake"
        assert data["stages"][0]["status"] == "passed"

    def test_logs_approval(self, temp_dir):
        """Approval decisions are persisted to the log file."""
        logger = AuditLogger("run_test_003", str(temp_dir))
        logger.log_approval("pre_implementation", approved=True, note="LGTM")

        with open(temp_dir / "run_test_003.json") as f:
            data = json.load(f)

        assert data["approvals"][0]["approved"] is True
        assert data["approvals"][0]["checkpoint"] == "pre_implementation"

    def test_complete_sets_timestamp(self, temp_dir):
        """complete() sets the completed_at timestamp."""
        logger = AuditLogger("run_test_004", str(temp_dir))
        logger.complete()

        with open(temp_dir / "run_test_004.json") as f:
            data = json.load(f)

        assert data["completed_at"] is not None


# ─── Context Detection Tests ──────────────────────────────────────────────────

class TestProjectContext:
    def test_detects_python_project(self, temp_dir):
        """Context detector identifies Python projects."""
        (temp_dir / "requirements.txt").write_text("flask\n")
        ctx = ProjectContext(str(temp_dir))
        result = ctx.detect()
        assert "Python" in result["tech_stack"]

    def test_lists_python_files(self, temp_dir):
        """Context detector lists Python source files."""
        (temp_dir / "app.py").write_text("# app")
        ctx = ProjectContext(str(temp_dir))
        result = ctx.detect()
        assert "app.py" in result["existing_files"]
