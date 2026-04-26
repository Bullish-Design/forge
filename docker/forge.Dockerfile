FROM python:3.13-slim

ARG FORGE_OVERLAY_REF=main
ARG OBSIDIAN_AGENT_REF=main
ARG OBSIDIAN_OPS_REF=main

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    git \
  && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock README.md /app/
COPY src /app/src

RUN pip install --no-cache-dir . \
  && pip install --no-cache-dir \
    "forge-overlay @ git+https://github.com/Bullish-Design/forge-overlay.git@${FORGE_OVERLAY_REF}" \
    "obsidian-ops @ git+https://github.com/Bullish-Design/obsidian-ops.git@${OBSIDIAN_OPS_REF}" \
    "obsidian-agent @ git+https://github.com/Bullish-Design/obsidian-agent.git@${OBSIDIAN_AGENT_REF}"

COPY docker/entrypoint.py /usr/local/bin/forge-entrypoint.py
RUN chmod +x /usr/local/bin/forge-entrypoint.py

ENTRYPOINT ["python", "/usr/local/bin/forge-entrypoint.py"]
