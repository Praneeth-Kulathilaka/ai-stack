"""
Planning Layer — converts a validated spec into a structured implementation plan.

Uses Gemini to reason about the spec and produce tasks, design summary,
impacted files, risks, and test strategy.
"""

from __future__ import annotations
from pathlib import Path

from pydantic import ValidationError

from .ai_client import AIClient, AIClientError
from .audit import AuditLogger
from .models import FeatureSpec, PlanOutput, Task


class PlanningError(Exception):
    pass


def generate_plan(
    spec: FeatureSpec,
    ai_client: AIClient,
    artifacts_dir: str,
    logger: AuditLogger,
) -> PlanOutput:
    """
    Generate an implementation plan from a validated spec.
    Saves the plan as an artifact and returns a PlanOutput.
    """
    try:
        data = ai_client.call_json(
            stage="planning",
            prompt_template="planning_v1.txt",
            variables={
                "feature_objective": spec.feature_objective,
                "user_story": spec.user_story,
                "business_rules": spec.business_rules,
                "acceptance_criteria": spec.acceptance_criteria,
                "non_functional_requirements": spec.non_functional_requirements,
                "out_of_scope": spec.out_of_scope,
            },
        )
        plan = _parse_plan(data)

    except AIClientError as e:
        raise PlanningError(f"AI call failed during planning: {e}") from e
    except Exception as e:
        raise PlanningError(f"Planning failed: {e}") from e

    # Save artifact
    artifact_path = _save_artifact(plan, artifacts_dir)
    logger.log_stage(
        stage="planning",
        status="passed",
        artifacts=[artifact_path],
    )

    return plan


# ─── Internal ─────────────────────────────────────────────────────────────────

def _parse_plan(data: dict) -> PlanOutput:
    try:
        tasks = [Task(**t) for t in data.get("tasks", [])]
        return PlanOutput(
            tasks=tasks,
            technical_design_summary=data["technical_design_summary"],
            impacted_files=data["impacted_files"],
            risk_considerations=data["risk_considerations"],
            test_strategy=data["test_strategy"],
        )
    except (KeyError, ValidationError) as e:
        raise PlanningError(
            f"AI returned an unexpected plan structure: {e}\nData: {data}"
        ) from e


def _save_artifact(plan: PlanOutput, artifacts_dir: str) -> str:
    path = Path(artifacts_dir) / "plan.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    return str(path)
