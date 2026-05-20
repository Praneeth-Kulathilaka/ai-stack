"""
Code Generation — generates code from an approved implementation plan.

Key safety principle: all generated files are written to the artifacts
directory first. Only after human approval are they written to the
actual project directory. Files outside allowed_dirs are rejected.
"""

from __future__ import annotations
import json
from pathlib import Path, PurePosixPath

from .ai_client import AIClient, AIClientError
from .audit import AuditLogger
from .models import CodegenOutput, FeatureSpec, GeneratedFile, PlanOutput


class CodegenError(Exception):
    pass


class PathViolationError(CodegenError):
    """Raised when AI tries to write outside allowed directories."""
    pass


def generate_code(
    spec: FeatureSpec,
    plan: PlanOutput,
    ai_client: AIClient,
    allowed_dirs: list[str],
    artifacts_dir: str,
    logger: AuditLogger,
) -> CodegenOutput:
    """
    Generate code from the approved plan.
    Validates all file paths against allowed_dirs.
    Saves generated files to artifacts/ (not to the actual project yet).
    """
    try:
        # Summarise generated files for the prompt context
        generated_files_summary = [
            {"filepath": f, "purpose": "to be generated"}
            for f in plan.impacted_files
        ]

        data = ai_client.call_json(
            stage="codegen",
            prompt_template="codegen_v1.txt",
            variables={
                "feature_objective": spec.feature_objective,
                "technical_design_summary": plan.technical_design_summary,
                "tasks": [t.model_dump() for t in plan.tasks],
                "impacted_files": plan.impacted_files,
                "business_rules": spec.business_rules,
                "acceptance_criteria": spec.acceptance_criteria,
                "non_functional_requirements": spec.non_functional_requirements,
                "allowed_dirs": allowed_dirs,
            },
        )

        output = _parse_output(data)

    except AIClientError as e:
        raise CodegenError(f"AI call failed during code generation: {e}") from e
    except CodegenError:
        raise
    except Exception as e:
        raise CodegenError(f"Code generation failed: {e}") from e

    # Validate all paths BEFORE writing anything
    _validate_paths(output.files, allowed_dirs)

    # Write to artifacts staging directory
    artifact_paths = _save_artifacts(output, artifacts_dir)

    logger.log_stage(
        stage="codegen",
        status="passed",
        artifacts=artifact_paths,
        metadata={"change_summary": output.change_summary},
    )

    return output


def apply_generated_files(
    output: CodegenOutput,
    artifacts_dir: str,
    project_root: str = ".",
) -> list[str]:
    """
    Copy approved generated files from artifacts/ to their real destinations.
    Called only after human approval.
    """
    written: list[str] = []
    for gf in output.files:
        dest = Path(project_root) / gf.filepath
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(gf.content, encoding="utf-8")
        written.append(str(dest))
    return written


# ─── Internal ─────────────────────────────────────────────────────────────────

def _parse_output(data: dict) -> CodegenOutput:
    try:
        files = [GeneratedFile(**f) for f in data.get("files", [])]
        if not files:
            raise CodegenError("AI returned no files")
        return CodegenOutput(
            files=files,
            change_summary=data["change_summary"],
        )
    except (KeyError, TypeError) as e:
        raise CodegenError(
            f"AI returned unexpected codegen structure: {e}"
        ) from e


def _validate_paths(files: list[GeneratedFile], allowed_dirs: list[str]) -> None:
    """
    Ensure every generated filepath is inside an allowed directory.
    Prevents AI from writing outside the sandbox.
    """
    for gf in files:
        filepath = gf.filepath.replace("\\", "/")
        if not any(filepath.startswith(d.rstrip("/") + "/") or filepath.startswith(d)
                   for d in allowed_dirs):
            raise PathViolationError(
                f"Generated file '{gf.filepath}' is outside allowed directories: "
                f"{allowed_dirs}. Pipeline halted for safety."
            )


def _save_artifacts(output: CodegenOutput, artifacts_dir: str) -> list[str]:
    staging = Path(artifacts_dir) / "generated_code"
    staging.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []

    for gf in output.files:
        # Mirror the filepath structure inside artifacts/generated_code/
        dest = staging / gf.filepath
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(gf.content, encoding="utf-8")
        paths.append(str(dest))

    # Also save summary
    summary_path = Path(artifacts_dir) / "codegen_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "change_summary": output.change_summary,
                "files": [
                    {"filepath": f.filepath, "description": f.description}
                    for f in output.files
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    paths.append(str(summary_path))
    return paths
