FROM golang:1.25-bookworm AS kiln-builder

ARG FORGE_OVERLAY_REF=main
ARG OBSIDIAN_AGENT_REF=main
ARG OBSIDIAN_OPS_REF=main
ARG KILN_REF=v0.10.3
ARG JJ_VERSION=0.35.0

RUN git clone --depth 1 --branch ${KILN_REF} https://github.com/Bullish-Design/kiln-fork.git /src/kiln-fork
WORKDIR /src/kiln-fork
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/kiln ./cmd/kiln

FROM rust:1.88-bookworm AS jj-builder

ARG JJ_VERSION=0.35.0
RUN cargo install --locked --version ${JJ_VERSION} jj-cli \
  || cargo install --locked --version 0.35.0 jj-cli

FROM python:3.13-slim

ARG FORGE_OVERLAY_REF=v0.2.1
ARG OBSIDIAN_AGENT_REF=v0.3.1
ARG OBSIDIAN_OPS_REF=v0.7.1

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    git \
  && rm -rf /var/lib/apt/lists/*

COPY --from=kiln-builder /out/kiln /usr/local/bin/kiln
COPY --from=jj-builder /usr/local/cargo/bin/jj /usr/local/bin/jj

COPY pyproject.toml uv.lock README.md /app/
COPY src /app/src

RUN pip install --no-cache-dir \
    "forge-overlay @ git+https://github.com/Bullish-Design/forge-overlay.git@${FORGE_OVERLAY_REF}" \
    "obsidian-ops @ git+https://github.com/Bullish-Design/obsidian-ops.git@${OBSIDIAN_OPS_REF}" \
    "obsidian-agent @ git+https://github.com/Bullish-Design/obsidian-agent.git@${OBSIDIAN_AGENT_REF}" \
  && pip install --no-cache-dir --no-deps .

COPY docker/entrypoint.py /usr/local/bin/forge-entrypoint.py
RUN chmod +x /usr/local/bin/forge-entrypoint.py

ENTRYPOINT ["python", "/usr/local/bin/forge-entrypoint.py"]
