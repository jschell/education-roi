# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12.15 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
RUN uv sync --frozen --no-dev

FROM python:3.12-slim-bookworm AS runtime
RUN useradd --create-home --uid 10001 appuser
WORKDIR /app
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appuser /app/src /app/src
COPY --chown=appuser:appuser data/README.md data/README.md
COPY --chown=appuser:appuser results/README.md results/README.md
ENV PATH="/app/.venv/bin:$PATH" EDU_ROI_ROOT=/app
USER appuser
ENTRYPOINT ["edu-roi"]
CMD ["--help"]
