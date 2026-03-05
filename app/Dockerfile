FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /opt/app

# System deps for trafilatura / lxml
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      build-essential libxml2-dev libxslt1-dev curl && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --upgrade pip && \
    pip install .

COPY . .

# Health check for FastAPI
HEALTHCHECK --interval=15s --timeout=5s --retries=3 \
  CMD curl -sf http://localhost:8000/health || exit 1

EXPOSE 8000
