#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

from __future__ import annotations

from pathlib import Path
import subprocess


def main() -> int:
    script = Path(__file__).resolve().with_name("cleanup.sh")
    repo_root = script.parents[2]
    completed = subprocess.run(["bash", str(script)], cwd=repo_root, check=False)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
