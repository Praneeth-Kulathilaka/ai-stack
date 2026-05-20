"""
AI Client — single gateway for all Gemini API calls.

Every AI interaction in the pipeline goes through this class.
This ensures:
  - All prompts are loaded from versioned template files
  - Every call is logged with prompt + response for auditability
  - Model/temperature config is centralised
  - Retry logic lives in one place
"""

from __future__ import annotations
import json
import os
import time
from pathlib import Path

import google.generativeai as genai
from google.generativeai.types import GenerateContentResponse

from .audit import AuditLogger


class AIClientError(Exception):
    """Raised when the AI call fails after retries."""
    pass


class AIClient:
    def __init__(
        self,
        model: str,
        prompts_dir: str,
        audit_logger: AuditLogger,
        temperature: float = 0.2,
        max_retries: int = 3,
    ) -> None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "GEMINI_API_KEY environment variable not set. "
                "Copy .env.example to .env and add your key."
            )
        genai.configure(api_key=api_key)
        self.model_name = model
        self.model = genai.GenerativeModel(
            model,
            generation_config=genai.GenerationConfig(temperature=temperature),
        )
        self.prompts_dir = Path(prompts_dir)
        self.logger = audit_logger
        self.max_retries = max_retries

    # ─── Public API ──────────────────────────────────────────────────────────

    def call(self, stage: str, prompt_template: str, variables: dict) -> str:
        """
        Load a prompt template, render it with variables, call Gemini,
        log everything, and return the raw response text.
        """
        prompt = self._render_prompt(prompt_template, variables)
        response_text = self._call_with_retry(prompt)
        self.logger.log_ai_call(
            stage=stage,
            prompt_template=prompt_template,
            prompt_rendered=prompt,
            response=response_text,
            model=self.model_name,
        )
        return response_text

    def call_json(self, stage: str, prompt_template: str, variables: dict) -> dict:
        """
        Like call(), but expects JSON back and parses it.
        Strips markdown code fences that Gemini sometimes adds.
        """
        raw = self.call(stage, prompt_template, variables)
        return self._parse_json(raw)

    # ─── Internal ─────────────────────────────────────────────────────────────

    def _render_prompt(self, template_name: str, variables: dict) -> str:
        path = self.prompts_dir / template_name
        if not path.exists():
            raise FileNotFoundError(f"Prompt template not found: {path}")
        template = path.read_text(encoding="utf-8")
        for key, value in variables.items():
            placeholder = f"{{{key}}}"
            if isinstance(value, (list, dict)):
                value = json.dumps(value, indent=2)
            template = template.replace(placeholder, str(value))
        return template

    def _call_with_retry(self, prompt: str) -> str:
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response: GenerateContentResponse = self.model.generate_content(prompt)
                return response.text
            except Exception as e:
                last_error = e
                wait = 2 ** attempt  # exponential backoff: 2s, 4s, 8s
                if attempt < self.max_retries:
                    time.sleep(wait)
        raise AIClientError(
            f"Gemini call failed after {self.max_retries} attempts: {last_error}"
        )

    def _parse_json(self, raw: str) -> dict:
        """Strip markdown fences and parse JSON."""
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            # drop first and last fence lines
            cleaned = "\n".join(lines[1:-1]).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            raise AIClientError(
                f"AI response was not valid JSON: {e}\nRaw response:\n{raw}"
            )
