#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

from __future__ import annotations

from lib import fail, setup_runtime


def main() -> int:
    try:
        setup_runtime()
        return 0
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    raise SystemExit(main())
