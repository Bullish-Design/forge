from __future__ import annotations

import io
from pathlib import Path

import pytest
from typer.testing import CliRunner

from forge_cli.commands import app
from forge_cli.config import ForgeConfig
from forge_cli.processes import ProcessManager, wait_for_http


def test_dev_prints_startup_order(tmp_path: Path) -> None:
    cfg = tmp_path / "forge.yaml"
    cfg.write_text("vault_dir: ./vault\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(app, ["dev", "--config", str(cfg)])

    assert result.exit_code == 0
    assert "startup-order: overlay -> agent -> kiln" in result.stdout


class _DummyProcess:
    def __init__(self) -> None:
        self.stdout: io.StringIO | None = io.StringIO("")
        self._alive = True

    def poll(self) -> int | None:
        return None if self._alive else 0

    def terminate(self) -> None:
        self._alive = False

    def wait(self, timeout: float | None = None) -> int:
        return 0

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

    def fake_wait(url: str, timeout_s: float = 20.0, interval_s: float = 0.2, expected_status: int = 200) -> None:
        _ = timeout_s, interval_s, expected_status
        waited.append(url)

    monkeypatch.setattr("forge_cli.processes.wait_for_http", fake_wait)

    manager = ProcessManager(popen_factory=fake_popen)  # type: ignore[arg-type]
    manager.start_overlay(cfg)
    manager.start_agent(cfg)
    manager.start_kiln(cfg)
    manager.stop_all()

    assert [call[0][0] for call in launched] == ["forge-overlay", "obsidian-agent", "kiln"]
    assert waited == [f"{cfg.overlay_url}/ops/events", f"{cfg.agent_url}/api/health"]

    kiln_cmd = launched[2][0]
    assert "--no-serve" in kiln_cmd
    assert "--on-rebuild" in kiln_cmd
    assert cfg.on_rebuild_url in kiln_cmd

    agent_env = launched[1][1]
    assert agent_env is not None
    assert agent_env["AGENT_VAULT_DIR"] == str(cfg.vault_dir)
    assert agent_env["AGENT_SITE_BASE_URL"] == cfg.overlay_url


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
