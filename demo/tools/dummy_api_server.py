#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Deterministic dummy API used by the forge demo harness.

This server mimics the subset of agent endpoints needed by the demo:
- GET  /api/health
- POST /api/agent/apply (alias: /api/apply)
- POST /api/agent/undo  (alias: /api/undo)
- POST /api/vault/vcs/sync/ensure
- PUT  /api/vault/vcs/sync/remote
- POST /api/vault/vcs/sync
- GET  /api/vault/vcs/sync/status
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import argparse
import json
from pathlib import Path
import threading
import time
from typing import Any
import uuid


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass
class Job:
    id: str
    operation: str
    status: JobStatus
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    request: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: str | None = None
    _transition_at: float = 0.0


@dataclass
class DemoState:
    vault_dir: Path
    lock: threading.Lock = field(default_factory=threading.Lock)
    apply_count: int = 0
    history: list[tuple[Path, str]] = field(default_factory=list)
    sync_remote: str = "origin"
    sync_remote_url: str | None = None
    sync_bootstrapped: bool = False
    sync_count: int = 0
    jobs: list[Job] = field(default_factory=list)
    job_completion_delay_s: float = 2.0

    def resolve_target(self, raw_path: str | None) -> tuple[Path, str]:
        rel = (raw_path or "projects/forge-v2.md").lstrip("/")
        candidate = (self.vault_dir / rel).resolve()
        vault_root = self.vault_dir.resolve()
        if not candidate.is_relative_to(vault_root):
            raise ValueError(f"path escapes vault: {raw_path}")
        return candidate, rel

    def apply(self, instruction: str, current_file: str | None) -> dict[str, Any]:
        with self.lock:
            target, rel = self.resolve_target(current_file)
            target.parent.mkdir(parents=True, exist_ok=True)
            original = target.read_text(encoding="utf-8") if target.exists() else ""
            self.history.append((target, original))

            self.apply_count += 1
            marker = (
                f"\n\n## Dummy LLM Update {self.apply_count}\n\n"
                f"- instruction: {instruction}\n"
                "- backend: dummy-llm:v1\n"
            )
            target.write_text(original + marker, encoding="utf-8")

            return {
                "ok": True,
                "summary": f"Applied deterministic dummy update #{self.apply_count}",
                "changed_files": [rel],
                "provider": "dummy-llm",
            }

    def undo(self) -> dict[str, Any]:
        with self.lock:
            if not self.history:
                return {
                    "ok": False,
                    "summary": "Nothing to undo",
                    "changed_files": [],
                }

            target, previous = self.history.pop()
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(previous, encoding="utf-8")
            rel = str(target.relative_to(self.vault_dir.resolve()))
            return {
                "ok": True,
                "summary": "Reverted latest dummy update",
                "changed_files": [rel],
            }

    def sync_ensure(self) -> dict[str, Any]:
        return {
            "ok": True,
            "status": "ready",
            "detail": "dummy sync backend ready",
        }

    def sync_remote_configure(self, remote: str, url: str) -> dict[str, Any]:
        self.sync_remote = remote
        self.sync_remote_url = url
        return {
            "ok": True,
            "remote": self.sync_remote,
            "url": self.sync_remote_url,
        }

    def sync_run(self, remote: str) -> dict[str, Any]:
        self.sync_count += 1
        self.sync_bootstrapped = True
        self.sync_remote = remote
        return {
            "ok": True,
            "sync_ok": True,
            "remote": self.sync_remote,
            "sync_count": self.sync_count,
            "provider": "dummy-sync",
        }

    def sync_status(self) -> dict[str, Any]:
        return {
            "ok": True,
            "status": "ready" if self.sync_bootstrapped else "not_configured",
            "remote": self.sync_remote,
            "remote_url": self.sync_remote_url,
            "sync_count": self.sync_count,
        }

    def submit_job(self, operation: str, payload: dict[str, Any] | None) -> Job:
        with self.lock:
            now = datetime.now(timezone.utc).isoformat()
            request_payload = dict(payload or {})
            if operation == "apply" and "instruction" not in request_payload:
                request_payload["instruction"] = ""
            job = Job(
                id=str(uuid.uuid4()),
                operation=operation,
                status=JobStatus.QUEUED,
                created_at=now,
                request=request_payload,
                _transition_at=time.time() + 0.3,
            )
            self.jobs.append(job)
            return job

    def get_job(self, job_id: str) -> Job | None:
        with self.lock:
            for job in self.jobs:
                if job.id == job_id:
                    self._advance_job(job)
                    return job
        return None

    def list_jobs(self, limit: int = 50) -> list[Job]:
        with self.lock:
            for job in self.jobs:
                self._advance_job(job)
            return list(reversed(self.jobs[-limit:]))

    def _advance_job(self, job: Job) -> None:
        now = time.time()
        if job.status == JobStatus.QUEUED and now >= job._transition_at:
            job.status = JobStatus.RUNNING
            job.started_at = datetime.now(timezone.utc).isoformat()
            job._transition_at = now + self.job_completion_delay_s

        if job.status == JobStatus.RUNNING and now >= job._transition_at:
            job.finished_at = datetime.now(timezone.utc).isoformat()
            instruction = str(job.request.get("instruction", ""))
            if "FAIL" in instruction:
                job.status = JobStatus.FAILED
                job.error = "Simulated failure triggered by FAIL keyword in instruction"
                job.result = {
                    "ok": False,
                    "updated": False,
                    "summary": "",
                    "changed_files": [],
                    "error": job.error,
                    "warning": None,
                }
                return

            if job.operation == "apply":
                result = self.apply(instruction=instruction or "no instruction", current_file=job.request.get("current_file"))
            elif job.operation == "undo":
                result = self.undo()
            else:
                result = {"ok": False, "error": f"unknown operation: {job.operation}"}

            job.status = JobStatus.SUCCEEDED if result.get("ok") else JobStatus.FAILED
            job.result = {
                "ok": bool(result.get("ok", False)),
                "updated": bool(result.get("ok", False)),
                "summary": str(result.get("summary", "")),
                "changed_files": result.get("changed_files", []),
                "error": result.get("error"),
                "warning": None,
            }
            if not result.get("ok"):
                job.error = str(result.get("error", "operation failed"))

    def _job_to_dict(self, job: Job) -> dict[str, Any]:
        return {
            "id": job.id,
            "operation": job.operation,
            "status": job.status.value,
            "created_at": job.created_at,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
            "request": job.request,
            "result": job.result,
            "error": job.error,
        }


