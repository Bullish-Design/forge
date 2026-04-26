from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_demo_lib():
    repo_root = Path(__file__).resolve().parents[1]
    module_path = repo_root / "demo" / "scripts" / "lib.py"
    spec = importlib.util.spec_from_file_location("demo_lib", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_stop_pid_targets_process_group(monkeypatch) -> None:
    lib = _load_demo_lib()
    calls: list[tuple[str, int, int]] = []

    monkeypatch.setattr(lib.os, "getpgid", lambda pid: 4321)

    def fake_killpg(pgid: int, sig: int) -> None:
        calls.append(("killpg", pgid, sig))

    monkeypatch.setattr(lib.os, "killpg", fake_killpg)
    monkeypatch.setattr(lib, "process_alive", lambda _pid: False)

    lib.stop_pid(999)

    assert calls
    assert calls[0][0] == "killpg"
    assert calls[0][1] == 4321


def test_cleanup_runtime_attempts_port_holder_cleanup(monkeypatch, tmp_path: Path) -> None:
    lib = _load_demo_lib()
    monkeypatch.setattr(lib, "RUNTIME_DIR", tmp_path / "runtime")
    monkeypatch.setattr(lib, "PID_FILE", tmp_path / "runtime" / "pids.env")
    monkeypatch.setattr(lib, "parse_pid_file", lambda: {})

    called_ports: list[tuple[int, ...]] = []
    monkeypatch.setattr(lib, "_kill_port_holders", lambda *ports: called_ports.append(ports))

    rc = lib.cleanup_runtime()

    assert rc == 0
    assert called_ports == [(lib.DEMO_OVERLAY_PORT, lib.DEMO_API_PORT)]
