# Forge on Windows — Docker Install Guide

Date: 2026-04-06

## Overview

This guide walks through setting up Forge on a Windows machine using Docker Desktop. Forge runs entirely inside Linux containers — no Go toolchain or Linux subsystem knowledge is required on the Windows host. By the end you will have Forge serving an Obsidian vault over your Tailscale network at `http://forge:8080`.

## Prerequisites

| Requirement | Why |
|---|---|
| Windows 10/11 (64-bit, Pro/Enterprise/Education recommended) | Docker Desktop needs Hyper-V or WSL 2 |
| Admin access | Docker Desktop installer and Hyper-V/WSL features require it |
| A Tailscale account | The sidecar container joins your tailnet |
| An Obsidian vault (any folder of `.md` files) | This is what Forge builds and serves |
| An LLM backend **or** an Anthropic API key | Powers the Ops agent for `/api/apply` |

## Step 1 — Install Docker Desktop

1. Download Docker Desktop for Windows from https://www.docker.com/products/docker-desktop/
2. Run the installer. When prompted, enable **WSL 2 backend** (recommended over Hyper-V).
3. If the installer asks to enable the "Windows Subsystem for Linux" feature, allow it.
4. Reboot when prompted.
5. Launch Docker Desktop from the Start menu. Wait for the engine status icon (bottom-left) to show green/running.
6. Open PowerShell and verify:

```powershell
docker --version
docker compose version
```

Both commands should print version strings. If `docker compose` is not found, update Docker Desktop — Compose V2 is bundled in current versions.

## Step 2 — Install Tailscale on Windows

Tailscale on the Windows host is **not** required for the container stack to work (the sidecar handles tailnet membership). However, installing it on the host lets you reach `http://forge:8080` from the same machine during testing.

1. Download from https://tailscale.com/download/windows
2. Install and sign in to your tailnet.

## Step 3 — Generate a Tailscale Auth Key

The Tailscale sidecar container needs an auth key to join your tailnet without interactive login.

1. Go to https://login.tailscale.com/admin/settings/keys
2. Click **Generate auth key**.
3. Recommended settings:
   - **Reusable**: Yes — so container restarts don't burn the key.
   - **Ephemeral**: Yes — automatically removes the device from your tailnet when the container stops. This prevents stale device entries from accumulating. Disable only if you need the device to persist across long downtime periods.
   - **Tags**: Optional. Apply an ACL tag if your tailnet uses tag-based policies.
4. Copy the key (`tskey-auth-...`). You will need it in Step 5.

**Security note:** Treat this key like a password. A leaked reusable, non-ephemeral auth key grants persistent access to your tailnet. Using ephemeral mode limits exposure — if the key leaks, any device that joins will be automatically removed when it disconnects. If you suspect a key has been compromised, revoke it immediately at the admin console.

## Step 4 — Clone the Forge Repository

Open PowerShell and clone the repo to a convenient location:

```powershell
cd C:\Users\$env:USERNAME\Projects
git clone https://github.com/Bullish-Design/forge.git
cd forge
```

If you don't have `git` installed, download it from https://git-scm.com/download/win or use the GitHub Desktop app.

## Step 5 — Create the `.env` File

Inside the `forge` directory, create a file named `.env` with your secrets. You can copy from the example:

```powershell
Copy-Item .env.example .env
```

Then open `.env` in a text editor (Notepad, VS Code, etc.) and fill in the values:

```env
# --- Tailscale ---
TS_AUTHKEY=tskey-auth-PASTE_YOUR_KEY_HERE

# --- Vault ---
# Point directly at your Obsidian vault so edits from Obsidian
# and edits from the Ops agent stay in sync.
VAULT_PATH=C:\Users\YourName\Documents\MyVault

# --- Ops LLM Backend ---
# Option A: OpenAI-compatible endpoint (e.g. local vLLM on another machine)
OPS_LLM_BASE_URL=http://your-llm-host:8000/v1
OPS_LLM_MODEL=
OPS_API_KEY=

# Option B: Anthropic API (leave OPS_LLM_BASE_URL empty)
# ANTHROPIC_API_KEY=sk-ant-PASTE_YOUR_KEY_HERE
```

