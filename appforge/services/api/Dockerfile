# AppForge AI - API and agent worker (Linux container, runs under Docker Desktop/WSL2)
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# curl is used by the compose healthcheck.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Dependency layer first so code edits do not invalidate the install cache.
COPY pyproject.toml README.md ./
COPY appforge ./appforge
RUN pip install --upgrade pip && pip install .

# Non-root runtime user; /data is the artifact volume mount point.
RUN useradd --system --create-home --uid 10001 appforge \
    && mkdir -p /data/artifacts \
    && chown -R appforge:appforge /app /data
USER appforge

ENV APPFORGE_STORAGE_ROOT=/data/artifacts

EXPOSE 8000

HEALTHCHECK --interval=20s --timeout=5s --start-period=25s --retries=5 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "appforge.main:app", "--host", "0.0.0.0", "--port", "8000"]
