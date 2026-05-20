"""
Quality Gates — automated validation checks that run against generated code.

Each gate runs a tool via subprocess and captures pass/fail + output.
The pipeline halts if any enabled gate fails.

Gates implemented:
  - lint:      ruff (fast Python linter)
  - type_check: mypy (static type checking)
  - security:  bandit (security vulnerability scanning)
  - tests:     pytest (test execution with coverage)
"""

from __future__ import annotations
import subprocess
import sys
from pathlib import Path

from .audit import AuditLogger
from .models import GateResult, QualityReport


class QualityGateError(Exception):
    """Raised when one or more quality gates fail."""
    pass


def run_quality_gates(
    target_dir: str,
    gate_config: dict[str, bool],
    logger: AuditLogger,
) -> QualityReport:
    """
    Run all enabled quality gates against the target directory.
    Returns a QualityReport. Logs each result to the audit trail.
    """
    results: list[GateResult] = []

    gate_runners = {
        "lint": _run_lint,
        "type_check": _run_type_check,
        "security": _run_security,
        "tests": _run_tests,
    }

    for gate_name, runner in gate_runners.items():
        if not gate_config.get(gate_name, False):
            results.append(GateResult(
                gate=gate_name,
                passed=True,
                output="(skipped — disabled in config)",
            ))
            continue

        result = runner(target_dir)
        results.append(result)
        logger.log_validation(
            gate=result.gate,
            passed=result.passed,
            output=result.output,
        )

    report = QualityReport.from_results(results)
    logger.log_stage(
        stage="quality_gates",
        status="passed" if report.overall_passed else "failed",
        errors=[r.gate for r in results if not r.passed],
    )

    return report


# ─── Individual Gate Runners ──────────────────────────────────────────────────

def _run_lint(target_dir: str) -> GateResult:
    """Run ruff linter."""
    result = _run_tool(["ruff", "check", target_dir, "--output-format=text"])
    return GateResult(
        gate="lint",
        passed=result.returncode == 0,
        output=result.stdout + result.stderr,
        errors=_extract_errors(result.stdout) if result.returncode != 0 else [],
    )


def _run_type_check(target_dir: str) -> GateResult:
    """Run mypy type checker."""
    result = _run_tool([
        "mypy", target_dir,
        "--ignore-missing-imports",
        "--no-error-summary",
    ])
    return GateResult(
        gate="type_check",
        passed=result.returncode == 0,
        output=result.stdout + result.stderr,
        errors=_extract_errors(result.stdout) if result.returncode != 0 else [],
    )


def _run_security(target_dir: str) -> GateResult:
    """Run bandit security scanner."""
    result = _run_tool([
        "bandit", "-r", target_dir,
        "-ll",          # only medium severity and above
        "-q",           # quiet (no progress bar)
        "--format", "text",
    ])
    # bandit returns 1 if issues found, 0 if clean
    return GateResult(
        gate="security",
        passed=result.returncode == 0,
        output=result.stdout + result.stderr,
        errors=_extract_errors(result.stdout) if result.returncode != 0 else [],
    )


def _run_tests(target_dir: str) -> GateResult:
    """Run pytest with coverage."""
    result = _run_tool([
        sys.executable, "-m", "pytest",
        "tests/",
        "-v",
        "--tb=short",
        f"--cov={target_dir}",
        "--cov-report=term-missing",
        "--no-header",
    ])
    return GateResult(
        gate="tests",
        passed=result.returncode == 0,
        output=result.stdout + result.stderr,
        errors=_extract_test_failures(result.stdout) if result.returncode != 0 else [],
    )


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _run_tool(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )


def _extract_errors(output: str) -> list[str]:
    """Extract lines that look like errors from tool output."""
    return [
        line.strip()
        for line in output.splitlines()
        if line.strip() and ("error" in line.lower() or "E " in line)
    ][:10]  # cap at 10 to keep audit logs readable


def _extract_test_failures(output: str) -> list[str]:
    """Extract FAILED test names from pytest output."""
    return [
        line.strip()
        for line in output.splitlines()
        if line.startswith("FAILED")
    ]
