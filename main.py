"""
AI Pipeline CLI — entry point for all pipeline commands.
"""

from __future__ import annotations
import os
import sys
import json
import uuid
from pathlib import Path
from typing import Optional

# Force UTF-8 output on Windows to avoid encoding errors with Unicode symbols
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

import typer
import yaml
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich import box

# Load .env before any imports that need env vars
load_dotenv()

# Add src/ to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from pipeline.audit import AuditLogger
from pipeline.ai_client import AIClient
from pipeline.intake import load_spec, SpecIntakeError
from pipeline.planning import generate_plan, PlanningError
from pipeline.codegen import generate_code, apply_generated_files, CodegenError
from pipeline.testgen import generate_tests, apply_generated_tests, TestgenError
from pipeline.gates import run_quality_gates
from pipeline.approval import (
    request_plan_approval,
    request_deployment_approval,
    ApprovalRejectedError,
)
from pipeline.context import ProjectContext

app = typer.Typer(
    help="AI-native spec-driven development pipeline",
    no_args_is_help=True,
)
audit_app = typer.Typer(help="Audit log commands")
app.add_typer(audit_app, name="audit")

console = Console()


# ─── Config Loader ────────────────────────────────────────────────────────────


def load_config(config_path: str = "config.yaml") -> dict:
    path = Path(config_path)
    if not path.exists():
        console.print(f"[red]Config file not found: {config_path}[/red]")
        raise typer.Exit(1)
    with open(path) as f:
        return yaml.safe_load(f)


def make_run_id() -> str:
    from datetime import datetime

    return f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"


# ─── Commands ─────────────────────────────────────────────────────────────────


@app.command()
def validate(
    spec_path: str = typer.Argument(..., help="Path to the feature spec file"),
):
    """Validate a feature spec file without running the pipeline."""
    console.print(f"\n[bold]Validating spec:[/bold] {spec_path}\n")
    try:
        spec = load_spec(spec_path)
        console.print("[green]✓ Spec is valid[/green]\n")
        _print_spec_summary(spec)
    except SpecIntakeError as e:
        console.print(f"[red]✗ Spec validation failed:[/red]\n{e}")
        raise typer.Exit(1)


@app.command()
def plan(
    spec_path: str = typer.Argument(..., help="Path to the feature spec file"),
    config_path: str = typer.Option("config.yaml", "--config", "-c"),
):
    """Generate and display an implementation plan without generating code."""
    cfg = load_config(config_path)
    run_id = make_run_id()
    logger = AuditLogger(run_id, cfg["audit_dir"])

    console.print(f"\n[bold blue]Run ID:[/bold blue] {run_id}\n")

    try:
        with _spinner("Loading spec..."):
            spec = load_spec(spec_path)
        console.print("[green]✓ Spec loaded[/green]")

        ai = AIClient(
            model=cfg["model"],
            prompts_dir=cfg["prompts_dir"],
            audit_logger=logger,
            temperature=cfg.get("temperature", 0.2),
        )

        with _spinner("Generating plan..."):
            plan_output = generate_plan(spec, ai, cfg["artifacts_dir"], logger)
        console.print("[green]✓ Plan generated[/green]")

        request_plan_approval(plan_output, logger)
        logger.complete()

    except (SpecIntakeError, PlanningError, ApprovalRejectedError) as e:
        console.print(f"\n[red]Pipeline stopped:[/red] {e}")
        raise typer.Exit(1)


