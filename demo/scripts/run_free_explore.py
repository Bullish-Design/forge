#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

from __future__ import annotations

import os
import sys
import termios
import tty

from lib import DEMO_OVERLAY_HOST, DEMO_OVERLAY_PORT, cleanup_runtime, run_script


def read_single_key() -> str:
    if not sys.stdin.isatty():
        line = input()
        return line[:1] if line else "\n"

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def print_urls() -> None:
    print(f"Site home:      http://{DEMO_OVERLAY_HOST}:{DEMO_OVERLAY_PORT}/index.html")
    print(f"Capability map: http://{DEMO_OVERLAY_HOST}:{DEMO_OVERLAY_PORT}/references/kiln-capabilities")
    print(f"Mutation note:  http://{DEMO_OVERLAY_HOST}:{DEMO_OVERLAY_PORT}/projects/forge-v2")


def main() -> int:
    keep_running = False
    try:
        print("Starting Forge free-explore demo (real orchestrator + obsidian-agent).")
        cleanup_runtime()
        if run_script("setup.py") != 0:
            return 1
        if run_script("start_stack.py") != 0:
            return 1

        print("")
        print("Free-explore stack is live.")
        print(f"LLM upstream: {os.environ.get('AGENT_LLM_BASE_URL', os.environ.get('DEMO_VLLM_BASE_URL', 'http://remora-server:8000/v1'))}")
        print_urls()
        print("")
        print("Use the overlay panel to run prompt-based apply/undo actions through real obsidian-agent.")
        print("Press k to keep stack running and exit, or any other key to cleanup.")
        if read_single_key().strip().lower() == "k":
            keep_running = True
            print("\nLeaving free-explore stack running.")
            print("When done: uv run demo/scripts/cleanup.py")
    finally:
        if not keep_running:
            cleanup_runtime()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
