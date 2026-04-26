"""Process orchestration helpers for forge CLI commands."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from typing import TextIO

import httpx

from forge_cli.config import ForgeConfig


class ProcessLaunchError(RuntimeError):
    """Raised when a subprocess cannot be launched."""


@dataclass(slots=True)
class ManagedProcess:
    """Runtime metadata for a managed child process."""

    name: str
    command: tuple[str, ...]
    process: subprocess.Popen[str]


def wait_for_http(
    url: str,
    timeout_s: float = 20.0,
    interval_s: float = 0.2,
    expected_status: int = 200,
) -> None:
    """Poll ``url`` until it returns ``expected_status`` or timeout."""

    deadline = time.monotonic() + timeout_s
    last_error: BaseException | None = None

    with httpx.Client(follow_redirects=True) as client:
        while time.monotonic() < deadline:
            try:
                with client.stream("GET", url, timeout=1.0) as response:
                    if response.status_code == expected_status:
                        return
                    last_error = RuntimeError(f"status={response.status_code}")
            except httpx.HTTPError as exc:
                last_error = exc

            time.sleep(interval_s)

    detail = f" ({last_error})" if last_error is not None else ""
    raise TimeoutError(f"Timed out waiting for {url}{detail}")


class ProcessManager:
    """Starts and stops forge component subprocesses."""

    def __init__(self, popen_factory: type[subprocess.Popen] = subprocess.Popen) -> None:
        self._popen_factory = popen_factory
        self._processes: list[ManagedProcess] = []
        self._log_threads: list[threading.Thread] = []

    def start(
        self,
        name: str,
        command: Iterable[str],
        *,
        env: Mapping[str, str] | None = None,
        cwd: Path | None = None,
    ) -> ManagedProcess:
        cmd = tuple(command)
        merged_env = os.environ.copy()
        if env is not None:
            merged_env.update({key: str(value) for key, value in env.items()})

        try:
            process = self._popen_factory(
                list(cmd),
                env=merged_env,
                cwd=str(cwd) if cwd is not None else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            rendered = " ".join(cmd)
            raise ProcessLaunchError(f"Failed to launch {name}: {rendered}") from exc

        managed = ManagedProcess(name=name, command=cmd, process=process)
        self._processes.append(managed)

        if process.stdout is not None:
            thread = threading.Thread(
                target=_stream_prefixed_logs,
                args=(name, process.stdout),
                daemon=True,
            )
            thread.start()
            self._log_threads.append(thread)

        return managed

    def start_overlay(self, config: ForgeConfig) -> ManagedProcess:
        process = self.start(
            "overlay",
            [
                "forge-overlay",
                "--site-dir",
                str(config.output_dir),
                "--overlay-dir",
                str(config.overlay_dir),
                "--api-upstream",
                config.agent_url,
                "--host",
                config.host,
                "--port",
                str(config.port),
            ],
        )
        wait_for_http(f"{config.overlay_url}/ops/events")
        return process

    def start_agent(self, config: ForgeConfig) -> ManagedProcess:
        process = self.start(
            "agent",
            ["obsidian-agent"],
            env={
                "AGENT_VAULT_DIR": str(config.effective_agent_vault_dir),
                "AGENT_LLM_MODEL": config.agent_llm_model,
                "AGENT_HOST": config.agent_host,
                "AGENT_PORT": str(config.agent_port),
                "AGENT_SITE_BASE_URL": config.overlay_url,
            },
        )
        wait_for_http(f"{config.agent_url}/api/health")
        return process

    def start_kiln(self, config: ForgeConfig) -> ManagedProcess:
        return self.start(
            "kiln",
            [
                config.kiln_bin,
                "dev",
                "--no-serve",
                "--on-rebuild",
                config.on_rebuild_url,
                "--input",
                str(config.vault_dir),
                "--output",
                str(config.output_dir),
                "--theme",
                config.kiln_theme,
                "--font",
                config.kiln_font,
                "--lang",
                config.kiln_lang,
                "--name",
                config.kiln_site_name,
            ],
        )

    def stop_all(self, timeout_s: float = 5.0) -> None:
        for managed in reversed(self._processes):
            process = managed.process
            if process.poll() is not None:
                continue
            process.terminate()
            try:
                process.wait(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=timeout_s)

        self._processes.clear()

    def __enter__(self) -> ProcessManager:
        return self

    def __exit__(self, *_args: object) -> None:
        self.stop_all()


def _stream_prefixed_logs(name: str, stream: TextIO) -> None:
    for line in stream:
        sys.stdout.write(f"[{name}] {line}")
