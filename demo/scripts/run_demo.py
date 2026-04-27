#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import tty
import termios
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request


SCRIPT_DIR = Path(__file__).resolve().parent
DEMO_DIR = SCRIPT_DIR.parent
RUNTIME_DIR = Path(os.environ.get("DEMO_RUNTIME_DIR", str(DEMO_DIR / "runtime")))
VAULT_DIR = RUNTIME_DIR / "vault"
PUBLIC_DIR = RUNTIME_DIR / "public"
LOG_DIR = RUNTIME_DIR / "logs"
PID_FILE = RUNTIME_DIR / "pids.env"

DEMO_OVERLAY_HOST = os.environ.get("DEMO_OVERLAY_HOST", "127.0.0.1")
DEMO_OVERLAY_PORT = int(os.environ.get("DEMO_OVERLAY_PORT", "18080"))
AUTO_ADVANCE = os.environ.get("AUTO_ADVANCE", "0") == "1"

KEEP_STACK_RUNNING = False


def log(message: str) -> None:
    print(f"[demo] {message}")


def fail(message: str) -> RuntimeError:
    return RuntimeError(f"[demo][error] {message}")


def print_rule() -> None:
    print("\n" + "=" * 65)


def step_header(step_num: str, title: str) -> None:
    print_rule()
    print(f"Step {step_num}: {title}")
    print_rule()


def pause_step(prompt: str) -> None:
    if AUTO_ADVANCE:
        log(f"{prompt} [auto-advance]")
        time.sleep(1)
        return
    print(f"\n{prompt}", end="", flush=True)
    read_single_key()
    print("")


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


def run_helper_script(name: str, quiet: bool = False) -> None:
    script_path = SCRIPT_DIR / name
    if quiet:
        subprocess.run(
            [sys.executable, str(script_path)],
            cwd=DEMO_DIR.parent,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return

    subprocess.run([sys.executable, str(script_path)], cwd=DEMO_DIR.parent, check=True)


def read_pid_file() -> dict[str, int]:
    if not PID_FILE.exists():
        raise fail(f"missing pid file: {PID_FILE}")

    pids: dict[str, int] = {}
    for line in PID_FILE.read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or not value:
            continue
        try:
            pids[key] = int(value)
        except ValueError as exc:
            raise fail(f"invalid pid entry in {PID_FILE}: {line}") from exc
    return pids


def http_get(url: str) -> bytes:
    req = request.Request(url=url, method="GET")
    with request.urlopen(req, timeout=15) as response:
        return response.read()


def http_post_json(url: str, payload: dict[str, object]) -> bytes:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url=url,
        method="POST",
        data=body,
        headers={"content-type": "application/json"},
    )
    with request.urlopen(req, timeout=20) as response:
        return response.read()


def http_put_json(url: str, payload: dict[str, object]) -> bytes:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url=url,
        method="PUT",
        data=body,
        headers={"content-type": "application/json"},
    )
    with request.urlopen(req, timeout=20) as response:
        return response.read()


def vault_append_token(api_base: str, path: str, token: str) -> dict[str, object]:
    payload = json.loads(http_get(f"{api_base}/vault/files?path={urlparse.quote(path)}").decode("utf-8"))
    content = str(payload.get("content", ""))
    sha = str(payload.get("sha256", ""))
    updated = content.rstrip("\n") + f"\n\n{token}\n"
    return json.loads(
        http_put_json(
            f"{api_base}/vault/files",
            {"path": path, "content": updated, "expected_sha256": sha},
        ).decode("utf-8")
    )


def vault_restore_content(api_base: str, path: str, original_content: str) -> dict[str, object]:
    payload = json.loads(http_get(f"{api_base}/vault/files?path={urlparse.quote(path)}").decode("utf-8"))
    sha = str(payload.get("sha256", ""))
    return json.loads(
        http_put_json(
            f"{api_base}/vault/files",
            {"path": path, "content": original_content, "expected_sha256": sha},
        ).decode("utf-8")
    )


def wait_until(predicate, timeout_s: float, interval_s: float = 0.25) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval_s)
    return False


def wait_for_initial_build(log_path: Path, timeout_s: float = 90.0) -> None:
    if not wait_until(lambda: "Build complete seconds=" in read_text(log_path), timeout_s=timeout_s):
        raise fail("initial kiln build did not complete in time")


def count_pattern(path: Path, pattern: str) -> int:
    if not path.exists():
        return 0
    text = path.read_text(encoding="utf-8", errors="ignore")
    return len(re.findall(pattern, text))


def count_substring(path: Path, needle: str) -> int:
    if not path.exists():
        return 0
    text = path.read_text(encoding="utf-8", errors="ignore")
    return text.count(needle)


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def rendered_html_path(markdown_relpath: str) -> Path:
    stem = Path(markdown_relpath).with_suffix("")
    flat_candidate = PUBLIC_DIR / stem.parent / f"{stem.name}.html"
    if flat_candidate.exists():
        return flat_candidate
    return PUBLIC_DIR / stem.parent / stem.name / "index.html"