**`VAULT_PATH`** should be the absolute path to your existing Obsidian vault. This bind-mounts your vault directly into the container, so changes made by the Ops agent appear in Obsidian immediately, and vice versa. If you leave it empty, it defaults to a `vault/` directory inside the repo.

Pick **one** of Option A or Option B for the LLM backend. If using Anthropic, clear/remove `OPS_LLM_BASE_URL` and set `ANTHROPIC_API_KEY`. If using a local/remote OpenAI-compatible backend, set `OPS_LLM_BASE_URL` and optionally `OPS_API_KEY`.

**Important:** Never commit `.env` to version control. It is already in `.gitignore`.

## Step 6 — Verify Your Vault

Since `VAULT_PATH` points directly at your Obsidian vault, there is no copy step. Just confirm the path is correct:

```powershell
# Should list your vault's markdown files
Get-ChildItem -Path "C:\Users\YourName\Documents\MyVault" -Filter "*.md" | Select-Object -First 5
```

If you don't have an existing vault and want to start from scratch:

```powershell
mkdir vault
Set-Content -Path .\vault\index.md -Value "# Welcome`nThis is my Forge site."
```

Then leave `VAULT_PATH` empty in `.env` (it defaults to `./vault`).

**Existing `.jj` directory:** If your vault already has a `.jj` directory from another machine or a previous setup, the entrypoint will detect and reuse it. A new `jj` repository is only initialized when no `.jj` directory exists.

## Step 7 — Build and Start the Containers

From the `forge` directory in PowerShell:

```powershell
docker compose up --build -d
```

This will:
1. Build the Forge image from source (first run takes a few minutes).
2. Pull the Tailscale image (`tailscale/tailscale:stable`).
3. Start the Tailscale sidecar and authenticate to your tailnet.
4. Start the Forge container, initialize a `jj` repository in the vault (if needed), and begin serving.

Note: the Forge service image is local-only (`forge:local`) and is not pulled from any remote registry.

Watch the logs to confirm startup:

```powershell
docker compose logs -f
```

Look for:
- Tailscale: `"Success."` or a login URL if auth key is invalid.
- Forge: `Listening on :8080` or similar startup message.

Press `Ctrl+C` to stop following logs (containers keep running).

## Step 8 — Verify the Installation

### 8a. Local health check

From PowerShell on the Windows host:

```powershell
curl http://127.0.0.1:8080/api/health
```

Expected response:

```json
{"ok":true,"status":"healthy"}
```

If this fails, the port mapping or container may not be ready yet. Check `docker compose ps` and logs.

### 8b. Tailnet access

From any device on your Tailscale network, open a browser to:

```
http://forge:8080
```

Or using the full MagicDNS name:

```
http://forge.<your-tailnet>.ts.net:8080
```

You should see your vault rendered as a site with the Ops overlay (a small UI element for interacting with the Ops agent).

### 8c. Test the Ops agent

```powershell
curl -X POST http://127.0.0.1:8080/api/apply `
  -H "Content-Type: application/json" `
  -d '{"instruction": "Add a new page called hello.md with a greeting", "current_url_path": "/"}'
```

This should create a new file in your vault and trigger a site rebuild. If you have Obsidian open on the same vault, you should see the new file appear.

### 8d. Test undo

```powershell
curl -X POST http://127.0.0.1:8080/api/undo
```

This reverts the last Ops change via `jj undo` and rebuilds.

## Step 9 — Routine Operations

### Stop the stack

```powershell
docker compose down
```

Tailscale state and vault data persist across restarts. Your vault files are on the host filesystem and are never affected by container lifecycle.

### Restart the stack

```powershell
docker compose up -d
```

No `--build` needed unless you've pulled new source code.

### Rebuild after a code update

```powershell
git pull
docker compose up --build -d
```

### Trigger a manual site rebuild

If you've edited vault files from Obsidian or another editor and the site hasn't updated, you can trigger a rebuild by restarting the forge container:

```powershell
docker compose restart forge
```

This re-runs the full site build on startup.

### View logs

