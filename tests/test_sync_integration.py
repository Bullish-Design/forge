from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import time

import pytest

from forge_cli.config import ForgeConfig
from forge_cli.processes import ProcessManager


@pytest.mark.integration
def test_sync_bootstrap_integration_with_real_jj_git(tmp_path: Path) -> None:
    if os.environ.get("FORGE_RUN_SYNC_TESTS") != "1":
        pytest.skip("Set FORGE_RUN_SYNC_TESTS=1 to run sync integration tests.")

    if shutil.which("jj") is None:
        pytest.skip("jj binary not found")
    if shutil.which("obsidian-agent") is None:
        pytest.skip("obsidian-agent binary not found")

    vault = tmp_path / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    remote_repo = tmp_path / "remote.git"

    subprocess.run(["git", "init", "--bare", str(remote_repo)], check=True)
    subprocess.run(["jj", "git", "init", "--colocate"], cwd=vault, check=True)

    seed = vault / "seed.md"
    seed.write_text("# Seed\n\nbootstrap integration\n", encoding="utf-8")

    # Create an initial local commit so sync has content to push.
    subprocess.run(["jj", "describe", "-m", "seed"], cwd=vault, check=True)
    subprocess.run(["jj", "bookmark", "set", "main"], cwd=vault, check=True)

    cfg = ForgeConfig(
        vault_dir=vault,
        output_dir=tmp_path / "public",
        overlay_dir=tmp_path / "overlay",
        agent_host="127.0.0.1",
        agent_port=19081,
        sync_remote="origin",
        sync_remote_url=remote_repo.as_uri(),
    )

    env = os.environ.copy()
    env["AGENT_VAULT_DIR"] = str(vault)
    env["AGENT_HOST"] = cfg.agent_host
    env["AGENT_PORT"] = str(cfg.agent_port)
    env["AGENT_LLM_MODEL"] = "openai:auto"

    proc = subprocess.Popen(["obsidian-agent"], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        manager = ProcessManager()
        deadline = time.monotonic() + 30
        ready = False
        while time.monotonic() < deadline:
            try:
                manager.bootstrap_sync(cfg)
                ready = True
                break
            except Exception:
                time.sleep(0.5)
        if not ready:
            pytest.fail("bootstrap_sync did not succeed against live agent")

        state = vault / ".forge" / "sync-state.json"
        assert state.exists(), "expected sync-state.json to exist"
        text = state.read_text(encoding="utf-8")
        assert "sync_ok" in text

        refs = subprocess.run(["git", "show-ref"], cwd=remote_repo, check=True, capture_output=True, text=True).stdout
        assert "refs/heads/main" in refs
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
