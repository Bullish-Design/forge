#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import time
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(cmd, text=True, capture_output=True, check=False)
    if check and completed.returncode != 0:
        raise RuntimeError(
            f"command failed: {' '.join(cmd)}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    return completed


def http_get_json(url: str, timeout: float = 20.0) -> dict[str, object]:
    req = request.Request(url, method="GET")
    with request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_get_text(url: str, timeout: float = 20.0) -> str:
    req = request.Request(url, method="GET")
    with request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def http_post_json(url: str, payload: dict[str, object], timeout: float = 30.0) -> dict[str, object]:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=body, method="POST", headers={"content-type": "application/json"})
    with request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_put_json(url: str, payload: dict[str, object], timeout: float = 30.0) -> dict[str, object]:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=body, method="PUT", headers={"content-type": "application/json"})
    with request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def wait_until(predicate, timeout_s: float, interval_s: float = 0.5) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval_s)
    return False


def wait_http_ok(url: str, timeout_s: float = 180.0) -> None:
    def _ready() -> bool:
        try:
            _ = http_get_json(url, timeout=5.0)
            return True
        except Exception:
            return False

    if not wait_until(_ready, timeout_s=timeout_s, interval_s=1.0):
        raise RuntimeError(f"timed out waiting for {url}")


def ensure_contains(url: str, needle: str, timeout_s: float = 90.0) -> None:
    if not wait_until(lambda: needle in http_get_text(url, timeout=5.0), timeout_s=timeout_s, interval_s=1.0):
        raise RuntimeError(f"timed out waiting for {needle!r} at {url}")


def ensure_contains_any(urls: list[str], needle: str, timeout_s: float = 90.0) -> str:
    def _check() -> str | None:
        for url in urls:
            try:
                if needle in http_get_text(url, timeout=5.0):
                    return url
            except Exception:
                continue
        return None

    found: dict[str, str | None] = {"url": None}
    ok = wait_until(lambda: (found.__setitem__("url", _check()) or found["url"] is not None), timeout_s=timeout_s, interval_s=1.0)
    if not ok or found["url"] is None:
        raise RuntimeError(f"timed out waiting for {needle!r} at any of: {urls}")
    return str(found["url"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate forge docker stack end-to-end.")
    parser.add_argument("--compose-file", default="docker/docker-compose.yml")
    parser.add_argument("--keep-running-on-fail", action="store_true")
    parser.add_argument("--skip-build", action="store_true")
    return parser.parse_args()


def validate_runtime_tools(compose_file: str) -> None:
    version_jj = run(["docker", "compose", "-f", compose_file, "exec", "-T", "forge", "jj", "--version"])
    version_kiln = run(["docker", "compose", "-f", compose_file, "exec", "-T", "forge", "kiln", "version"])
    print(version_jj.stdout.strip())
    print(version_kiln.stdout.strip())


def main() -> int:
    args = parse_args()
    port = int(os.environ.get("FORGE_PORT", "8080"))
    base = f"http://127.0.0.1:{port}"
    api = f"{base}/api"

    up_cmd = ["docker", "compose", "-f", args.compose_file, "up", "-d"]
    if not args.skip_build:
        up_cmd.append("--build")

    try:
        run(["docker", "compose", "-f", args.compose_file, "down"], check=False)
        run(["docker", "rm", "-f", "forge-app", "forge-tailscale"], check=False)
        print("[docker-validate] starting stack...")
        run(up_cmd)

        print("[docker-validate] validating runtime tools...")
        validate_runtime_tools(args.compose_file)

        print("[docker-validate] waiting for API health...")
        wait_http_ok(f"{api}/health", timeout_s=240.0)

        print("[docker-validate] checking sync endpoints...")
        ensure_payload = http_post_json(f"{api}/vault/vcs/sync/ensure", {})
        if ensure_payload.get("status") not in {"ready", "migration_needed"}:
            raise RuntimeError(f"unexpected sync ensure payload: {ensure_payload}")
        status_payload = http_get_json(f"{api}/vault/vcs/sync/status")
        if "status" not in status_payload:
            raise RuntimeError(f"unexpected sync status payload: {status_payload}")

        print("[docker-validate] testing write -> rebuild -> undo flow...")
        path = "docker-validation.md"
        token = f"docker-validation-token-{int(time.time())}"
        write = http_put_json(f"{api}/vault/files", {"path": path, "content": f"# Docker Validation\n\n{token}\n"})
        if not write.get("ok", False):
            raise RuntimeError(f"write failed: {write}")

        candidate_urls = [
            f"{base}/docker-validation",
            f"{base}/docker-validation/",
            f"{base}/docker-validation.html",
        ]
        print("[docker-validate] checking overlay injection on rendered page...")
        rendered_url = ensure_contains_any(candidate_urls, "/ops/ops.css", timeout_s=180.0)
        ensure_contains(rendered_url, "/ops/ops.js", timeout_s=180.0)
        ensure_contains(rendered_url, token, timeout_s=180.0)

        undo = http_post_json(f"{api}/vault/undo", {})
        if not undo.get("ok", False):
            raise RuntimeError(f"undo failed: {undo}")

        def _token_gone() -> bool:
            try:
                for url in candidate_urls:
                    try:
                        if token in http_get_text(url, timeout=5.0):
                            return False
                        return True
                    except urlerror.HTTPError:
                        continue
                return True
            except urlerror.HTTPError as exc:
                return exc.code == 404

        if not wait_until(_token_gone, timeout_s=120.0, interval_s=1.0):
            raise RuntimeError("undo did not propagate to rendered content")

        print("[docker-validate] docker validation passed")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"[docker-validate] FAILED: {exc}")
        run(["docker", "compose", "-f", args.compose_file, "ps"], check=False)
        run(["docker", "compose", "-f", args.compose_file, "logs", "--tail", "200"], check=False)
        if args.keep_running_on_fail:
            print("[docker-validate] keeping stack running for inspection")
            return 1
        run(["docker", "compose", "-f", args.compose_file, "down"], check=False)
        return 1
    finally:
        if not args.keep_running_on_fail:
            run(["docker", "compose", "-f", args.compose_file, "down"], check=False)


if __name__ == "__main__":
    raise SystemExit(main())
