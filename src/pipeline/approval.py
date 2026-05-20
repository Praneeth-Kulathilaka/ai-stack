"""
Approval Workflow — human checkpoints before critical pipeline stages.

Two checkpoints:
  1. pre_implementation  — after planning, before code is generated
  2. pre_deployment      — after quality gates, before files are written to project

Design principle: approval decisions are always logged to the audit trail,
whether approved or rejected.
"""

from __future__ import annotations
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table
from rich import box

from .audit import AuditLogger
from .models import CodegenOutput, PlanOutput, QualityReport

console = Console()


class ApprovalRejectedError(Exception):
    """Raised when a human rejects an approval checkpoint."""

    pass


def request_plan_approval(
    plan: PlanOutput,
    logger: AuditLogger,
) -> None:
    """
    Show the implementation plan and ask for approval before code generation.
    Raises ApprovalRejectedError if the user rejects.
    """
    _print_plan_summary(plan)

    approved = Confirm.ask(
        "\n[bold yellow]Approve this plan and begin code generation?[/bold yellow]",
        default=False,
    )
    logger.log_approval(
        checkpoint="pre_implementation",
        approved=approved,
        note="Plan reviewed by operator",
    )

    if not approved:
        raise ApprovalRejectedError(
            "Plan rejected by operator. Pipeline halted at pre_implementation checkpoint."
        )

    console.print("[green]✓ Plan approved. Proceeding to code generation.[/green]\n")


def request_deployment_approval(
    codegen_output: CodegenOutput,
    quality_report: QualityReport | None,
    logger: AuditLogger,
) -> None:
    """
    Show the quality report and change summary, ask for final approval
    before writing files to the project.
    Raises ApprovalRejectedError if the user rejects.
    """
    _print_deployment_summary(codegen_output, quality_report)

    approved = Confirm.ask(
        "\n[bold yellow]Approve and write generated files to project?[/bold yellow]",
        default=False,
    )
    logger.log_approval(
        checkpoint="pre_deployment",
        approved=approved,
        note="Quality report reviewed by operator",
    )

    if not approved:
        raise ApprovalRejectedError(
            "Deployment rejected by operator. Pipeline halted at pre_deployment checkpoint."
        )

    console.print("[green]✓ Deployment approved. Writing files.[/green]\n")


# ─── Display Helpers ──────────────────────────────────────────────────────────


def _print_plan_summary(plan: PlanOutput) -> None:
    console.print()
    console.print(
        Panel(
            plan.technical_design_summary,
            title="[bold blue]Technical Design Summary[/bold blue]",
            border_style="blue",
        )
    )

    table = Table(box=box.SIMPLE, show_header=True, header_style="bold cyan")
    table.add_column("ID", style="dim", width=5)
    table.add_column("Task", min_width=30)
    table.add_column("Effort", width=8)

    for task in plan.tasks:
        color = {"small": "green", "medium": "yellow", "large": "red"}.get(
            task.estimated_effort, "white"
        )
        table.add_row(
            task.id,
            f"[bold]{task.title}[/bold]\n{task.description}",
            f"[{color}]{task.estimated_effort}[/{color}]",
        )

    console.print(
        Panel(
            table,
            title="[bold blue]Implementation Tasks[/bold blue]",
            border_style="blue",
        )
    )

    if plan.risk_considerations:
        risks = "\n".join(f"  • {r}" for r in plan.risk_considerations)
        console.print(
            Panel(
                risks,
                title="[bold yellow]⚠ Risk Considerations[/bold yellow]",
                border_style="yellow",
            )
        )


def _print_deployment_summary(
    codegen: CodegenOutput,
    report: QualityReport | None,
) -> None:
    console.print()

    if report is None:
        console.print(
            Panel(
                "Quality gates were skipped for this run.",
                title="[bold yellow]Quality Gates Skipped[/bold yellow]",
                border_style="yellow",
            )
        )
    else:
        # Quality gates table
        table = Table(box=box.SIMPLE, show_header=True, header_style="bold cyan")
        table.add_column("Gate", width=15)
        table.add_column("Status", width=10)
        table.add_column("Notes")

        for result in report.results:
            status = "[green]✓ PASS[/green]" if result.passed else "[red]✗ FAIL[/red]"
            notes = "; ".join(result.errors[:3]) if result.errors else "—"
            table.add_row(result.gate, status, notes)

        console.print(
            Panel(
                table,
                title="[bold blue]Quality Gate Results[/bold blue]",
                border_style="blue",
            )
        )

    # Change summary
    console.print(
        Panel(
            codegen.change_summary,
            title="[bold blue]Change Summary[/bold blue]",
            border_style="blue",
        )
    )

    # Files to be written
    files_list = "\n".join(f"  • {f.filepath}" for f in codegen.files)
    console.print(
        Panel(
            files_list,
            title="[bold blue]Files to be Written[/bold blue]",
            border_style="blue",
        )
    )
