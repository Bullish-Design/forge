#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time
from urllib import error as urlerror
from urllib import request

SCRIPT_DIR = Path(__file__).resolve().parent
DEMO_DIR = SCRIPT_DIR.parent
RUNTIME_DIR = Path(os.environ.get("DEMO_RUNTIME_DIR", str(DEMO_DIR / "runtime")))
VAULT_TEMPLATE_DIR = DEMO_DIR / "vault-template"
OVERLAY_TEMPLATE_DIR = DEMO_DIR / "overlay"
OVERLAY_TEMPLATE_DIR = Path(os.environ.get("DEMO_OVERLAY_TEMPLATE_DIR", str(OVERLAY_TEMPLATE_DIR)))

VAULT_DIR = RUNTIME_DIR / "vault"
PUBLIC_DIR = RUNTIME_DIR / "public"
OVERLAY_DIR = RUNTIME_DIR / "overlay"
CONFIG_OVERLAY_DIR = Path(os.environ.get("DEMO_OVERLAY_DIR", str(OVERLAY_DIR)))
LOG_DIR = RUNTIME_DIR / "logs"
PID_FILE = RUNTIME_DIR / "pids.env"
CONFIG_FILE = RUNTIME_DIR / "forge.demo.yaml"

DEMO_OVERLAY_HOST = os.environ.get("DEMO_OVERLAY_HOST", "127.0.0.1")
DEMO_OVERLAY_PORT = int(os.environ.get("DEMO_OVERLAY_PORT", "18080"))
DEMO_API_HOST = os.environ.get("DEMO_API_HOST", "127.0.0.1")
DEMO_API_PORT = int(os.environ.get("DEMO_API_PORT", "18081"))

AGENT_LLM_BASE_URL = os.environ.get("AGENT_LLM_BASE_URL", os.environ.get("DEMO_VLLM_BASE_URL", "http://remora-server:8000/v1"))
AGENT_LLM_MODEL = os.environ.get("AGENT_LLM_MODEL", os.environ.get("DEMO_VLLM_MODEL", "openai:auto"))
AGENT_LLM_API_KEY = os.environ.get("AGENT_LLM_API_KEY", os.environ.get("OPENAI_API_KEY", "EMPTY"))

if Path("/home/andrew/Documents/Projects/kiln-fork/kiln").exists():
    DEFAULT_KILN_BIN = "/home/andrew/Documents/Projects/kiln-fork/kiln"
else:
    DEFAULT_KILN_BIN = "kiln"
KILN_BIN = os.environ.get("KILN_BIN", DEFAULT_KILN_BIN)


def log(message: str) -> None:
    print(f"[demo] {message}")


def fail(message: str) -> RuntimeError:
    return RuntimeError(f"[demo][error] {message}")


def require_dependency_commands() -> None:
    # We intentionally require these to exist since forge dev relies on them.
    for command in ("forge", "obsidian-agent", "forge-overlay", "jj"):
        if shutil.which(command) is None:
            raise fail(f"required dependency command not installed on PATH: {command}")

    if Path(KILN_BIN).exists():
        if not os.access(KILN_BIN, os.X_OK):
            raise fail(f"KILN_BIN exists but is not executable: {KILN_BIN}")
    elif shutil.which(KILN_BIN) is None:
        raise fail(f"required kiln binary not found: {KILN_BIN}")


