"""Configuration loading for forge orchestrator."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class ForgeConfig:
    """Minimal scaffold config for M3 bootstrap."""

    vault_dir: Path = Path("vault")
    output_dir: Path = Path("public")
    overlay_dir: Path = Path("static")
    port: int = 8080
    agent_port: int = 8081

    @property
    def agent_url(self) -> str:
        return f"http://127.0.0.1:{self.agent_port}"

    @property
    def overlay_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def on_rebuild_url(self) -> str:
        return f"{self.overlay_url}/internal/rebuild"

    @classmethod
    def load(cls, path: Path) -> "ForgeConfig":
        data: dict[str, Any] = {}
        if path.exists():
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data = raw

        return cls(
            vault_dir=Path(os.getenv("FORGE_VAULT_DIR", data.get("vault_dir", "vault"))),
            output_dir=Path(os.getenv("FORGE_OUTPUT_DIR", data.get("output_dir", "public"))),
            overlay_dir=Path(os.getenv("FORGE_OVERLAY_DIR", data.get("overlay_dir", "static"))),
            port=int(os.getenv("FORGE_PORT", data.get("port", 8080))),
            agent_port=int(os.getenv("FORGE_AGENT_PORT", data.get("agent_port", 8081))),
        )
