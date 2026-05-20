"""
Shared Pydantic models used across all pipeline stages.
Defining them in one place ensures consistency and makes
interfaces between stages explicit and type-safe.
"""

from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, field_validator

# ─── Spec Models ────────────────────────────────────────────────────────────


class FeatureSpec(BaseModel):
    """Validated representation of an input feature specification."""

    feature_objective: str
    user_story: str
    business_rules: list[str]
    acceptance_criteria: list[str]
    non_functional_requirements: list[str]
    out_of_scope: list[str]

    @field_validator("feature_objective", "user_story")
    @classmethod
    def must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Field must not be empty")
        return v.strip()

    @field_validator("acceptance_criteria")
    @classmethod
    def must_have_criteria(cls, v: list[str]) -> list[str]:
        if len(v) == 0:
            raise ValueError("At least one acceptance criterion is required")
        return v


# ─── Planning Models ─────────────────────────────────────────────────────────


class Task(BaseModel):
    id: str
    title: str
    description: str
    estimated_effort: str  # e.g. "small", "medium", "large"


class PlanOutput(BaseModel):
    """Structured output from the planning stage."""

    tasks: list[Task]
    technical_design_summary: str
    impacted_files: list[str]
    risk_considerations: list[str]
    test_strategy: str


# ─── Code Generation Models ──────────────────────────────────────────────────


class GeneratedFile(BaseModel):
    """A single file produced by the code generation stage."""

    filepath: str
    content: str
    description: str


class CodegenOutput(BaseModel):
    """Structured output from the code generation stage."""

    files: list[GeneratedFile]
    change_summary: str


# ─── Test Generation Models ──────────────────────────────────────────────────


class GeneratedTest(BaseModel):
    """A single test file mapped to acceptance criteria."""

    filepath: str
    content: str
    covers_criteria: list[str]  # e.g. ["AC1", "AC3"]


class TestgenOutput(BaseModel):
    """Structured output from the test generation stage."""

    test_files: list[GeneratedTest]
    coverage_summary: str


# ─── Quality Gate Models ─────────────────────────────────────────────────────


class GateResult(BaseModel):
    gate: str
    passed: bool
    output: str
    errors: list[str] = []


class QualityReport(BaseModel):
    """Aggregated results from all quality gates."""

    overall_passed: bool
    results: list[GateResult]

    @classmethod
    def from_results(cls, results: list[GateResult]) -> "QualityReport":
        return cls(
            overall_passed=all(r.passed for r in results),
            results=results,
        )


# ─── Pipeline State ──────────────────────────────────────────────────────────


class StageResult(BaseModel):
    stage: str
    status: Literal["passed", "failed", "skipped", "awaiting_approval"]
    artifacts: list[str] = []
    errors: list[str] = []


class PipelineState(BaseModel):
    """Tracks the overall state as it flows through the pipeline."""

    run_id: str
    mode: Literal["new", "existing"] = "new"
    spec: FeatureSpec | None = None
    plan: PlanOutput | None = None
    codegen: CodegenOutput | None = None
    testgen: TestgenOutput | None = None
    quality_report: QualityReport | None = None
    stages: list[StageResult] = []

    def record_stage(
        self,
        stage: str,
        status: Literal["passed", "failed", "skipped", "awaiting_approval"],
        artifacts: list[str] = [],
        errors: list[str] = [],
    ) -> None:
        self.stages.append(
            StageResult(stage=stage, status=status, artifacts=artifacts, errors=errors)
        )
