from __future__ import annotations

from pathlib import Path

import pytest

from forge_cli.config import ForgeConfig
from forge_cli.processes import ProcessLaunchError, ProcessManager


class _Response:
    def __init__(self, payload: dict[str, object], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def json(self) -> dict[str, object]:
        return self._payload


def _cfg(tmp_path: Path) -> ForgeConfig:
    return ForgeConfig(
        vault_dir=tmp_path / "vault",
        output_dir=tmp_path / "public",
        overlay_dir=tmp_path / "overlay",
        sync_remote="origin",
        sync_remote_url="https://github.com/example/repo.git",
        sync_remote_token="token-xyz",
    )


def test_bootstrap_happy_path_calls_ensure_remote_sync(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    manager = ProcessManager()
    cfg = _cfg(tmp_path)
    calls: list[tuple[str, str, dict[str, object] | None, float]] = []

    def fake_post(url: str, json: dict[str, object] | None = None, timeout: float = 0) -> _Response:
        calls.append(("POST", url, json, timeout))
        if url.endswith("/ensure"):
            return _Response({"status": "ready"})
        if url.endswith("/sync"):
            return _Response({"sync_ok": True})
        raise AssertionError(f"unexpected post url: {url}")

    def fake_put(url: str, json: dict[str, object] | None = None, timeout: float = 0) -> _Response:
        calls.append(("PUT", url, json, timeout))
        return _Response({"ok": True})

    monkeypatch.setattr("forge_cli.processes.httpx.post", fake_post)
    monkeypatch.setattr("forge_cli.processes.httpx.put", fake_put)

    manager.bootstrap_sync(cfg)

    assert calls[0] == ("POST", f"{cfg.agent_url}/api/vault/vcs/sync/ensure", None, 30.0)
    assert calls[1] == (
        "PUT",
        f"{cfg.agent_url}/api/vault/vcs/sync/remote",
        {
            "url": "https://github.com/example/repo.git",
            "remote": "origin",
            "token": "token-xyz",
        },
        30.0,
    )
    assert calls[2] == (
        "POST",
        f"{cfg.agent_url}/api/vault/vcs/sync",
        {"remote": "origin"},
        120.0,
    )


def test_bootstrap_raises_on_ensure_error_status(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    manager = ProcessManager()
    cfg = _cfg(tmp_path)

    monkeypatch.setattr(
        "forge_cli.processes.httpx.post",
        lambda url, json=None, timeout=0: _Response({"status": "error", "detail": "bad state"})
        if str(url).endswith("/ensure")
        else _Response({"sync_ok": True}),
    )
    monkeypatch.setattr("forge_cli.processes.httpx.put", lambda *args, **kwargs: _Response({"ok": True}))

    with pytest.raises(ProcessLaunchError, match="bad state"):
        manager.bootstrap_sync(cfg)


def test_bootstrap_migration_needed_logs_and_skips_remote_sync(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manager = ProcessManager()
    cfg = _cfg(tmp_path)
    put_called = False
    sync_called = False

    def fake_post(url: str, json: dict[str, object] | None = None, timeout: float = 0) -> _Response:
        nonlocal sync_called
        _ = json, timeout
        if url.endswith("/ensure"):
            return _Response({"status": "migration_needed", "detail": "git-only with uncommitted changes"})
        sync_called = True
        return _Response({"sync_ok": True})

    def fake_put(url: str, json: dict[str, object] | None = None, timeout: float = 0) -> _Response:
        nonlocal put_called
        _ = url, json, timeout
        put_called = True
        return _Response({"ok": True})

    monkeypatch.setattr("forge_cli.processes.httpx.post", fake_post)
    monkeypatch.setattr("forge_cli.processes.httpx.put", fake_put)

    manager.bootstrap_sync(cfg)

    stderr = capsys.readouterr().err
    assert "migration needed" in stderr
    assert put_called is False
    assert sync_called is False


def test_bootstrap_conflict_logs_warning(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    manager = ProcessManager()
    cfg = _cfg(tmp_path)

    def fake_post(url: str, json: dict[str, object] | None = None, timeout: float = 0) -> _Response:
        _ = json, timeout
        if url.endswith("/ensure"):
            return _Response({"status": "ready"})
        return _Response({"sync_ok": False, "conflict": True, "conflict_bookmark": "conflicts/main-123"})

    monkeypatch.setattr("forge_cli.processes.httpx.post", fake_post)
    monkeypatch.setattr("forge_cli.processes.httpx.put", lambda *args, **kwargs: _Response({"ok": True}))

    manager.bootstrap_sync(cfg)

    stderr = capsys.readouterr().err
    assert "initial sync conflict" in stderr
    assert "conflicts/main-123" in stderr


def test_bootstrap_skips_when_remote_not_configured(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    manager = ProcessManager()
    cfg = ForgeConfig(vault_dir=tmp_path / "vault", output_dir=tmp_path / "public", overlay_dir=tmp_path / "overlay")

    def fail(*_args, **_kwargs):
        raise AssertionError("httpx should not be called")

    monkeypatch.setattr("forge_cli.processes.httpx.post", fail)
    monkeypatch.setattr("forge_cli.processes.httpx.put", fail)

    manager.bootstrap_sync(cfg)
