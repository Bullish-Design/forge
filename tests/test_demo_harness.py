from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.integration
def test_demo_harness_full_stack_validation() -> None:
    if os.environ.get("FORGE_RUN_DEMO_VALIDATION") != "1":
        pytest.skip("Set FORGE_RUN_DEMO_VALIDATION=1 to run full demo harness validation.")

    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "demo" / "scripts" / "validate_full_stack.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )

    if result.returncode != 0:
        details = "\n".join(
            [
                "demo harness validation failed",
                "--- stdout ---",
                result.stdout,
                "--- stderr ---",
                result.stderr,
            ]
        )
        raise AssertionError(details)
