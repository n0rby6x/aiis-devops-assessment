# --- build stage: resolve deps into a venv so the final image stays slim ---
FROM python:3.12-slim AS builder

WORKDIR /app

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- runtime stage ---
FROM python:3.12-slim

# Metadata (nice to have, not required)
LABEL org.opencontainers.image.title="myapp" \
      org.opencontainers.image.description="DevOps homework demo service"

RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin appuser

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY main.py .

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    ENVIRONMENT=dev

USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/health', timeout=2)" || exit 1

# 2 workers is a reasonable default for a small stateless-ish service;
# tune via replicaCount in Helm rather than here for horizontal scaling.
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "main:app"]