def show_site_urls() -> None:
    print(f"Site home:      http://{DEMO_OVERLAY_HOST}:{DEMO_OVERLAY_PORT}/index.html")
    print(f"Capability map: http://{DEMO_OVERLAY_HOST}:{DEMO_OVERLAY_PORT}/references/kiln-capabilities")
    print(f"Live-reload:    http://{DEMO_OVERLAY_HOST}:{DEMO_OVERLAY_PORT}/experiments/live-reload")
    print(f"Mutation note:  http://{DEMO_OVERLAY_HOST}:{DEMO_OVERLAY_PORT}/projects/forge-v2")


def maybe_keep_stack_running() -> None:
    global KEEP_STACK_RUNNING

    if AUTO_ADVANCE:
        log("auto-advance mode: cleaning up stack")
        return

    print("\nPress k to keep the stack running for manual exploration.")
    print("Press any key for cleanup, or k to keep it running: ", end="", flush=True)
    keep = read_single_key().strip().lower()
    print("")
    if keep == "k":
        KEEP_STACK_RUNNING = True


def run_walkthrough() -> None:
    print_rule()
    print("Forge v2 Interactive Demo Walkthrough")
    print_rule()
    print("This walkthrough uses a real localhost stack and pauses between steps.")
    print("Talk track reference: demo/DEMO_SCRIPT.md")

    pause_step("Press any key to initialize a clean demo runtime...")

    run_helper_script("cleanup.py", quiet=True)
    run_helper_script("setup.py")
    run_helper_script("start_stack.py")
    read_pid_file()

    step_header("1", "Open The Live Site")
    show_site_urls()
    print("\nTalking points:")
    print(" - kiln-fork is running watch mode with --no-serve and --on-rebuild.")
    print(" - forge-overlay serves generated output and injects demo overlay assets.")
    print(" - real obsidian-agent is running behind overlay through forge dev.")
    pause_step("Open the URLs and inspect baseline behavior, then press any key...")

    step_header("2", "Show Kiln Rendering Capabilities")
    print("Suggested pages to inspect:")
    print(" - /index.html (tables, code, callouts, math, tags)")
    print(" - /canvas/roadmap (canvas output)")
    print(" - /references/kiln-capabilities (feature matrix)")
    print(" - /experiments/live-reload (watch target)")
    pause_step("After reviewing these pages, press any key...")

    step_header("3", "Trigger A Real Incremental Rebuild")
    token = f"walkthrough-mutation-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{os.getpid()}"
    orchestrator_log = LOG_DIR / "forge.log"
    live_reload_md = VAULT_DIR / "experiments" / "live-reload.md"
    target_html = rendered_html_path("experiments/live-reload.md")

    kiln_before = count_pattern(orchestrator_log, r"\[kiln\].*rebuilding after file change")
    overlay_before = count_pattern(orchestrator_log, r"\[overlay\].*POST /internal/rebuild")
    wait_for_initial_build(orchestrator_log)
    live_reload_md.parent.mkdir(parents=True, exist_ok=True)
    with live_reload_md.open("a", encoding="utf-8") as handle:
        handle.write(f"\n\nWalkthrough mutation token: {token}\n")

    def rebuild_done() -> bool:
        kiln_after = count_pattern(orchestrator_log, r"\[kiln\].*rebuilding after file change")
        overlay_after = count_pattern(orchestrator_log, r"\[overlay\].*POST /internal/rebuild")
        html_has_token = target_html.exists() and token in target_html.read_text(encoding="utf-8", errors="ignore")
        return kiln_after > kiln_before and overlay_after > overlay_before and html_has_token

    if not wait_until(rebuild_done, timeout_s=60):
        raise fail("expected rebuild + webhook + rendered token was not observed")

    print(f"Mutation token appended and rendered: {token}")
    print("Refresh /experiments/live-reload to confirm the update.")
    pause_step("After confirming live-reload update, press any key...")

    step_header("4", "Demonstrate Overlay API Proxy Health")
    health_url = f"http://{DEMO_OVERLAY_HOST}:{DEMO_OVERLAY_PORT}/api/health"
    health_payload = json.loads(http_get(health_url).decode("utf-8"))
    print("Proxy health response:")
    print(json.dumps(health_payload, indent=2, sort_keys=True))
    pause_step("After reviewing health output, press any key...")

    step_header("5", "Demonstrate Sync Bootstrap Endpoints")
    sync_ensure_url = f"http://{DEMO_OVERLAY_HOST}:{DEMO_OVERLAY_PORT}/api/vault/vcs/sync/ensure"
    sync_remote_url = f"http://{DEMO_OVERLAY_HOST}:{DEMO_OVERLAY_PORT}/api/vault/vcs/sync/remote"
    sync_run_url = f"http://{DEMO_OVERLAY_HOST}:{DEMO_OVERLAY_PORT}/api/vault/vcs/sync"
    sync_status_url = f"http://{DEMO_OVERLAY_HOST}:{DEMO_OVERLAY_PORT}/api/vault/vcs/sync/status"

    ensure_payload = json.loads(http_post_json(sync_ensure_url, {}).decode("utf-8"))
    remote_payload = json.loads(
        http_put_json(
            sync_remote_url,
            {"remote": "origin", "url": "https://github.com/example/demo-vault.git"},
        ).decode("utf-8")
    )
    sync_payload = json.loads(http_post_json(sync_run_url, {"remote": "origin"}).decode("utf-8"))
    status_payload = json.loads(http_get(sync_status_url).decode("utf-8"))

    print("Ensure response:")
    print(json.dumps(ensure_payload, indent=2, sort_keys=True))
    print("Remote configuration response:")
    print(json.dumps(remote_payload, indent=2, sort_keys=True))
    print("Sync run response:")
    print(json.dumps(sync_payload, indent=2, sort_keys=True))
    print("Sync status response:")
    print(json.dumps(status_payload, indent=2, sort_keys=True))
    pause_step("After reviewing sync endpoint output, press any key...")

    step_header("6", "Run Deterministic Apply Through Overlay")
    apply_url = f"http://{DEMO_OVERLAY_HOST}:{DEMO_OVERLAY_PORT}/api/agent/apply"
    api_base = f"http://{DEMO_OVERLAY_HOST}:{DEMO_OVERLAY_PORT}/api"
    note_html = rendered_html_path("projects/forge-v2.md")
    apply_token = f"WALKTHROUGH_APPLY_{int(time.time())}"
    baseline_marker_count = count_substring(note_html, apply_token)
    apply_via = "agent"
    fallback_original_content: str | None = None
    try:
        apply_payload = json.loads(
            http_post_json(
                apply_url,
                {
                    "instruction": f"Append exactly this line at end of file: {apply_token}",
                    "current_file": "projects/forge-v2.md",
                },
            ).decode("utf-8")
        )
        if not apply_payload.get("ok"):
            raise RuntimeError(f"agent apply returned not ok: {apply_payload}")
    except (urlerror.HTTPError, RuntimeError):
        apply_via = "vault"
        fallback_original_content = str(
            json.loads(http_get(f"{api_base}/vault/files?path={urlparse.quote('projects/forge-v2.md')}").decode("utf-8")).get(
                "content", ""
            )
        )
        apply_payload = vault_append_token(api_base, "projects/forge-v2.md", apply_token)
    print("Apply response:")
    print(json.dumps(apply_payload, indent=2, sort_keys=True))
    if not apply_payload.get("ok"):
        raise fail(f"apply request failed: {apply_payload}")
    if apply_via == "vault":
        print("Agent apply unavailable; used deterministic vault-route fallback.")

    print("Waiting for rendered apply update...")
    if not wait_until(
        lambda: note_html.exists() and count_substring(note_html, apply_token) > baseline_marker_count,
        timeout_s=45,
    ):
        raise fail("apply marker not observed in rendered note")

    print(f"Apply completed. Refresh /projects/forge-v2 to see token: {apply_token}")
    pause_step("After confirming apply output in browser, press any key...")

    step_header("7", "Run Undo Through Overlay")
    undo_url = f"http://{DEMO_OVERLAY_HOST}:{DEMO_OVERLAY_PORT}/api/agent/undo"
    undo_payload = (
        json.loads(http_post_json(undo_url, {}).decode("utf-8"))
        if apply_via == "agent"
        else vault_restore_content(api_base, "projects/forge-v2.md", fallback_original_content or "")
    )
    print("Undo response:")
    print(json.dumps(undo_payload, indent=2, sort_keys=True))
    if not undo_payload.get("ok"):
        raise fail(f"undo request failed: {undo_payload}")

    print("Waiting for rendered undo update...")
    if not wait_until(
        lambda: note_html.exists() and count_substring(note_html, apply_token) == baseline_marker_count,
        timeout_s=45,
    ):
        raise fail("undo marker removal not observed in rendered note")

    print("Undo completed. Refresh /projects/forge-v2 to confirm marker removal.")
    pause_step("After confirming undo output in browser, press any key...")

    step_header("8", "Wrap-Up")
    kiln_rebuilds = count_pattern(orchestrator_log, r"\[kiln\].*rebuilding after file change")
    overlay_hooks = count_pattern(orchestrator_log, r'\[overlay\].*POST /internal/rebuild HTTP/1.1" 204')
    print("Final checks:")
    print(f" - kiln incremental rebuilds observed: {kiln_rebuilds}")
    print(f" - overlay rebuild webhooks observed (204): {overlay_hooks}")
    print(" - overlay /api proxy health/apply/undo path succeeded")
    print("\nInteractive walkthrough complete.")

    maybe_keep_stack_running()


def main() -> int:
    try:
        run_walkthrough()
    except (RuntimeError, subprocess.CalledProcessError, urlerror.URLError, json.JSONDecodeError) as exc:
        print(exc, file=sys.stderr)
        return 1
    finally:
        if KEEP_STACK_RUNNING:
            log("leaving demo stack running")
            show_site_urls()
            log("when done, run: uv run demo/scripts/cleanup.py")
        else:
            run_helper_script("cleanup.py", quiet=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
