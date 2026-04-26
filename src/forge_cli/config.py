"""Configuration loading for forge orchestrator."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import yaml


class ForgeConfig(BaseSettings):
    """Config model for the forge orchestrator."""

    model_config = SettingsConfigDict(env_prefix="FORGE_", extra="ignore")

    vault_dir: Path = Path("vault")
    output_dir: Path = Path("public")
    overlay_dir: Path = Path("static")

    host: str = "127.0.0.1"
    port: int = Field(default=8080, ge=1, le=65535)

    agent_host: str = "127.0.0.1"
    agent_port: int = Field(default=8081, ge=1, le=65535)
    agent_vault_dir: Path | None = None
    agent_llm_model: str = "anthropic:claude-sonnet-4-20250514"
    sync_after_commit: bool = False
    sync_remote: str = "origin"
    sync_remote_url: str | None = None
    sync_remote_token: str | None = None

    kiln_bin: str = "kiln"
    kiln_theme: str = "default"
    kiln_font: str = "inter"
    kiln_lang: str = "en"
    kiln_site_name: str = "My Notes"

    @field_validator("vault_dir", "output_dir", "overlay_dir", "agent_vault_dir", mode="before")
    @classmethod
    def normalize_paths(cls, value: object) -> object:
        if value is None:
            return value
        return Path(str(value)).expanduser()

    @property
    def agent_url(self) -> str:
        return f"http://{self.agent_host}:{self.agent_port}"

    @property
    def overlay_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def on_rebuild_url(self) -> str:
        return f"{self.overlay_url}/internal/rebuild"

    @property
    def effective_agent_vault_dir(self) -> Path:
        return self.agent_vault_dir if self.agent_vault_dir is not None else self.vault_dir

    @classmethod
    def load(cls, path: Path) -> "ForgeConfig":
        file_data = _load_yaml_config(path)

        env_settings = cls()
        env_overrides = {k: getattr(env_settings, k) for k in env_settings.model_fields_set}

        merged = {**file_data, **env_overrides}
        return cls(**merged)


def _load_yaml_config(path: Path) -> dict[str, Any]:
    """Load config from forge.yaml-style file with optional nested agent/kiln blocks."""
    if not path.exists():
        return {}

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        return {}

    data: dict[str, Any] = {}

    # Flat keys
    for key in (
        "vault_dir",
        "output_dir",
        "overlay_dir",
        "host",
        "port",
        "agent_host",
        "agent_port",
        "agent_vault_dir",
        "agent_llm_model",
        "kiln_bin",
        "kiln_theme",
        "kiln_font",
        "kiln_lang",
        "kiln_site_name",
    ):
        if key in raw:
            data[key] = raw[key]

    # Nested agent block
    agent = raw.get("agent")
    if isinstance(agent, Mapping):
        if "host" in agent:
            data["agent_host"] = agent["host"]
        if "port" in agent:
            data["agent_port"] = agent["port"]
        if "vault_dir" in agent:
            data["agent_vault_dir"] = agent["vault_dir"]
        if "llm_model" in agent:
            data["agent_llm_model"] = agent["llm_model"]

    # Nested kiln block
    kiln = raw.get("kiln")
    if isinstance(kiln, Mapping):
        if "bin" in kiln:
            data["kiln_bin"] = kiln["bin"]
        if "theme" in kiln:
            data["kiln_theme"] = kiln["theme"]
        if "font" in kiln:
            data["kiln_font"] = kiln["font"]
        if "lang" in kiln:
            data["kiln_lang"] = kiln["lang"]
        if "site_name" in kiln:
            data["kiln_site_name"] = kiln["site_name"]

    # Nested sync block
    sync = raw.get("sync")
    if isinstance(sync, Mapping):
        if "after_commit" in sync:
            data["sync_after_commit"] = sync["after_commit"]
        if "remote" in sync:
            data["sync_remote"] = sync["remote"]
        if "remote_url" in sync:
            data["sync_remote_url"] = sync["remote_url"]
        if "remote_token" in sync:
            data["sync_remote_token"] = sync["remote_token"]

    return data
