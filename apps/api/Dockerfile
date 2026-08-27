# InsightFlow API — FastAPI service image.
#
# Build:
#   docker build -t insightflow-api ./apps/api
#
# Run (standalone, without compose):
#   docker run -p 8000:8000 \
#     -e DATABASE_URL=postgresql+asyncpg://insightflow:insightflow@host.docker.internal:5432/insightflow \
#     -e LLM_API_KEY=sk-... \
#     -v insightflow_data:/app/data \
#     insightflow-api
#
# The code-sandbox container (insightflow-sandbox) is optional: the API talks to
# it via the Docker socket. Mount /var/run/docker.sock only if you enable it.
FROM python:3.12-slim

# Tini for sane signal handling of the uvicorn process.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl tini \
    && rm -rf /var/lib/apt/lists/*

# docker CLI (optional) so the API can launch the code-sandbox container.
# Not present on every base image flavour, so it is best-effort and non-fatal.
RUN apt-get update \
    && (apt-get install -y --no-install-recommends docker-cli || true) \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install Python deps first for better layer caching.
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code.
COPY app /app/app

# Writable data directory for DuckDB + local file storage (mount a volume here).
RUN mkdir -p /app/data/uploads

EXPOSE 8000

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
