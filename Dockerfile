# ── Stage 1: Builder ──────────────────────────────────────────────────────────
# Install dependencies in a separate stage so the final image stays small
FROM python:3.11-slim AS builder

WORKDIR /build

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: Runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# Copy installed packages from builder stage
COPY --from=builder /install /usr/local

# Copy project files
COPY . .

# Create directories that will be mounted as volumes
# So they persist after container stops
RUN mkdir -p artifacts audit specs /output

# Run as non-root user for security 
RUN useradd --create-home --shell /bin/bash pipeline
RUN chown -R pipeline:pipeline /app /output
USER pipeline

# Default command — show help
ENTRYPOINT ["python", "main.py"]
CMD ["--help"]
