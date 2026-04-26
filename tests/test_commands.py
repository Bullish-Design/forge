from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from forge_cli.commands import app


def test_dev_prints_startup_order(tmp_path: Path) -> None:
    cfg = tmp_path / "forge.yaml"
    cfg.write_text("vault_dir: ./vault\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(app, ["dev", "--config", str(cfg)])

    assert result.exit_code == 0
    assert "startup-order: overlay -> agent -> kiln" in result.stdout
