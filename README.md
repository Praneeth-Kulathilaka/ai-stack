# AI-Native Spec-Driven Development Pipeline

An AI-assisted pipeline that transforms a structured feature specification into implementation plans, code, tests, and deployment artefacts — with human approval gates and full auditability.

---

## Quick Start

### 1. Clone and set up

```bash
git clone <your-repo-url>
cd ai-pipeline

python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux

pip install -r requirements.txt
```

### 2. Configure API key

```bash
copy .env.example .env      # Windows
# cp .env.example .env      # Mac/Linux
```

Create `.env` in root folder and add your Gemini API key:
```
GEMINI_API_KEY=your_key_here
```

Get a free key at: https://aistudio.google.com

### 3. Run the pipeline

```bash
# Validate a spec (no AI calls)
python main.py validate specs/auth_feature.yaml

# Generate a plan only
python main.py plan specs/auth_feature.yaml

# Full pipeline run
python main.py run specs/auth_feature.yaml

# Existing project mode
python main.py run specs/auth_feature.yaml --mode existing --root ./my-project

# Dry run (no files written to project)
python main.py run specs/auth_feature.yaml --dry-run
```

### 4. Docker

```bash
docker build -t ai-pipeline .
docker run --env-file .env ai-pipeline run specs/auth_feature.yaml
```

---

## Pipeline Stages

```
Spec Intake → Planning → [Approval 1] → Code Generation → Test Generation
    → Quality Gates → [Approval 2] → Deploy Files
```

| Stage | What it does |
|---|---|
| Spec Intake | Loads & validates YAML/JSON/Markdown spec |
| Planning | AI generates implementation tasks, design summary, risks |
| Approval 1 | Human reviews plan before any code is generated |
| Code Generation | AI generates code, restricted to allowed directories |
| Test Generation | AI generates pytest tests mapped to acceptance criteria |
| Quality Gates | Runs ruff, mypy, bandit, pytest automatically |
| Approval 2 | Human reviews quality report before files are written |
| Deploy | Writes approved files to project |

---

## Audit Trail

Every pipeline run produces a JSON audit log in `audit/`:

```bash
python main.py audit list           # show all runs
python main.py audit show <run_id>  # inspect a specific run
```

Each log captures: spec version, all AI prompts and responses, approval decisions, validation results, and generated artifacts.

---

## Writing a Spec

Specs can be YAML, JSON, or Markdown (with YAML front-matter). Required fields:

```yaml
feature_objective: "What this feature does"
user_story: "As a ... I want to ... so that ..."
business_rules:
  - Rule 1
acceptance_criteria:
  - AC1: Description
non_functional_requirements:
  - NFR1
out_of_scope:
  - Item 1
```

---

## Configuration

Edit `config.yaml` to change:
- **model**: Gemini model to use (`gemini-1.5-flash`, `gemini-1.5-pro`)
- **allowed_dirs**: Directories AI is permitted to write to
- **quality_gates**: Enable/disable individual gates
- **temperature**: AI creativity (lower = more deterministic)

---

## Running Tests

```bash
pytest tests/ -v --cov=src/pipeline
```

---

## Architecture

### Design Decisions

**Single AI client gateway** — all Gemini calls go through `AIClient`. This centralises retry logic, logging, and model config. Swapping models requires changing one file.

**Prompts as versioned files** — prompts live in `prompts/` with version suffixes (`planning_v1.txt`). This enables prompt iteration without code changes, and the audit log records which version was used.

**Artifacts before deployment** — generated files are written to `artifacts/` first, not directly to the project. They only reach the project after human approval at checkpoint 2.

**Path validation as a hard safety gate** — the `_validate_paths()` function in `codegen.py` rejects any file outside `allowed_dirs` before a single byte is written.

**Pydantic everywhere** — every stage boundary uses typed Pydantic models. This catches malformed AI responses early and makes the pipeline self-documenting.

### Trade-offs

| Decision | Trade-off |
|---|---|
| Gemini free tier | Slightly less capable than GPT-4 or Claude Opus, but zero cost |
| CLI over web UI | Faster to build; sufficient for this prototype |
| JSON-only AI responses | Requires strict prompting, but makes parsing reliable |
| Synchronous pipeline | Simple to reason about; async would improve performance |

### Limitations

- No streaming output from AI (full response before next stage)
- Quality gates run on staging artifacts, not final project files
- No parallel stage execution
- Prompt templates are simple string replacement, not a templating engine

### Future Improvements

- Agent orchestration (LangGraph or similar) for more adaptive planning
- Streaming AI responses with live output
- Web UI dashboard for pipeline runs and audit logs
- Prompt evaluation framework with automated regression testing
- Cost tracking per pipeline run
- Git integration — auto-create branch, commit generated files, open PR
