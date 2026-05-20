"""
Audit Logger — captures every meaningful event in the pipeline.

Design principle: write to disk after every event so that even
if the pipeline crashes mid-run, the audit trail is preserved.
"""

from __future__ import annotations
import json
import os
from datetime import datetime, timezone
from pathlib import Path


class AuditLogger:
    def __init__(self, run_id: str, audit_dir: str) -> None:
        self.run_id = run_id
        self.audit_dir = Path(audit_dir)
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.audit_dir / f"{run_id}.json"

        self._log: dict = {
            "run_id": run_id,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
            "stages": [],
            "ai_interactions": [],
            "approvals": [],
            "validation_results": [],
        }
        self._save()

    # ─── Public API ──────────────────────────────────────────────────────────

    def log_stage(
        self,
        stage: str,
        status: str,
        artifacts: list[str] = [],
        errors: list[str] = [],
        metadata: dict = {},
    ) -> None:
        """Record the outcome of a pipeline stage."""
        self._log["stages"].append({
            "stage": stage,
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "artifacts": artifacts,
            "errors": errors,
            "metadata": metadata,
        })
        self._save()

    def log_ai_call(
        self,
        stage: str,
        prompt_template: str,
        prompt_rendered: str,
        response: str,
        model: str,
    ) -> None:
        """Record every AI interaction for reproducibility."""
        self._log["ai_interactions"].append({
            "stage": stage,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "model": model,
            "prompt_template": prompt_template,
            "prompt_rendered": prompt_rendered,
            "response": response,
        })
        self._save()

    def log_approval(self, checkpoint: str, approved: bool, note: str = "") -> None:
        """Record human approval decisions."""
        self._log["approvals"].append({
            "checkpoint": checkpoint,
            "approved": approved,
            "note": note,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        self._save()

    def log_validation(self, gate: str, passed: bool, output: str) -> None:
        """Record quality gate results."""
        self._log["validation_results"].append({
            "gate": gate,
            "passed": passed,
            "output": output,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        self._save()

    def complete(self) -> None:
        """Mark the run as completed."""
        self._log["completed_at"] = datetime.now(timezone.utc).isoformat()
        self._save()

    def get_log_path(self) -> str:
        return str(self.log_path)

    # ─── Internal ─────────────────────────────────────────────────────────────

    def _save(self) -> None:
        with open(self.log_path, "w", encoding="utf-8") as f:
            json.dump(self._log, f, indent=2, ensure_ascii=False)