@app.command()
def run(
    spec_path: str = typer.Argument(..., help="Path to the feature spec file"),
    config_path: str = typer.Option("config.yaml", "--config", "-c"),
    mode: str = typer.Option("new", "--mode", "-m", help="'new' or 'existing'"),
    root: str = typer.Option(
        ".", "--root", "-r", help="Output directory for generated files"
    ),
    skip_gates: bool = typer.Option(
        False, "--skip-gates", help="Skip quality gates (not recommended)"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Run without writing files to project"
    ),
):
    """
    Run the full pipeline: spec → plan → code → tests → quality gates → deploy.
    """
    cfg = load_config(config_path)
    run_id = make_run_id()
    logger = AuditLogger(run_id, cfg["audit_dir"])

    console.print()
    console.print(
        Panel(
            f"[bold]Run ID:[/bold] {run_id}\n"
            f"[bold]Spec:[/bold] {spec_path}\n"
            f"[bold]Mode:[/bold] {mode}\n"
            f"[bold]Audit log:[/bold] {logger.get_log_path()}",
            title="[bold blue]AI Pipeline[/bold blue]",
            border_style="blue",
        )
    )
    console.print()

    try:
        # ── Stage 1: Spec Intake ──────────────────────────────────────────────
        _stage_header("1 / 7", "Spec Intake")
        with _spinner("Loading and validating spec..."):
            spec = load_spec(spec_path)
        logger.log_stage("intake", "passed", artifacts=[spec_path])
        console.print(
            f"[green]✓ Spec valid[/green] — {len(spec.acceptance_criteria)} acceptance criteria\n"
        )

        # ── Context (existing mode) ───────────────────────────────────────────
        project_context = {}
        if mode == "existing":
            _stage_header("1b", "Project Context Detection")
            with _spinner("Scanning existing project..."):
                ctx = ProjectContext(root)
                project_context = ctx.detect()
            console.print(
                f"[green]✓ Context detected[/green] — {project_context['tech_stack']}\n"
            )

        # ── Stage 2: AI Client ────────────────────────────────────────────────
        ai = AIClient(
            model=cfg["model"],
            prompts_dir=cfg["prompts_dir"],
            audit_logger=logger,
            temperature=cfg.get("temperature", 0.2),
        )

        # ── Stage 3: Planning ─────────────────────────────────────────────────
        _stage_header("2 / 7", "Planning")
        with _spinner("Generating implementation plan..."):
            plan_output = generate_plan(spec, ai, cfg["artifacts_dir"], logger)
        console.print(
            f"[green]✓ Plan generated[/green] — {len(plan_output.tasks)} tasks\n"
        )

        # ── Approval Checkpoint 1 ─────────────────────────────────────────────
        _stage_header("3 / 7", "Approval Checkpoint 1 — Pre-Implementation")
        request_plan_approval(plan_output, logger)

        # ── Stage 4: Code Generation ──────────────────────────────────────────
        _stage_header("4 / 7", "Code Generation")
        with _spinner("Generating code..."):
            codegen_output = generate_code(
                spec,
                plan_output,
                ai,
                allowed_dirs=cfg["allowed_dirs"],
                artifacts_dir=cfg["artifacts_dir"],
                logger=logger,
            )
        console.print(
            f"[green]✓ Code generated[/green] — {len(codegen_output.files)} files\n"
        )

        # ── Stage 5: Test Generation ──────────────────────────────────────────
        _stage_header("5 / 7", "Test Generation")
        with _spinner("Generating tests..."):
            testgen_output = generate_tests(
                spec,
                codegen_output,
                ai,
                artifacts_dir=cfg["artifacts_dir"],
                logger=logger,
            )
        console.print(
            f"[green]✓ Tests generated[/green] — {len(testgen_output.test_files)} test files\n"
        )

        # ── Stage 6: Quality Gates ────────────────────────────────────────────
        _stage_header("6 / 7", "Quality Gates")
        if skip_gates:
            console.print("[yellow]⚠ Quality gates skipped (--skip-gates)[/yellow]\n")
            quality_report = None
        else:
            # Write generated code to staging area for gate checks
            staging_dir = str(Path(cfg["artifacts_dir"]) / "generated_code")
            with _spinner("Running quality gates..."):
                quality_report = run_quality_gates(
                    target_dir=staging_dir,
                    gate_config=cfg["quality_gates"],
                    logger=logger,
                )

            if quality_report.overall_passed:
                console.print("[green]✓ All quality gates passed[/green]\n")
            else:
                failed = [r.gate for r in quality_report.results if not r.passed]
                console.print(
                    f"[yellow]⚠ Quality gates failed: {', '.join(failed)} — continuing[/yellow]"
                )
                console.print(f"[dim]See audit log: {logger.get_log_path()}[/dim]\n")

        # ── Approval Checkpoint 2 ─────────────────────────────────────────────
        _stage_header("7 / 7", "Approval Checkpoint 2 — Pre-Deployment")
        request_deployment_approval(codegen_output, quality_report, logger)

        # ── Deploy: Write Files ───────────────────────────────────────────────
        if dry_run:
            console.print("[yellow]⚠ Dry run — files not written to project[/yellow]")
        else:
            with _spinner("Writing files to project..."):
                written = apply_generated_files(
                    codegen_output, cfg["artifacts_dir"], root
                )
                written += apply_generated_tests(
                    testgen_output, cfg["artifacts_dir"], root
                )
            console.print(f"[green]✓ {len(written)} files written[/green]")

        logger.complete()

        # ── Final Summary ─────────────────────────────────────────────────────
        console.print()
        console.print(
            Panel(
                f"[green bold]Pipeline completed successfully[/green bold]\n\n"
                f"Run ID: {run_id}\n"
                f"Audit log: {logger.get_log_path()}\n"
                f"Artifacts: {cfg['artifacts_dir']}",
                title="[bold green]✓ Done[/bold green]",
                border_style="green",
            )
        )

    except ApprovalRejectedError as e:
        console.print(f"\n[yellow]Pipeline halted by operator:[/yellow] {e}")
        logger.complete()
        raise typer.Exit(0)
    except (SpecIntakeError, PlanningError, CodegenError, TestgenError) as e:
        console.print(f"\n[red]Pipeline failed:[/red] {e}")
        logger.log_stage("pipeline", "failed", errors=[str(e)])
        logger.complete()
        raise typer.Exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Pipeline interrupted by user.[/yellow]")
        logger.log_stage("pipeline", "failed", errors=["Interrupted by user"])
        logger.complete()
        raise typer.Exit(1)


