from __future__ import annotations

from pathlib import Path

from forge_cli.config import ForgeConfig


def test_load_defaults_when_config_missing(tmp_path: Path) -> None:
    cfg = ForgeConfig.load(tmp_path / "missing.yaml")

    assert cfg.vault_dir == Path("vault")
    assert cfg.output_dir == Path("public")
    assert cfg.overlay_dir == Path("static")
    assert cfg.port == 8080
    assert cfg.agent_port == 8081
    assert cfg.sync_after_commit is False
    assert cfg.sync_remote == "origin"
    assert cfg.sync_remote_url is None
    assert cfg.sync_remote_token is None
    assert cfg.agent_url == "http://127.0.0.1:8081"
    assert cfg.overlay_url == "http://127.0.0.1:8080"
    assert cfg.on_rebuild_url == "http://127.0.0.1:8080/internal/rebuild"


def test_load_nested_yaml_blocks(tmp_path: Path) -> None:
    cfg_path = tmp_path / "forge.yaml"
    cfg_path.write_text(
        """
vault_dir: ./notes
output_dir: ./dist
overlay_dir: ./overlay
port: 9090

agent:
  host: 0.0.0.0
  port: 9191
  vault_dir: ./agent-vault
  llm_model: openai:gpt-4.1-mini

kiln:
  bin: /usr/local/bin/kiln
  theme: nord
  font: merriweather
  lang: it
  site_name: Team Notes

sync:
  after_commit: true
  remote: upstream
  remote_url: https://github.com/example/vault.git
  remote_token: token-abc
""".strip()
        + "\n",
        encoding="utf-8",
    )

    cfg = ForgeConfig.load(cfg_path)

    assert cfg.vault_dir == Path("notes")
    assert cfg.output_dir == Path("dist")
    assert cfg.overlay_dir == Path("overlay")
    assert cfg.port == 9090
    assert cfg.agent_host == "0.0.0.0"
    assert cfg.agent_port == 9191
    assert cfg.agent_vault_dir == Path("agent-vault")
    assert cfg.agent_llm_model == "openai:gpt-4.1-mini"
    assert cfg.kiln_bin == "/usr/local/bin/kiln"
    assert cfg.kiln_theme == "nord"
    assert cfg.kiln_font == "merriweather"
    assert cfg.kiln_lang == "it"
    assert cfg.kiln_site_name == "Team Notes"
    assert cfg.sync_after_commit is True
    assert cfg.sync_remote == "upstream"
    assert cfg.sync_remote_url == "https://github.com/example/vault.git"
    assert cfg.sync_remote_token == "token-abc"
    assert cfg.effective_agent_vault_dir == Path("agent-vault")


def test_env_overrides_file_values(tmp_path: Path, monkeypatch) -> None:
    cfg_path = tmp_path / "forge.yaml"
    cfg_path.write_text(
        """
port: 7000
agent_port: 7001
vault_dir: ./vault-from-file
sync:
  after_commit: false
""".strip()
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("FORGE_PORT", "8000")
    monkeypatch.setenv("FORGE_AGENT_PORT", "8001")
    monkeypatch.setenv("FORGE_VAULT_DIR", "./vault-from-env")
    monkeypatch.setenv("FORGE_SYNC_AFTER_COMMIT", "true")

    cfg = ForgeConfig.load(cfg_path)

    assert cfg.port == 8000
    assert cfg.agent_port == 8001
    assert cfg.vault_dir == Path("vault-from-env")
    assert cfg.sync_after_commit is True
