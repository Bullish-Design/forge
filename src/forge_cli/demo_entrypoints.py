from __future__ import annotations

from pathlib import Path
import subprocess
import sys


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _script_path(name: str) -> Path:
    path = _repo_root() / "demo" / "scripts" / name
    if not path.exists():
        raise FileNotFoundError(f"demo script not found: {path}")
    return path


def _run(name: str) -> int:
    script = _script_path(name)
    return _run_path(script)


def _run_path(path: Path) -> int:
    completed = subprocess.run([sys.executable, str(path)], cwd=_repo_root(), check=False)
    return completed.returncode


def demo_setup() -> int:
    return _run("setup.py")


def demo_start() -> int:
    return _run("start_stack.py")


def demo_validate() -> int:
    return _run("validate_full_stack.py")


def demo_run() -> int:
    return _run("run_demo.py")


def demo_cleanup() -> int:
    return _run("cleanup.py")


def demo_start_free_explore() -> int:
    return _run("start_stack_free_explore.py")


def demo_run_free_explore() -> int:
    return _run("run_free_explore.py")


def demo_run_production_ui() -> int:
    return _run("run_demo_production_ui.py")


def docker_up() -> int:
    return _run_path(_repo_root() / "docker" / "up.py")


def docker_down() -> int:
    return _run_path(_repo_root() / "docker" / "down.py")


def docker_validate() -> int:
    return _run_path(_repo_root() / "docker" / "validate.py")
