#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

from __future__ import annotations

from lib import start_stack


def main() -> int:
    try:
        return start_stack()
    except RuntimeError as exc:
        print(exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
