#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


def env(name: str, default: str) -> str:
    value = os.environ.get(name, default)
    return value.strip() if isinstance(value, str) else default


def main() -> int:
    cfg_path = Path(env("FORGE_CONFIG_PATH", "/app/forge.yaml"))
    vault_dir = env("FORGE_VAULT_DIR", "/data/vault")
    output_dir = env("FORGE_OUTPUT_DIR", "/data/public")
    overlay_dir = env("FORGE_OVERLAY_DIR", "/app/static")
    host = env("FORGE_HOST", "0.0.0.0")
    port = env("FORGE_PORT", "8080")
    agent_host = env("FORGE_AGENT_HOST", "127.0.0.1")
    agent_port = env("FORGE_AGENT_PORT", "8081")
    kiln_bin = env("FORGE_KILN_BIN", "/usr/local/bin/kiln")
    agent_model = env("FORGE_AGENT_LLM_MODEL", env("AGENT_LLM_MODEL", "openai:auto"))
    sync_remote_url = env("FORGE_SYNC_REMOTE_URL", "")
    sync_after_commit = env("FORGE_SYNC_AFTER_COMMIT", "true")
    sync_remote = env("FORGE_SYNC_REMOTE", "origin")

    Path(vault_dir).mkdir(parents=True, exist_ok=True)
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    Path(overlay_dir).mkdir(parents=True, exist_ok=True)
    cfg_path.parent.mkdir(parents=True, exist_ok=True)

    if not Path(kiln_bin).exists():
        print(
            f"[forge-entrypoint] missing kiln binary at {kiln_bin}. "
            "Mount host kiln via KILN_BIN_HOST_PATH or bake kiln into image.",
            file=sys.stderr,
        )
        return 2

    lines = [
        f"vault_dir: {vault_dir}",
        f"output_dir: {output_dir}",
        f"overlay_dir: {overlay_dir}",
        f"host: {host}",
        f"port: {port}",
        "",
        "agent:",
        f"  host: {agent_host}",
        f"  port: {agent_port}",
        f"  vault_dir: {vault_dir}",
        f"  llm_model: {agent_model}",
        "",
        "kiln:",
        f"  bin: {kiln_bin}",
        "  theme: default",
        "  font: inter",
        "  lang: en",
        "  site_name: Forge Docker",
    ]
    if sync_remote_url:
        lines.extend(
            [
                "",
                "sync:",
                f"  after_commit: {sync_after_commit}",
                f"  remote: {sync_remote}",
                f"  remote_url: {sync_remote_url}",
            ]
        )
    config_text = "\n".join(lines) + "\n"
    cfg_path.write_text(config_text, encoding="utf-8")

    cmd = ["forge", "dev", "--config", str(cfg_path)]
    print(f"[forge-entrypoint] exec: {' '.join(cmd)}")
    completed = subprocess.run(cmd, check=False)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