```powershell
# All services
docker compose logs -f

# Forge only
docker compose logs -f forge

# Tailscale only
docker compose logs -f tailscale
```

### Check container health

```powershell
docker compose ps
```

The `forge` service should show `healthy` status after the healthcheck passes.

## Troubleshooting

### "Cannot connect to the Docker daemon"

Docker Desktop is not running. Launch it from the Start menu and wait for the engine to start.

### Tailscale shows a login URL instead of connecting

Your `TS_AUTHKEY` is invalid, expired, or missing. Generate a new one (Step 3) and update `.env`. Then:

```powershell
docker compose down
docker volume rm forge_tailscale-state
docker compose up -d
```

Removing the state volume forces a fresh auth.

### Port 8080 already in use

Another process is using port 8080. Either stop that process, or change `FORGE_PORT` in `.env`:

```env
FORGE_PORT=9090
```

Then access via `http://127.0.0.1:9090` locally. The Tailscale address still uses 8080 internally.

### `/api/apply` returns a jj error

The vault directory may not have been initialized as a jj repository. Check:

```powershell
docker compose exec forge ls /data/vault/.jj
```

If `.jj` doesn't exist, restart the forge container — the entrypoint initializes it automatically:

```powershell
docker compose restart forge
```

If the vault already has a `.jj` directory from a different machine, the entrypoint will reuse it. If that `.jj` state is corrupted, you can remove it and let the entrypoint re-initialize:

```powershell
# From the host, remove the jj directory from your vault
Remove-Item -Recurse -Force "C:\Users\YourName\Documents\MyVault\.jj"
docker compose restart forge
```

### Slow first build

The first `docker compose up --build` compiles Forge from Go source and downloads the Jujutsu binary from GitHub. Subsequent builds use Docker layer caching and are much faster — only layers after a source change are rebuilt.

### File changes in vault not reflected

Forge watches the vault directory for changes. On Docker Desktop with WSL 2, file watching across the Windows/Linux boundary can have delays of several seconds. This is a known Docker Desktop limitation. Workarounds:

- **Wait a few seconds** — changes usually propagate within 5–10 seconds.
- **Restart the container** — `docker compose restart forge` forces a full rebuild.
- **Use the Ops agent** — edits made by the agent happen inside the container and are detected immediately.

## Cleanup and Uninstall

### Remove the containers and network

```powershell
docker compose down
```

### Remove the containers, network, and Tailscale state

```powershell
docker compose down -v
```

The `-v` flag removes the `tailscale-state` volume. The Tailscale device entry will linger in your admin console unless the key was ephemeral — remove it manually at https://login.tailscale.com/admin/machines.

### Remove the Docker image

```powershell
docker rmi forge:local
```

### Full cleanup

```powershell
docker compose down -v --rmi all
```

This removes containers, volumes, and all images built for the stack.

Your vault files are never deleted by any of these commands — they live on your host filesystem at the path you configured in `VAULT_PATH`.

## Windows-Specific Notes

- **Line endings**: The repository includes a `.gitattributes` file that ensures `docker/entrypoint.sh` keeps LF line endings on Windows. If you cloned the repo before this was added, the entrypoint may fail with `/bin/bash^M: bad interpreter`. Fix by re-cloning or running:
  ```powershell
  git checkout -- docker/entrypoint.sh
  ```
- **Path length**: Windows has a 260-character path limit by default. If your vault has deeply nested directories, enable long paths: `git config --system core.longpaths true`.
- **WSL 2 memory**: Docker Desktop on WSL 2 may consume significant memory. Configure limits in `%USERPROFILE%\.wslconfig`:
  ```ini
  [wsl2]
  memory=4GB
  ```
- **Firewall**: Windows Firewall may block container traffic. Docker Desktop usually configures rules automatically, but if Tailscale access fails, check that Docker's WSL 2 network adapter is allowed through the firewall.
- **`/dev/net/tun` on WSL 2**: The Tailscale container needs TUN device access. Docker Desktop on WSL 2 provides this automatically. If using Hyper-V backend, ensure the `--device /dev/net/tun` equivalent is supported by your Docker version.
