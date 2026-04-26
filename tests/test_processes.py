from __future__ import annotations

import io

from forge_cli.processes import _stream_prefixed_logs


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
