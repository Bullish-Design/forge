#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
PROD_OVERLAY_DIR = REPO_ROOT / "src" / "overlay"


def main() -> int:
    if not (PROD_OVERLAY_DIR / "ops.js").exists() or not (PROD_OVERLAY_DIR / "ops.css").exists():
        print(f"[demo][error] missing production overlay assets in {PROD_OVERLAY_DIR}")
        return 1

    env = os.environ.copy()
    env["DEMO_OVERLAY_TEMPLATE_DIR"] = str(PROD_OVERLAY_DIR)

    cmd = [sys.executable, str(SCRIPT_DIR / "run_demo.py")]
    completed = subprocess.run(cmd, cwd=REPO_ROOT, env=env, check=False)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
