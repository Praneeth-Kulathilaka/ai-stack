"""
Test Generation — generates pytest tests from generated code and acceptance criteria.

Tests are explicitly mapped back to acceptance criteria so reviewers
can trace every test to a business requirement.
"""

from __future__ import annotations
import json
from pathlib import Path

from .ai_client import AIClient, AIClientError
from .audit import AuditLogger
from .models import CodegenOutput, FeatureSpec, GeneratedTest, TestgenOutput


class TestgenError(Exception):
    pass


def generate_tests(
    spec: FeatureSpec,
    codegen_output: CodegenOutput,
    ai_client: AIClient,
    artifacts_dir: str,
    logger: AuditLogger,
) -> TestgenOutput:
    """
    Generate unit and integration tests from generated code and spec.
    Maps every test back to an acceptance criterion.
    """
    # Build a summary of generated files to pass as context
    generated_files_context = [
        {"filepath": f.filepath, "content": f.content}
        for f in codegen_output.files
    ]

    try:
        data = ai_client.call_json(
            stage="testgen",
            prompt_template="testgen_v1.txt",
            variables={
                "acceptance_criteria": spec.acceptance_criteria,
                "generated_files": json.dumps(generated_files_context, indent=2),
                "feature_objective": spec.feature_objective,
            },
        )
        output = _parse_output(data)

    except AIClientError as e:
        raise TestgenError(f"AI call failed during test generation: {e}") from e
    except TestgenError:
        raise
    except Exception as e:
        raise TestgenError(f"Test generation failed: {e}") from e

    artifact_paths = _save_artifacts(output, artifacts_dir)
    logger.log_stage(
        stage="testgen",
        status="passed",
        artifacts=artifact_paths,
        metadata={"coverage_summary": output.coverage_summary},
    )

    return output


def apply_generated_tests(
    output: TestgenOutput,
    artifacts_dir: str,
    project_root: str = ".",
) -> list[str]:
    """Copy approved test files to their real destinations."""
    written: list[str] = []
    for gt in output.test_files:
        dest = Path(project_root) / gt.filepath
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(gt.content, encoding="utf-8")
        written.append(str(dest))
    return written


# ─── Internal ─────────────────────────────────────────────────────────────────

def _parse_output(data: dict) -> TestgenOutput:
    try:
        test_files = [GeneratedTest(**t) for t in data.get("test_files", [])]
        if not test_files:
            raise TestgenError("AI returned no test files")
        return TestgenOutput(
            test_files=test_files,
            coverage_summary=data["coverage_summary"],
        )
    except (KeyError, TypeError) as e:
        raise TestgenError(
            f"AI returned unexpected testgen structure: {e}"
        ) from e


def _save_artifacts(output: TestgenOutput, artifacts_dir: str) -> list[str]:
    staging = Path(artifacts_dir) / "generated_tests"
    staging.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []

    for gt in output.test_files:
        dest = staging / gt.filepath
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(gt.content, encoding="utf-8")
        paths.append(str(dest))

    summary_path = Path(artifacts_dir) / "testgen_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "coverage_summary": output.coverage_summary,
                "test_files": [
                    {
                        "filepath": t.filepath,
                        "covers_criteria": t.covers_criteria,
                    }
                    for t in output.test_files
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    paths.append(str(summary_path))
    return paths
