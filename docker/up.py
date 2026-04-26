#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

from __future__ import annotations

import argparse
import subprocess


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and start docker compose stack for forge + tailscale.")
    parser.add_argument("--compose-file", default="docker/docker-compose.yml")
    parser.add_argument("--skip-build", action="store_true")
    args = parser.parse_args()

    cmd = ["docker", "compose", "-f", args.compose_file, "up", "-d"]
    if not args.skip_build:
        cmd.append("--build")

    completed = subprocess.run(cmd, check=False)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
