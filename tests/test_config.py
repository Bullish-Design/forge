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