class Handler(BaseHTTPRequestHandler):
    server_version = "ForgeDummyAPI/1.0"

    @property
    def state(self) -> DemoState:
        return self.server.state  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: object) -> None:
        print(f"[{self.log_date_time_string()}] {self.address_string()} {format % args}")

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("content-length", "0"))
        raw = self.rfile.read(length) if length > 0 else b"{}"
        if not raw:
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("invalid JSON body") from exc
        if not isinstance(data, dict):
            raise ValueError("JSON payload must be an object")
        return data

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/api/health":
            self._send_json(
                {
                    "ok": True,
                    "status": "healthy",
                    "provider": "dummy-llm",
                    "apply_count": self.state.apply_count,
                }
            )
            return
        if self.path == "/api/vault/vcs/sync/status":
            self._send_json(self.state.sync_status())
            return
        if self.path.startswith("/v1/jobs/"):
            job_id = self.path.split("/v1/jobs/")[1].split("?", 1)[0].rstrip("/")
            job = self.state.get_job(job_id)
            if job is None:
                self._send_json({"error": f"job not found: {job_id}"}, status=HTTPStatus.NOT_FOUND)
                return
            self._send_json(self.state._job_to_dict(job))
            return
        if self.path.startswith("/v1/jobs"):
            limit = 50
            if "?" in self.path:
                query = self.path.split("?", 1)[1]
                for part in query.split("&"):
                    if part.startswith("limit="):
                        try:
                            limit = max(1, min(200, int(part.split("=", 1)[1])))
                        except ValueError:
                            pass
            jobs = self.state.list_jobs(limit=limit)
            self._send_json({"jobs": [self.state._job_to_dict(job) for job in jobs]})
            return

        self._send_json({"ok": False, "error": f"Not found: {self.path}"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        if self.path in {"/api/agent/apply", "/api/apply"}:
            try:
                payload = self._read_json()
                instruction = str(payload.get("instruction", "no instruction provided")).strip()
                current_file = payload.get("current_file")
                response = self.state.apply(instruction=instruction, current_file=None if current_file is None else str(current_file))
            except ValueError as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            self._send_json(response)
            return
        if self.path.rstrip("/") == "/v1/jobs":
            try:
                payload = self._read_json()
                operation = payload.get("operation")
                if operation not in {"apply", "undo"}:
                    self._send_json({"error": "operation must be 'apply' or 'undo'"}, status=HTTPStatus.BAD_REQUEST)
                    return
                job_payload = payload.get("payload")
                if operation == "apply" and (not isinstance(job_payload, dict) or not str(job_payload.get("instruction", "")).strip()):
                    self._send_json({"error": "payload with instruction required for apply operation"}, status=HTTPStatus.BAD_REQUEST)
                    return
                job = self.state.submit_job(str(operation), job_payload if isinstance(job_payload, dict) else None)
                self._send_json(
                    {"job_id": job.id, "status": job.status.value, "created_at": job.created_at},
                    status=HTTPStatus.ACCEPTED,
                )
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        if self.path in {"/api/agent/undo", "/api/undo"}:
            self._send_json(self.state.undo())
            return
        if self.path == "/api/vault/vcs/sync/ensure":
            self._send_json(self.state.sync_ensure())
            return
        if self.path == "/api/vault/vcs/sync":
            try:
                payload = self._read_json()
                remote = str(payload.get("remote", self.state.sync_remote)).strip() or self.state.sync_remote
            except ValueError as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json(self.state.sync_run(remote))
            return

        self._send_json({"ok": False, "error": f"Not found: {self.path}"}, status=HTTPStatus.NOT_FOUND)

    def do_PUT(self) -> None:  # noqa: N802
        if self.path == "/api/vault/vcs/sync/remote":
            try:
                payload = self._read_json()
                remote = str(payload.get("remote", "origin")).strip() or "origin"
                url = str(payload.get("url", "")).strip()
                if not url:
                    raise ValueError("url is required")
            except ValueError as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json(self.state.sync_remote_configure(remote=remote, url=url))
            return

        self._send_json({"ok": False, "error": f"Not found: {self.path}"}, status=HTTPStatus.NOT_FOUND)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run deterministic dummy API for forge demo harness")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18081)
    parser.add_argument("--vault-dir", type=Path, required=True)
    parser.add_argument("--job-delay", type=float, default=2.0, help="Simulated job processing time in seconds")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    state = DemoState(vault_dir=args.vault_dir, job_completion_delay_s=args.job_delay)

    class DemoServer(ThreadingHTTPServer):
        state: DemoState

    server = DemoServer((args.host, args.port), Handler)
    server.state = state

    print(f"dummy-api listening on http://{args.host}:{args.port} (vault={args.vault_dir})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
