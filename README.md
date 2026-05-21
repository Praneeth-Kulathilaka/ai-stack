# AI-Native Spec-Driven Development Pipeline

An AI-assisted pipeline that transforms a structured feature specification into implementation plans, code, tests, and deployment artefacts with human approval gates and full auditability.

## Prerequisites

- Python 3.11+
- A Google Gemini API key — get one free at [aistudio.google.com](https://aistudio.google.com/apikey)

## Setup

```bash
git clone https://github.com/Praneeth-Kulathilaka/ai-stack
cd ai-pipeline
pip install -r requirements.txt
```

Create a `.env` file in the root folder and add your Gemini API key:

```
GEMINI_API_KEY=your_actual_key_here
```

## Running with Python

```bash
# Validate a spec (no API key needed)
python main.py validate specs/auth_feature.yaml

# Generate a plan only
python main.py plan specs/auth_feature.yaml

# Full pipeline run
python main.py run specs/auth_feature.yaml

# Output generated files to a separate folder
python main.py run specs/auth_feature.yaml --root ./my-project

# Run against an existing project
python main.py run specs/auth_feature.yaml --mode existing --root ./my-project

# Dry run (no files written)
python main.py run specs/auth_feature.yaml --dry-run

# View past runs
python main.py audit list
python main.py audit show <run_id>
```

## Running with Docker

### Build the image

```bash
docker build -t ai-pipeline .
```

### Run the pipeline

```bash
# Validate a spec
docker run --env-file .env ai-pipeline validate specs/auth_feature.yaml

# Generate a plan
docker run -it --env-file .env ai-pipeline plan specs/auth_feature.yaml

# Full pipeline run — output to a folder on your machine
docker run -it --env-file .env -v ./output:/output ai-pipeline run specs/auth_feature.yaml --root /output

# Use your own spec file from the host
docker run -it --env-file .env -v ./my-specs:/app/specs -v ./output:/output ai-pipeline run specs/my_feature.yaml --root /output
```

> **Note:** Use `-it` for interactive commands (`plan`, `run`) since they require approval prompts. Use `-v` to mount a host directory so generated files persist after the container exits.

## Running Tests

```bash
pytest tests/ -v --cov=src/pipeline
```
