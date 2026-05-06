from __future__ import annotations

import io
from pathlib import Path

from forge_cli.processes import ProcessManager, _stream_prefixed_logs


def test_stream_prefixed_logs_flushes_each_line() -> None:
    stream = io.StringIO("line-1\nline-2\n")
    output = io.StringIO()
    flush_calls: list[int] = []

    def _flush() -> None:
        flush_calls.append(1)

    output.flush = _flush  # type: ignore[method-assign]

    import forge_cli.processes as processes

    original_stdout = processes.sys.stdout
    try:
        processes.sys.stdout = output
        _stream_prefixed_logs("unit", stream)
    finally:
        processes.sys.stdout = original_stdout

    assert output.getvalue() == "[unit] line-1\n[unit] line-2\n"
    assert len(flush_calls) == 2


def test_resolve_overlay_dir_prefers_configured_when_assets_present(tmp_path: Path) -> None:
    configured = tmp_path / "overlay"
    configured.mkdir(parents=True)
    (configured / "ops.js").write_text("", encoding="utf-8")
    (configured / "ops.css").write_text("", encoding="utf-8")

    resolved = ProcessManager.resolve_overlay_dir(configured)
    assert resolved == configured


def test_resolve_overlay_dir_falls_back_to_repo_overlay_when_missing_assets(tmp_path: Path) -> None:
    configured = tmp_path / "overlay"
    configured.mkdir(parents=True)

    resolved = ProcessManager.resolve_overlay_dir(configured)

    assert resolved != configured
    assert (resolved / "ops.js").exists()
    assert (resolved / "ops.css").exists()