def ensure_port_free(host: str, port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        if sock.connect_ex((host, port)) == 0:
            raise fail(f"port already in use: {host}:{port}")


def wait_for_http(url: str, timeout_s: float = 45.0, any_status: bool = False) -> None:
    deadline = time.monotonic() + timeout_s
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            req = request.Request(url=url, method="GET")
            with request.urlopen(req, timeout=3):
                return
        except urlerror.HTTPError:
            if any_status:
                return
            last_error = RuntimeError("unexpected_http_status")
        except Exception as exc:  # noqa: BLE001
            last_error = exc
        time.sleep(0.25)
    raise fail(f"http readiness timeout for {url}: {last_error}")


def wait_for_file(path: Path, timeout_s: float = 45.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if path.exists():
            return
        time.sleep(0.2)
    raise fail(f"timed out waiting for file: {path}")


def parse_pid_file() -> dict[str, int]:
    if not PID_FILE.exists():
        return {}
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
        except ValueError:
            continue
    return pids


def process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def stop_pid(pid: int) -> None:
    pgid: int
    try:
        pgid = os.getpgid(pid)
        os.killpg(pgid, signal.SIGTERM)
    except OSError:
        return

    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if not process_alive(pid):
            return
        time.sleep(0.2)

    try:
        os.killpg(pgid, signal.SIGKILL)
    except OSError:
        return


def _kill_port_holders(*ports: int) -> None:
    """Best-effort cleanup for processes still listening on demo ports."""
    for port in ports:
        pids: set[int] = set()
        try:
            lsof_result = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True,
                text=True,
                check=False,
            )
            for pid_text in lsof_result.stdout.splitlines():
                try:
                    pids.add(int(pid_text.strip()))
                except ValueError:
                    continue
        except FileNotFoundError:
            pass

        if not pids:
            try:
                ss_result = subprocess.run(
                    ["ss", "-ltnp"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
            except FileNotFoundError:
                ss_result = None

            if ss_result is not None:
                match_token = f":{port} "
                for line in ss_result.stdout.splitlines():
                    if match_token not in line:
                        continue
                    for token in line.split():
                        if "pid=" not in token:
                            continue
                        start = token.find("pid=")
                        if start < 0:
                            continue
                        number = token[start + 4 :].split(",", 1)[0].rstrip(")")
                        try:
                            pids.add(int(number))
                        except ValueError:
                            continue

        for pid_value in pids:
            try:
                os.kill(pid_value, signal.SIGKILL)
            except OSError:
                continue


def write_demo_config() -> None:
    CONFIG_FILE.write_text(
        "\n".join(
            [
                f"vault_dir: {VAULT_DIR}",
                f"output_dir: {PUBLIC_DIR}",
                f"overlay_dir: {CONFIG_OVERLAY_DIR}",
                f"host: {DEMO_OVERLAY_HOST}",
                f"port: {DEMO_OVERLAY_PORT}",
                "",
                "agent:",
                f"  host: {DEMO_API_HOST}",
                f"  port: {DEMO_API_PORT}",
                f"  vault_dir: {VAULT_DIR}",
                f"  llm_model: {AGENT_LLM_MODEL}",
                "",
                "kiln:",
                f"  bin: {KILN_BIN}",
                "  theme: default",
                "  font: inter",
                "  lang: en",
                "  site_name: Forge Demo Harness",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def setup_runtime() -> None:
    log(f"resetting demo runtime at {RUNTIME_DIR}")
    shutil.rmtree(RUNTIME_DIR, ignore_errors=True)
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    shutil.copytree(VAULT_TEMPLATE_DIR, VAULT_DIR, dirs_exist_ok=True)
    subprocess.run(["jj", "git", "init", str(VAULT_DIR)], check=True)
    if CONFIG_OVERLAY_DIR == OVERLAY_DIR:
        OVERLAY_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copytree(OVERLAY_TEMPLATE_DIR, OVERLAY_DIR, dirs_exist_ok=True)
    elif not CONFIG_OVERLAY_DIR.exists():
        raise fail(f"configured DEMO_OVERLAY_DIR does not exist: {CONFIG_OVERLAY_DIR}")

    write_demo_config()
    log("runtime prepared")


def start_stack() -> int:
    require_dependency_commands()

    if PID_FILE.exists():
        raise fail(f"existing pid file found at {PID_FILE} (run: uv run demo/scripts/cleanup.py)")

    ensure_port_free(DEMO_OVERLAY_HOST, DEMO_OVERLAY_PORT)
    ensure_port_free(DEMO_API_HOST, DEMO_API_PORT)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    forge_log = LOG_DIR / "forge.log"
    handle = forge_log.open("w", encoding="utf-8")

    env = os.environ.copy()
    env["AGENT_LLM_BASE_URL"] = AGENT_LLM_BASE_URL
    env["AGENT_LLM_MODEL"] = AGENT_LLM_MODEL
    env["AGENT_LLM_API_KEY"] = AGENT_LLM_API_KEY

    cmd = ["uv", "run", "forge", "dev", "--config", str(CONFIG_FILE)]
    log("starting forge dev orchestrator")
    proc = subprocess.Popen(
        cmd,
        cwd=str(DEMO_DIR.parent),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=handle,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )

    # Wait for overlay and agent through orchestrator wiring.
    wait_for_http(f"http://{DEMO_OVERLAY_HOST}:{DEMO_OVERLAY_PORT}/", timeout_s=60, any_status=True)
    wait_for_http(f"http://{DEMO_OVERLAY_HOST}:{DEMO_OVERLAY_PORT}/api/health", timeout_s=60)
    wait_for_file(PUBLIC_DIR / "index.html", timeout_s=90)

    if proc.poll() is not None:
        raise fail("forge dev exited unexpectedly during startup")

    PID_FILE.write_text(f"FORGE_PID={proc.pid}\n", encoding="utf-8")
    log("stack started")
    log(f"site: http://{DEMO_OVERLAY_HOST}:{DEMO_OVERLAY_PORT}/index.html")
    return 0


def cleanup_runtime() -> int:
    pids = parse_pid_file()
    forge_pid = pids.get("FORGE_PID")
    if forge_pid is not None:
        log("stopping forge process group")
        stop_pid(forge_pid)

    _kill_port_holders(DEMO_OVERLAY_PORT, DEMO_API_PORT)

    log("removing runtime")
    shutil.rmtree(RUNTIME_DIR, ignore_errors=True)
    log("cleanup complete")
    return 0


def run_script(name: str, quiet: bool = False) -> int:
    path = SCRIPT_DIR / name
    if quiet:
        completed = subprocess.run(
            [sys.executable, str(path)],
            cwd=DEMO_DIR.parent,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return completed.returncode
    completed = subprocess.run([sys.executable, str(path)], cwd=DEMO_DIR.parent, check=False)
    return completed.returncode
