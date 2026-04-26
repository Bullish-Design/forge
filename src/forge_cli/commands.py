"""Typer commands for forge orchestration."""

from __future__ import annotations

from pathlib import Path

import typer

from forge_cli.config import ForgeConfig

app = typer.Typer(add_completion=False)


@app.command()
def dev(
    config: Path = typer.Option(Path("forge.yaml"), "--config", help="Path to forge config YAML."),
) -> None:
    """Bootstrap command scaffold for forge dev orchestration."""
    cfg = ForgeConfig.load(config)
    typer.echo("forge dev bootstrap")
    typer.echo("startup-order: overlay -> agent -> kiln")
    typer.echo(f"vault_dir={cfg.vault_dir}")
    typer.echo(f"output_dir={cfg.output_dir}")
    typer.echo(f"overlay_dir={cfg.overlay_dir}")
    typer.echo(f"overlay_url={cfg.overlay_url}")
    typer.echo(f"agent_url={cfg.agent_url}")
    typer.echo(f"on_rebuild_url={cfg.on_rebuild_url}")


@app.command()
def generate() -> None:
    """Placeholder generate command for scaffold milestone."""
    typer.echo("forge generate scaffold")


@app.command()
def serve() -> None:
    """Placeholder serve command for scaffold milestone."""
    typer.echo("forge serve scaffold")


@app.command()
def init() -> None:
    """Placeholder init command for scaffold milestone."""
    typer.echo("forge init scaffold")
