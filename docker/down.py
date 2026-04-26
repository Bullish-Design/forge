#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

from __future__ import annotations

import argparse
import subprocess


def main() -> int:
    parser = argparse.ArgumentParser(description="Stop docker compose stack for forge + tailscale.")
    parser.add_argument("--compose-file", default="docker/docker-compose.yml")
    args = parser.parse_args()

    completed = subprocess.run(["docker", "compose", "-f", args.compose_file, "down"], check=False)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
