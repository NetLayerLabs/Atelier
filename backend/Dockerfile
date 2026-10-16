# Atelier backend (FastAPI). With no configuration it runs and reports every service as "not connected".
#   docker build -t atelier-backend backend/
#   docker run -p 8787:8787 atelier-backend
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /usr/local/bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Dependencies first (cached layer), exactly as pinned in uv.lock, without dev deps.
# reportlab and pillow ship manylinux wheels, so no system packages are needed.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
COPY scripts ./scripts
# v5: the preset mood boards (real, openly licensed photos + manifest.json + ATTRIBUTION.md)
COPY static/moodboards ./static/moodboards

# Non-root user. static/ is written at runtime (diffusion renders, uploads, quote documents).
# v5: /data is the brand's data dir — the Brand workspace (SQLite + uploaded files) and the per-brand PO / style
# number sequences (sequences.json); docker-compose.yml mounts a volume there.
RUN useradd --create-home --uid 10001 atelier \
    && mkdir -p static/generated static/uploads static/quotes /data \
    && chown -R atelier:atelier static /data
ENV ATELIER_DATA_DIR=/data
VOLUME ["/data"]
USER atelier

EXPOSE 8787
HEALTHCHECK --interval=10s --timeout=4s --start-period=15s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/api/health', timeout=3)"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8787"]
