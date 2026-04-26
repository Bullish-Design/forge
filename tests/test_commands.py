from __future__ import annotations

import io
from pathlib import Path
import subprocess

import pytest
from typer.testing import CliRunner
import yaml

from forge_cli.commands import app
from forge_cli.config import ForgeConfig
from forge_cli.processes import ProcessManager, wait_for_http


class _DummyProcess:
    def __init__(self, return_code: int | None = None) -> None:
        self.stdout: io.StringIO | None = io.StringIO("")
        self._alive = return_code is None
        self._return_code = 0 if return_code is None else return_code

    def poll(self) -> int | None:
        return None if self._alive else self._return_code

    def terminate(self) -> None:
        self._alive = False

    def wait(self, timeout: float | None = None) -> int:
        _ = timeout
        self._alive = False
        return self._return_code

    def kill(self) -> None:
        self._alive = False


def test_process_manager_starts_overlay_agent_then_kiln(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    vault_dir = tmp_path / "vault"
    public_dir = tmp_path / "public"
    overlay_dir = tmp_path / "overlay"
    for path in (vault_dir, public_dir, overlay_dir):
        path.mkdir()

    cfg = ForgeConfig(
        vault_dir=vault_dir,
        output_dir=public_dir,
        overlay_dir=overlay_dir,
        port=18080,
        agent_port=18081,
    )

    launched: list[tuple[list[str], dict[str, str] | None]] = []
    waited: list[str] = []

    def fake_popen(
        cmd: list[str],
        *,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        stdout: object | None = None,
        stderr: object | None = None,
        text: bool = False,
        bufsize: int = -1,
    ) -> _DummyProcess:
        _ = cwd, stdout, stderr, text, bufsize
        launched.append((cmd, env))
        return _DummyProcess()

    def fake_wait(
        url: str,
        timeout_s: float = 60.0,
        interval_s: float = 0.2,
        expected_status: int = 200,
        expected_statuses: set[int] | None = None,
    ) -> None:
        _ = timeout_s, interval_s, expected_status, expected_statuses
        waited.append(url)

    monkeypatch.setattr("forge_cli.processes.wait_for_http", fake_wait)

    manager = ProcessManager(popen_factory=fake_popen)  # type: ignore[arg-type]
    manager.start_overlay(cfg)
    manager.start_agent(cfg)
    manager.start_kiln(cfg)
    manager.stop_all()

    assert [call[0][0] for call in launched] == ["forge-overlay", "obsidian-agent", "kiln"]
    assert waited == [f"{cfg.overlay_url}/", f"{cfg.agent_url}/api/health"]

    kiln_cmd = launched[2][0]
    assert "--no-serve" in kiln_cmd
    assert "--on-rebuild" in kiln_cmd
    assert cfg.on_rebuild_url in kiln_cmd

    agent_env = launched[1][1]
    assert agent_env is not None
    assert agent_env["AGENT_VAULT_DIR"] == str(cfg.vault_dir)
    assert agent_env["AGENT_SITE_BASE_URL"] == cfg.overlay_url
    assert agent_env["AGENT_SYNC_AFTER_COMMIT"] == "false"
    assert agent_env["AGENT_SYNC_REMOTE"] == "origin"
    assert "AGENT_SYNC_REMOTE_URL" not in agent_env
    assert "AGENT_SYNC_REMOTE_TOKEN" not in agent_env
    assert "FORGE_SYNC_REMOTE_URL" not in agent_env
    assert "FORGE_SYNC_REMOTE_TOKEN" not in agent_env


def test_wait_for_http_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeResponse:
        status_code = 503

        def __enter__(self) -> _FakeResponse:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
            _ = exc_type, exc, tb
            return False

    class _FakeClient:
        def __enter__(self) -> _FakeClient:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
            _ = exc_type, exc, tb
            return False

        def stream(self, method: str, url: str, timeout: float) -> _FakeResponse:
            _ = method, url, timeout
            return _FakeResponse()

    monkeypatch.setattr("forge_cli.processes.httpx.Client", lambda follow_redirects=True: _FakeClient())

    with pytest.raises(TimeoutError):
        wait_for_http("http://127.0.0.1:9999/health", timeout_s=0.01, interval_s=0.0)


def test_dev_starts_processes_in_order(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cfg = ForgeConfig(vault_dir=tmp_path / "vault", output_dir=tmp_path / "public", overlay_dir=tmp_path / "overlay")
    calls: list[str] = []

    class _FakeManager:
        def start_overlay(self, _config: ForgeConfig):
            calls.append("overlay")
            return type("M", (), {"process": _DummyProcess()})()

        def start_agent(self, _config: ForgeConfig):
            calls.append("agent")
            return type("M", (), {"process": _DummyProcess()})()

        def start_kiln(self, _config: ForgeConfig):
            calls.append("kiln")
            return type("M", (), {"process": _DummyProcess()})()

        def bootstrap_sync(self, _config: ForgeConfig):
            calls.append("bootstrap")

        def stop_all(self, timeout_s: float = 5.0):
            _ = timeout_s
            calls.append("stop")

    monkeypatch.setattr("forge_cli.commands.ProcessManager", _FakeManager)
    monkeypatch.setattr("forge_cli.commands.ForgeConfig.load", lambda _path: cfg)
    monkeypatch.setattr("forge_cli.commands._wait_for_processes", lambda _processes: None)

    runner = CliRunner()
    result = runner.invoke(app, ["dev", "--config", "forge.yaml"])

    assert result.exit_code == 0
    assert calls == ["overlay", "agent", "bootstrap", "kiln", "stop"]
    assert "startup-order: overlay -> agent -> kiln" in result.stdout


def test_dev_continues_when_bootstrap_sync_http_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cfg = ForgeConfig(vault_dir=tmp_path / "vault", output_dir=tmp_path / "public", overlay_dir=tmp_path / "overlay")
    calls: list[str] = []

    class _FakeManager:
        def start_overlay(self, _config: ForgeConfig):
            calls.append("overlay")
            return type("M", (), {"process": _DummyProcess()})()

        def start_agent(self, _config: ForgeConfig):
            calls.append("agent")
            return type("M", (), {"process": _DummyProcess()})()

        def bootstrap_sync(self, _config: ForgeConfig):
            calls.append("bootstrap")
            raise RuntimeError("boom")

        def start_kiln(self, _config: ForgeConfig):
            calls.append("kiln")
            return type("M", (), {"process": _DummyProcess()})()

        def stop_all(self, timeout_s: float = 5.0):
            _ = timeout_s
            calls.append("stop")

    monkeypatch.setattr("forge_cli.commands.ProcessManager", _FakeManager)
    monkeypatch.setattr("forge_cli.commands.ForgeConfig.load", lambda _path: cfg)
    monkeypatch.setattr("forge_cli.commands._wait_for_processes", lambda _processes: None)
    monkeypatch.setattr("forge_cli.commands.httpx.HTTPError", RuntimeError)

    runner = CliRunner()
    result = runner.invoke(app, ["dev", "--config", "forge.yaml"])

    assert result.exit_code == 0
    assert calls == ["overlay", "agent", "bootstrap", "kiln", "stop"]
    assert "sync bootstrap error: boom" in result.stderr


def test_dev_continues_when_bootstrap_sync_process_launch_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cfg = ForgeConfig(vault_dir=tmp_path / "vault", output_dir=tmp_path / "public", overlay_dir=tmp_path / "overlay")
    calls: list[str] = []

    class _FakeManager:
        def start_overlay(self, _config: ForgeConfig):
            calls.append("overlay")
            return type("M", (), {"process": _DummyProcess()})()

        def start_agent(self, _config: ForgeConfig):
            calls.append("agent")
            return type("M", (), {"process": _DummyProcess()})()

        def bootstrap_sync(self, _config: ForgeConfig):
            calls.append("bootstrap")
            raise RuntimeError("fatal-sync")

        def start_kiln(self, _config: ForgeConfig):
            calls.append("kiln")
            return type("M", (), {"process": _DummyProcess()})()

        def stop_all(self, timeout_s: float = 5.0):
            _ = timeout_s
            calls.append("stop")

    monkeypatch.setattr("forge_cli.commands.ProcessManager", _FakeManager)
    monkeypatch.setattr("forge_cli.commands.ForgeConfig.load", lambda _path: cfg)
    monkeypatch.setattr("forge_cli.commands._wait_for_processes", lambda _processes: None)
    monkeypatch.setattr("forge_cli.commands.ProcessLaunchError", RuntimeError)

    runner = CliRunner()
    result = runner.invoke(app, ["dev", "--config", "forge.yaml"])

    assert result.exit_code == 0
    assert calls == ["overlay", "agent", "bootstrap", "kiln", "stop"]
    assert "sync bootstrap failed: fatal-sync" in result.stderr


def test_serve_starts_only_overlay(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cfg = ForgeConfig(vault_dir=tmp_path / "vault", output_dir=tmp_path / "public", overlay_dir=tmp_path / "overlay")
    calls: list[str] = []

    class _FakeManager:
        def start_overlay(self, _config: ForgeConfig):
            calls.append("overlay")
            return type("M", (), {"process": _DummyProcess()})()

        def stop_all(self, timeout_s: float = 5.0):
            _ = timeout_s
            calls.append("stop")

    monkeypatch.setattr("forge_cli.commands.ProcessManager", _FakeManager)
    monkeypatch.setattr("forge_cli.commands.ForgeConfig.load", lambda _path: cfg)
    monkeypatch.setattr("forge_cli.commands._wait_for_processes", lambda _processes: None)

    runner = CliRunner()
    result = runner.invoke(app, ["serve", "--config", "forge.yaml"])

    assert result.exit_code == 0
    assert calls == ["overlay", "stop"]


def test_generate_invokes_kiln_generate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cfg = ForgeConfig(
        vault_dir=tmp_path / "vault",
        output_dir=tmp_path / "public",
        overlay_dir=tmp_path / "overlay",
        kiln_bin="kiln-custom",
        kiln_theme="nord",
        kiln_font="merriweather",
        kiln_lang="it",
        kiln_site_name="Team Notes",
    )
    invoked: list[list[str]] = []

    def fake_run(command: list[str], check: bool) -> subprocess.CompletedProcess[bytes]:
        assert check is True
        invoked.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("forge_cli.commands.ForgeConfig.load", lambda _path: cfg)
    monkeypatch.setattr("forge_cli.commands.subprocess.run", fake_run)

    runner = CliRunner()
    result = runner.invoke(app, ["generate", "--config", "forge.yaml"])

    assert result.exit_code == 0
    assert invoked
    assert invoked[0][0:2] == ["kiln-custom", "generate"]
    assert "--input" in invoked[0]
    assert "--output" in invoked[0]
    assert "--name" in invoked[0]
    assert "Team Notes" in invoked[0]


def test_init_scaffolds_directories_and_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    vault_dir = tmp_path / "vault"
    output_dir = tmp_path / "public"
    overlay_dir = tmp_path / "overlay"
    config_path = tmp_path / "forge.yaml"

    monkeypatch.setenv("FORGE_VAULT_DIR", str(vault_dir))
    monkeypatch.setenv("FORGE_OUTPUT_DIR", str(output_dir))
    monkeypatch.setenv("FORGE_OVERLAY_DIR", str(overlay_dir))

    runner = CliRunner()
    result = runner.invoke(app, ["init", "--config", str(config_path)])

    assert result.exit_code == 0
    assert vault_dir.exists()
    assert output_dir.exists()
    assert overlay_dir.exists()
    assert config_path.exists()

    parsed = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert parsed["vault_dir"] == str(vault_dir)
    assert parsed["output_dir"] == str(output_dir)
    assert parsed["overlay_dir"] == str(overlay_dir)
    assert parsed["sync"]["after_commit"] is False
    assert parsed["sync"]["remote"] == "origin"


def test_init_requires_force_when_config_exists(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config_path = tmp_path / "forge.yaml"
    original = "vault_dir: ./vault\n"
    config_path.write_text(original, encoding="utf-8")
    monkeypatch.setenv("FORGE_VAULT_DIR", str(tmp_path / "vault"))
    monkeypatch.setenv("FORGE_OUTPUT_DIR", str(tmp_path / "public"))
    monkeypatch.setenv("FORGE_OVERLAY_DIR", str(tmp_path / "overlay"))

    runner = CliRunner()
    result = runner.invoke(app, ["init", "--config", str(config_path)])

    assert result.exit_code == 2
    assert config_path.read_text(encoding="utf-8") == original
