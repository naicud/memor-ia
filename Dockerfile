# ─── MEMORIA MCP Server ───
# Multi-stage build with uv for fast, reproducible installs

FROM python:3.12-slim AS base

# ── Stage 1: Build ──
FROM base AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install dependencies first (layer cache)
COPY pyproject.toml README.md LICENSE ./
COPY src/ src/

RUN uv venv /app/.venv && \
    uv pip install --python /app/.venv/bin/python -e ".[full]"

# ── Stage 2: Runtime ──
FROM base AS runtime

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=builder /app/pyproject.toml /app/README.md /app/LICENSE ./

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    MEMORIA_TRANSPORT=http \
    MEMORIA_HOST=0.0.0.0 \
    MEMORIA_PORT=8080

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

ENTRYPOINT ["python", "-m", "memoria.mcp"]
