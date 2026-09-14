FROM ghcr.io/astral-sh/uv:0.9.26 AS uv
FROM node:24-bookworm-slim
COPY --from=uv /uv /uvx /usr/local/bin/
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates git cmake build-essential libssl-dev python3 \
    && rm -rf /var/lib/apt/lists/*
ARG APP_REVISION
ENV UV_PYTHON_INSTALL_DIR=/opt/python PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN test -n "$APP_REVISION" \
    && git clone --filter=blob:none --no-checkout https://github.com/luiscosio/ai-verification.git /app \
    && git -C /app checkout --detach "$APP_REVISION" \
    && git -C /app submodule update --init
WORKDIR /app
RUN uv python install 3.13 \
    && uv sync --project tools/workspace --locked --python 3.13 \
    && ./setup-workspace.sh --jobs 2 \
    && uv run --project tools/workspace --locked python site/build_site.py \
    && useradd --uid 10001 --create-home prover
USER prover
ENTRYPOINT ["/app/tools/workspace/.venv/bin/python", "site/local_prover.py"]
