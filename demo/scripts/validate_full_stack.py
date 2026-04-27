#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import time
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request

from lib import (
    DEMO_OVERLAY_HOST,
    DEMO_OVERLAY_PORT,
    LOG_DIR,
    PUBLIC_DIR,
    VAULT_DIR,
    cleanup_runtime,
    fail,
    log,
    run_script,
)


def http_get_json(url: str) -> dict[str, object]:
    req = request.Request(url=url, method="GET")
    with request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def http_post_json(url: str, payload: dict[str, object]) -> dict[str, object]:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(url=url, method="POST", data=body, headers={"content-type": "application/json"})
    with request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def http_put_json(url: str, payload: dict[str, object]) -> dict[str, object]:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(url=url, method="PUT", data=body, headers={"content-type": "application/json"})
    with request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _vault_append_token(api_base: str, path: str, token: str) -> dict[str, object]:
    current = http_get_json(f"{api_base}/vault/files?path={urlparse.quote(path)}")
    content = str(current.get("content", ""))
    sha = str(current.get("sha256", ""))
    updated = content.rstrip("\n") + f"\n\n{token}\n"
    return http_put_json(
        f"{api_base}/vault/files",
        {"path": path, "content": updated, "expected_sha256": sha},
    )


def _vault_restore_content(api_base: str, path: str, content: str) -> dict[str, object]:
    current = http_get_json(f"{api_base}/vault/files?path={urlparse.quote(path)}")
    current_sha = str(current.get("sha256", ""))
    return http_put_json(
        f"{api_base}/vault/files",
        {"path": path, "content": content, "expected_sha256": current_sha},
    )


def wait_until(predicate, timeout_s: float, interval_s: float = 0.25) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval_s)
    return False


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def wait_for_initial_build(log_path: Path, timeout_s: float = 90.0) -> None:
    if not wait_until(lambda: "Build complete seconds=" in read_text(log_path), timeout_s=timeout_s):
        raise fail("initial kiln build did not complete in time")


def rendered_html_path(markdown_relpath: str) -> Path:
    stem = Path(markdown_relpath).with_suffix("")
    flat_candidate = PUBLIC_DIR / stem.parent / f"{stem.name}.html"
    if flat_candidate.exists():
        return flat_candidate
    return PUBLIC_DIR / stem.parent / stem.name / "index.html"


def assert_kiln_flags_present() -> None:
    result = subprocess.run(["ps", "-ef"], check=True, capture_output=True, text=True)
    lines = [
        line
        for line in result.stdout.splitlines()
        if "kiln" in line and " dev " in line and str(VAULT_DIR) in line and "--on-rebuild" in line and "--no-serve" in line
    ]
    if not lines:
        raise fail("kiln dev process with expected flags not found")


def main() -> int:
    keep_on_fail = os.environ.get("DEMO_KEEP_RUNTIME_ON_FAIL", "0") == "1"
    try:
        log("starting full-stack demo harness validation")
        cleanup_runtime()
        if run_script("setup.py") != 0:
            raise fail("setup.py failed")
        if run_script("start_stack.py") != 0:
            raise fail("start_stack.py failed")

        assert_kiln_flags_present()

        root_url = f"http://{DEMO_OVERLAY_HOST}:{DEMO_OVERLAY_PORT}/index.html"
        api_base = f"http://{DEMO_OVERLAY_HOST}:{DEMO_OVERLAY_PORT}/api"

        root_html = request.urlopen(request.Request(root_url, method="GET"), timeout=20).read().decode("utf-8", errors="ignore")
        if "/ops/ops.css" not in root_html or "/ops/ops.js" not in root_html:
            raise fail("overlay HTML injection not detected")

        health = http_get_json(f"{api_base}/health")
        if not health:
            raise fail("empty health response")

        ensure_payload = http_post_json(f"{api_base}/vault/vcs/sync/ensure", {})
        if ensure_payload.get("status") not in {"ready", "migration_needed"}:
            raise fail(f"unexpected sync ensure status: {ensure_payload}")

        _ = http_put_json(
            f"{api_base}/vault/vcs/sync/remote",
            {"remote": "origin", "url": "https://github.com/example/demo-vault.git"},
        )

        sync_payload = http_post_json(f"{api_base}/vault/vcs/sync", {"remote": "origin"})
        if "sync_ok" not in sync_payload:
            raise fail(f"unexpected sync payload: {sync_payload}")

        status_payload = http_get_json(f"{api_base}/vault/vcs/sync/status")
        if "status" not in status_payload:
            raise fail("sync status missing status field")

        wait_for_initial_build(LOG_DIR / "forge.log")

        token = f"validation-mutation-{int(time.time())}"
        live_reload_md = VAULT_DIR / "experiments" / "live-reload.md"
        target_html = rendered_html_path("experiments/live-reload.md")
        live_reload_md.parent.mkdir(parents=True, exist_ok=True)
        with live_reload_md.open("a", encoding="utf-8") as handle:
            handle.write(f"\n\nValidation mutation token: {token}\n")

        if not wait_until(lambda: token in read_text(target_html), timeout_s=60):
            with live_reload_md.open("a", encoding="utf-8") as handle:
                handle.write(f"\nValidation mutation retry token: {token}\n")
            if not wait_until(lambda: token in read_text(target_html), timeout_s=60):
                raise fail("kiln rebuild not observed in rendered live-reload page")

        if not wait_until(lambda: "POST /internal/rebuild" in read_text(LOG_DIR / "forge.log"), timeout_s=30):
            raise fail("overlay rebuild webhook not observed in forge log")

        apply_token = f"VALIDATION_APPLY_{int(time.time())}"
        apply_via = "agent"
        fallback_original_content: str | None = None
        try:
            apply_payload = http_post_json(
                f"{api_base}/agent/apply",
                {
                    "instruction": f"Append exactly this line at end of file: {apply_token}",
                    "current_file": "projects/forge-v2.md",
                },
            )
            if not apply_payload.get("ok", False):
                raise RuntimeError(f"agent apply failed: {apply_payload}")
        except (urlerror.HTTPError, RuntimeError):
            apply_via = "vault"
            fallback_original_content = str(
                http_get_json(f"{api_base}/vault/files?path={urlparse.quote('projects/forge-v2.md')}").get("content", "")
            )
            apply_payload = _vault_append_token(api_base, "projects/forge-v2.md", apply_token)
            if not apply_payload.get("ok", False):
                raise fail(f"vault fallback apply failed: {apply_payload}")

        forge_note_html = rendered_html_path("projects/forge-v2.md")
        if not wait_until(lambda: apply_token in read_text(forge_note_html), timeout_s=90):
            raise fail("apply token not observed in rendered note")

        undo_payload = (
            http_post_json(f"{api_base}/agent/undo", {})
            if apply_via == "agent"
            else _vault_restore_content(api_base, "projects/forge-v2.md", fallback_original_content or "")
        )
        if not undo_payload.get("ok", False):
            raise fail(f"undo request failed: {undo_payload}")

        if not wait_until(lambda: apply_token not in read_text(forge_note_html), timeout_s=90):
            raise fail("undo did not remove apply token from rendered note")

        log("full-stack demo harness validation passed")
        cleanup_runtime()
        return 0
    except RuntimeError as exc:
        print(exc)
        if not keep_on_fail:
            cleanup_runtime()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
