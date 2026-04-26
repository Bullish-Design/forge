"""Typer commands for forge orchestration."""

from __future__ import annotations

from pathlib import Path
import subprocess
import time

import typer
import yaml

from forge_cli.config import ForgeConfig
from forge_cli.processes import ManagedProcess, ProcessManager

app = typer.Typer(add_completion=False)


@app.command()
def dev(
    config: Path = typer.Option(Path("forge.yaml"), "--config", help="Path to forge config YAML."),
) -> None:
    """Run overlay, agent, and kiln in coordinated dev mode."""
    cfg = ForgeConfig.load(config)
    manager = ProcessManager()

    try:
        overlay = manager.start_overlay(cfg)
        agent = manager.start_agent(cfg)
        kiln = manager.start_kiln(cfg)

        typer.echo("forge dev running")
        typer.echo("startup-order: overlay -> agent -> kiln")
        typer.echo(f"overlay={cfg.overlay_url}")
        typer.echo(f"agent={cfg.agent_url}")
        typer.echo(f"on_rebuild={cfg.on_rebuild_url}")
        _wait_for_processes([overlay, agent, kiln])
    except KeyboardInterrupt:
        typer.echo("shutting down forge dev")
    finally:
        manager.stop_all()


@app.command()
def generate(
    config: Path = typer.Option(Path("forge.yaml"), "--config", help="Path to forge config YAML."),
) -> None:
    """Run a one-off kiln static site generation."""
    cfg = ForgeConfig.load(config)
    _run_checked(
        [
            cfg.kiln_bin,
            "generate",
            "--input",
            str(cfg.vault_dir),
            "--output",
            str(cfg.output_dir),
            "--theme",
            cfg.kiln_theme,
            "--font",
            cfg.kiln_font,
            "--lang",
            cfg.kiln_lang,
            "--name",
            cfg.kiln_site_name,
        ]
    )


@app.command()
def serve(
    config: Path = typer.Option(Path("forge.yaml"), "--config", help="Path to forge config YAML."),
) -> None:
    """Run overlay-only preview mode (no kiln watcher)."""
    cfg = ForgeConfig.load(config)
    manager = ProcessManager()
    try:
        overlay = manager.start_overlay(cfg)
        typer.echo(f"forge serve running on {cfg.overlay_url}")
        _wait_for_processes([overlay])
    except KeyboardInterrupt:
        typer.echo("shutting down forge serve")
    finally:
        manager.stop_all()


@app.command()
def init(
    config: Path = typer.Option(Path("forge.yaml"), "--config", help="Path to write forge config YAML."),
    force: bool = typer.Option(False, "--force", help="Overwrite existing config file."),
) -> None:
    """Scaffold vault/output/overlay directories plus a config file."""
    cfg = ForgeConfig()

    cfg.vault_dir.mkdir(parents=True, exist_ok=True)
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    cfg.overlay_dir.mkdir(parents=True, exist_ok=True)

    if config.exists() and not force:
        raise typer.BadParameter(f"{config} already exists; pass --force to overwrite", param_hint="--config")

    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(_render_default_config(cfg), encoding="utf-8")
    typer.echo(f"wrote {config}")


def _run_checked(command: list[str]) -> None:
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as exc:
        raise typer.Exit(code=exc.returncode) from exc


def _wait_for_processes(processes: list[ManagedProcess]) -> None:
    while True:
        for managed in processes:
            return_code = managed.process.poll()
            if return_code is not None:
                raise typer.Exit(code=return_code)
        time.sleep(0.2)


def _render_default_config(cfg: ForgeConfig) -> str:
    payload = {
        "vault_dir": str(cfg.vault_dir),
        "output_dir": str(cfg.output_dir),
        "overlay_dir": str(cfg.overlay_dir),
        "host": cfg.host,
        "port": cfg.port,
        "agent": {
            "host": cfg.agent_host,
            "port": cfg.agent_port,
            "vault_dir": str(cfg.effective_agent_vault_dir),
            "llm_model": cfg.agent_llm_model,
        },
        "kiln": {
            "bin": cfg.kiln_bin,
            "theme": cfg.kiln_theme,
            "font": cfg.kiln_font,
            "lang": cfg.kiln_lang,
            "site_name": cfg.kiln_site_name,
        },
    }
    return yaml.safe_dump(payload, sort_keys=False)
