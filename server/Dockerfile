# agent-forge API — production image
FROM python:3.12-slim AS base

# uv for fast, reproducible installs
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# install deps first (cached layer)
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev --frozen 2>/dev/null || uv sync --no-dev

# app code
COPY . .

# run as a non-root user
RUN useradd --system --uid 10001 --home /app --no-create-home agentforge \
    && chown -R agentforge:agentforge /app
USER agentforge

EXPOSE 8099

# migrations are run by the deploy step (see DEPLOY.md), not in the image.
CMD ["gunicorn", "-c", "gunicorn.conf.py", "app.main:app"]
