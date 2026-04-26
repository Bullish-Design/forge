#!/usr/bin/env python3
"""
Minimal mock obsidian-agent for smoke testing.

Responds to health checks and simulates file-mutation API calls so Forge's
proxy layer can be exercised without needing a real LLM backend.

Usage: python3 mock_agent.py [PORT]   (default: 8082)
"""
import json
import sys
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8082
VAULT_DIR = os.environ.get("AGENT_VAULT_DIR", "/tmp/forge-smoke-vault")


class MockAgentHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[mock-agent] {fmt % args}", flush=True)

    def _send_json(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/health":
            self._send_json(200, {"status": "ok", "mock": True})
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b"{}"

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            self._send_json(400, {"error": "invalid JSON"})
            return

        if path == "/api/apply":
            # Simulate agent writing a file to the vault
            instruction = payload.get("instruction", "")
            # Write a synthetic result file so hot-reload can be verified
            result_path = os.path.join(VAULT_DIR, "agent-result.md")
            try:
                with open(result_path, "w") as f:
                    f.write(f"---\ntitle: Agent Result\n---\n\n# Agent Result\n\nInstruction received: {instruction}\n")
                self._send_json(200, {
                    "ok": True,
                    "mock": True,
                    "written": "agent-result.md",
                    "instruction": instruction,
                })
            except OSError as e:
                self._send_json(500, {"error": str(e)})
        else:
            self._send_json(404, {"error": "unknown endpoint"})


if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", PORT), MockAgentHandler)
    print(f"[mock-agent] Listening on http://127.0.0.1:{PORT}/", flush=True)
    server.serve_forever()
