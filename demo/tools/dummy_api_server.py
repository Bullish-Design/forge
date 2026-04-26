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
"""

from __future__ import annotations

from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import argparse
import json
from pathlib import Path
import threading
from typing import Any


@dataclass
class DemoState:
    vault_dir: Path
    lock: threading.Lock = field(default_factory=threading.Lock)
    apply_count: int = 0
    history: list[tuple[Path, str]] = field(default_factory=list)

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

        if self.path in {"/api/agent/undo", "/api/undo"}:
            self._send_json(self.state.undo())
            return

        self._send_json({"ok": False, "error": f"Not found: {self.path}"}, status=HTTPStatus.NOT_FOUND)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run deterministic dummy API for forge demo harness")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18081)
    parser.add_argument("--vault-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    state = DemoState(vault_dir=args.vault_dir)

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