# ─── Audit Commands ───────────────────────────────────────────────────────────


@audit_app.command("list")
def audit_list(
    config_path: str = typer.Option("config.yaml", "--config", "-c"),
):
    """List all past pipeline runs."""
    cfg = load_config(config_path)
    audit_dir = Path(cfg["audit_dir"])

    if not audit_dir.exists() or not list(audit_dir.glob("*.json")):
        console.print("[dim]No audit logs found.[/dim]")
        return

    table = Table(box=box.SIMPLE, header_style="bold cyan")
    table.add_column("Run ID")
    table.add_column("Started")
    table.add_column("Status")
    table.add_column("Stages")

    for log_file in sorted(audit_dir.glob("*.json"), reverse=True):
        with open(log_file) as f:
            data = json.load(f)
        completed = "✓ Complete" if data.get("completed_at") else "⚠ Incomplete"
        stages = len(data.get("stages", []))
        table.add_row(
            data["run_id"],
            data["started_at"][:19].replace("T", " "),
            completed,
            str(stages),
        )

    console.print(table)


@audit_app.command("show")
def audit_show(
    run_id: str = typer.Argument(..., help="Run ID to inspect"),
    config_path: str = typer.Option("config.yaml", "--config", "-c"),
):
    """Show the full audit log for a pipeline run."""
    cfg = load_config(config_path)
    log_path = Path(cfg["audit_dir"]) / f"{run_id}.json"

    if not log_path.exists():
        console.print(f"[red]Audit log not found: {log_path}[/red]")
        raise typer.Exit(1)

    with open(log_path) as f:
        data = json.load(f)

    console.print_json(json.dumps(data, indent=2))


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _spinner(message: str):
    return Progress(
        SpinnerColumn(),
        TextColumn(f"[dim]{message}[/dim]"),
        transient=True,
        console=console,
    )


def _stage_header(step: str, title: str) -> None:
    console.print(f"[bold cyan]── Stage {step}: {title}[/bold cyan]")


def _print_spec_summary(spec) -> None:
    console.print(f"[bold]Objective:[/bold] {spec.feature_objective}")
    console.print(
        f"[bold]Acceptance Criteria:[/bold] {len(spec.acceptance_criteria)} items"
    )
    console.print(f"[bold]Business Rules:[/bold] {len(spec.business_rules)} items")


if __name__ == "__main__":
    app()
