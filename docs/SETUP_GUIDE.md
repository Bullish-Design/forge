# Forge Setup Guide

How to create a new vault site from scratch and grow it into a full
AI-augmented publishing workflow.

---

## Prerequisites

You need these tools installed and on your `PATH`:

| Tool | Purpose | Install |
|------|---------|---------|
| Python 3.13+ | Forge CLI, overlay, agent | System package or pyenv |
| uv | Python package management | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| kiln | Static site generator | Build from `kiln-fork` repo |
| jj (jujutsu) | Vault version control | `cargo install jj-cli` or system package |
| devenv | Nix development environment | Optional, but used by all repos |

### Building kiln-fork

```bash
cd /path/to/kiln-fork
devenv shell -- go build -o kiln ./cmd/kiln
# Or install globally:
devenv shell -- go install ./cmd/kiln
```

Verify: `kiln version`

### Installing forge-overlay

```bash
cd /path/to/forge-overlay
devenv shell -- uv pip install -e .
```

Verify: `forge-overlay --help`

### Installing obsidian-agent

```bash
cd /path/to/obsidian-agent
devenv shell -- uv pip install -e .
```

Verify: `obsidian-agent --help`

### Installing forge

```bash
cd /path/to/forge
devenv shell -- uv pip install -e ".[dev]"
```

Verify: `forge --help`

---

## Step 1: Scaffold a New Site

Run `forge init` to create the directory structure and a starter config:

```bash
mkdir my-site && cd my-site
forge init
```

This creates:

```
my-site/
  vault/         # Your markdown content goes here
  public/        # Generated HTML output (gitignored)
  static/        # Overlay assets (ops.js, ops.css)
  forge.yaml     # Configuration file
```

### Initialize Version Control

Forge uses jujutsu for vault versioning (undo/redo support):

```bash
cd vault
jj git init
cd ..
```

If you prefer to version the whole project:

```bash
git init
echo "public/" >> .gitignore
```

---

## Step 2: Configure Your Site

Edit `forge.yaml`:

```yaml
vault_dir: ./vault
output_dir: ./public
overlay_dir: ./static
host: 127.0.0.1
port: 8080

agent:
  host: 127.0.0.1
  port: 8081
  llm_model: anthropic:claude-sonnet-4-20250514

kiln:
  bin: kiln                    # Or absolute path to your kiln binary
  theme: default               # default, dracula, catppuccin, nord
  font: inter                  # inter, merriweather, lato, system
  lang: en
  site_name: My Notes

sync:
  after_commit: false          # auto-sync after each agent commit
  remote: origin
  # remote_url: https://github.com/your-org/your-vault.git
  # remote_token: ghp_...
```

All values have sensible defaults. The minimal useful config is just:

```yaml
kiln:
  site_name: My Digital Garden
```

### Environment Variable Overrides

Any config field can be overridden with a `FORGE_` prefixed env var:

```bash
FORGE_PORT=9090 forge dev
FORGE_AGENT_LLM_MODEL=openai:gpt-4.1-mini forge dev
FORGE_KILN_THEME=nord forge dev
FORGE_SYNC_REMOTE_URL=https://github.com/your-org/your-vault.git forge dev
```

### Configure Remote Sync (Optional)

To enable bidirectional sync using the agent jj git bridge:

1. Set `FORGE_SYNC_REMOTE_URL`.
2. Set `FORGE_SYNC_REMOTE_TOKEN` for private repos.
3. Optionally set `FORGE_SYNC_AFTER_COMMIT=true` for event-driven post-commit sync.

On startup, Forge will run ensure -> remote configure -> initial sync. If
migration is needed (for example git-only dirty tree), startup continues with a
warning and local mode remains usable.

---

## Step 3: Add Your First Content

Create your home page:

```bash
cat > vault/index.md << 'EOF'
---
title: Home
tags:
  - home
---

# Welcome

This is my site, built with [Forge](https://github.com/Bullish-Design/forge).

## Recent Notes

- [[projects/first-project|My First Project]]
- [[daily/2026-04-26|Today's Log]]
EOF
```

Create a project note:

```bash
mkdir -p vault/projects
cat > vault/projects/first-project.md << 'EOF'
---
title: My First Project
tags:
  - project
  - active
---

# My First Project

## Overview

Describe your project here.

## Tasks

- [ ] Set up the vault structure
- [ ] Add content
- [ ] Customize the theme

> [!tip] Getting Started
> Start with a few notes and grow organically. You don't need to plan
> everything upfront.
EOF
```

Create a daily note:

```bash
mkdir -p vault/daily
cat > vault/daily/2026-04-26.md << 'EOF'
---
title: "2026-04-26"
tags:
  - daily
---

# 2026-04-26

## Log

- Set up Forge site
- Created initial vault structure

## Related

- [[projects/first-project]]
EOF
```

### Vault Structure Conventions

There are no strict rules, but common patterns:

```
vault/
  index.md                  # Home page (becomes site root)
  projects/                 # Long-lived project notes
  daily/                    # Daily log entries
  references/               # Reference material
  experiments/              # Scratch/experimental notes
  attachments/              # Images, files
  assets/                   # SVG, diagrams
  canvas/                   # Obsidian canvas files (.canvas)
  .forge/
    templates/              # Page templates (YAML)
```

kiln generates folder index pages automatically, so any directory with
markdown files gets a browsable listing.

---

## Step 4: Generate and Preview

### One-shot build

```bash
forge generate
```

This runs kiln to convert your vault into HTML in `public/`.

### Live development mode

```bash
forge dev
```

This starts:
1. **forge-overlay** on `http://127.0.0.1:8080` -- open this in your browser
2. **obsidian-agent** on `http://127.0.0.1:8081` -- LLM backend
3. **kiln** in watch mode -- rebuilds on every vault file change

Edit any file in `vault/` and the browser will update automatically via SSE.

Press `Ctrl+C` to shut everything down cleanly.

### Preview without agent

If you just want to preview the site without the AI agent:

```bash
forge serve
```

This starts only forge-overlay. You'll need to run `forge generate` first to
have content to serve.

---

## Step 5: Add Overlay Assets

The overlay directory (`static/` by default) contains JavaScript and CSS that
forge-overlay injects into every HTML page. Two files are expected:

### `static/ops.js` -- Minimal auto-reload

```javascript
(() => {
  const es = new EventSource("/ops/events");
  es.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    if (msg.type === "rebuilt") {
      console.log("[forge] Rebuild detected, reloading...");
      location.reload();
    }
  };
  es.onerror = () => {
    console.warn("[forge] SSE connection lost, will retry...");
  };
})();
```

### `static/ops.css` -- Optional status indicator

```css
#ops-indicator {
  position: fixed;
  bottom: 8px;
  right: 8px;
  padding: 4px 8px;
  font-size: 12px;
  background: rgba(0, 0, 0, 0.6);
  color: #0f0;
  border-radius: 4px;
  font-family: monospace;
  z-index: 99999;
  pointer-events: none;
}
```

These are the minimal assets. You can make them as complex as you want --
forge-overlay injects whatever is in the directory. The demo includes a full
interactive panel with apply/undo buttons as an example of what's possible.

---

## Step 6: Use the AI Agent

With `forge dev` running, the agent is available at
`http://127.0.0.1:8081/api/agent/apply` (proxied through overlay at
`http://127.0.0.1:8080/api/agent/apply`).

### Apply an edit

```bash
curl -X POST http://127.0.0.1:8080/api/agent/apply \
  -H "Content-Type: application/json" \
  -d '{
    "instruction": "Add a summary section with 3 key takeaways",
    "current_file": "projects/first-project.md"
  }'
```

The agent reads the file, uses the LLM to generate edits, writes the changes,
and commits via jujutsu. kiln detects the change and rebuilds automatically.

### Undo an edit

```bash
curl -X POST http://127.0.0.1:8080/api/agent/undo
```

This reverts the last agent operation via jujutsu undo.

### Scoped edits

Constrain the agent to a specific part of a file:

```bash
# Edit only content under a heading
curl -X POST http://127.0.0.1:8080/api/agent/apply \
  -H "Content-Type: application/json" \
  -d '{
    "instruction": "Rewrite this section to be more concise",
    "current_file": "projects/first-project.md",
    "scope": {
      "kind": "heading",
      "path": "projects/first-project.md",
      "heading": "## Overview"
    }
  }'

# Edit only a block reference
curl -X POST http://127.0.0.1:8080/api/agent/apply \
  -H "Content-Type: application/json" \
  -d '{
    "instruction": "Expand this bullet point",
    "current_file": "projects/first-project.md",
    "scope": {
      "kind": "block",
      "path": "projects/first-project.md",
      "block_id": "my-block-id"
    }
  }'
```

### Read and write vault files directly

The vault API provides direct CRUD without LLM involvement:

```bash
# Read a file
curl "http://127.0.0.1:8080/api/vault/files?path=projects/first-project.md"

# Write a file (with optimistic concurrency)
curl -X PUT http://127.0.0.1:8080/api/vault/files \
  -H "Content-Type: application/json" \
  -d '{
    "path": "projects/first-project.md",
    "content": "# Updated content\n\nNew body here.\n",
    "expected_sha256": "<sha256-from-previous-read>"
  }'

# Undo last vault change
curl -X POST http://127.0.0.1:8080/api/vault/undo
```

---

## Step 7: Add Page Templates

Templates let the agent (or API callers) create new pages with a consistent
structure. Create them in `vault/.forge/templates/`:

```bash
mkdir -p vault/.forge/templates
```

### Example: Daily note template

```yaml
# vault/.forge/templates/daily.yaml
key: daily
label: Daily Note
path_template: "daily/{{ today }}.md"
body_template: |
  ---
  title: "{{ today }}"
  tags:
    - daily
  ---

  # {{ today }}

  ## Log

  -

  ## Related

fields:
  - name: dummy
    label: Unused
    required: false
    description: No fields needed -- date is automatic
```

### Example: Project template

```yaml
# vault/.forge/templates/project.yaml
key: project
label: New Project
path_template: "projects/{{ slug(title) }}.md"
body_template: |
  ---
  title: "{{ title }}"
  tags:
    - project
    - active
  ---

  # {{ title }}

  ## Overview

  {{ description }}

  ## Tasks

  - [ ] Define scope
  - [ ] First milestone

fields:
  - name: title
    label: Project Title
    required: true
  - name: description
    label: Brief Description
    required: false
    default: ""
```

### Creating pages from templates

```bash
# List available templates
curl http://127.0.0.1:8080/api/vault/pages/templates

# Create a new project page
curl -X POST http://127.0.0.1:8080/api/vault/pages \
  -H "Content-Type: application/json" \
  -d '{
    "template_id": "project",
    "fields": {
      "title": "Website Redesign",
      "description": "Complete overhaul of the marketing site"
    }
  }'
```

Template expressions:
- `{{ field_name }}` -- field value
- `{{ slug(field_name) }}` -- lowercase, alphanumeric + hyphens
- `{{ today }}` -- ISO date (2026-04-26)
- `{{ now }}` -- ISO datetime (2026-04-26T14:30:00)

---

## Step 8: Customize the Theme

kiln supports four built-in themes: `default`, `dracula`, `catppuccin`, `nord`.

Set in `forge.yaml`:

```yaml
kiln:
  theme: nord
  font: merriweather
  accent_color: blue
```

Or override at runtime:

```bash
FORGE_KILN_THEME=dracula forge dev
```

### Available Fonts

| Font | Style |
|------|-------|
| `inter` | Clean sans-serif (default) |
| `merriweather` | Serif, good for reading |
| `lato` | Light sans-serif |
| `system` | OS default font stack |

### Sidebar Options

Disable individual sidebar panels if you prefer a cleaner layout:

```yaml
kiln:
  # These are passed as flags but not yet in forge.yaml schema --
  # use env vars or kiln.yaml in your vault directory for now
```

Or run kiln directly:

```bash
kiln generate --disable-toc --disable-local-graph --input ./vault --output ./public
```

---

## Growing Your Vault

### Content Tips

- **Start small.** A few notes with wikilinks between them is enough to see the
  system working.
- **Use wikilinks** (`[[page-name]]` or `[[path/to/page|Display Text]]`) for
  internal links. kiln resolves them and generates backlinks automatically.
- **Use tags** in frontmatter for categorization. kiln generates tag index pages.
- **Use headings consistently.** The agent's scoped edits work best with clear
  heading structure.
- **Use block references** (`^block-id`) to mark specific paragraphs for
  targeted agent edits.

### Markdown Features Supported by kiln

| Feature | Syntax | Notes |
|---------|--------|-------|
| Wikilinks | `[[page]]`, `[[page\|text]]` | Auto-resolved, backlinks generated |
| Tags | `#tag` inline, `tags:` in frontmatter | Tag index pages generated |
| Callouts | `> [!type] Title` | tip, warning, note, info, etc. |
| Math | `$inline$`, `$$block$$` | KaTeX rendering |
| Code blocks | ` ```lang ``` ` | Syntax highlighting |
| Tables | Pipe tables | Standard markdown tables |
| Task lists | `- [ ]`, `- [x]` | Rendered as checkboxes |
| Embeds | `![[page]]`, `![[page#heading]]` | Transclusion |
| Canvas | `.canvas` files | Obsidian canvas JSON rendered |
| Footnotes | `[^1]` | Rendered at page bottom |
| SVG | `![[file.svg]]` | Embedded inline |

### Folder Structure

kiln generates index pages for directories automatically. Every folder with
markdown files gets a browsable listing page. You can also create explicit
`index.md` files in any folder to customize the landing page.

---

## Running the Demo

The forge repo includes a self-contained demo that validates the full stack
without requiring an LLM:

```bash
# Automated validation (run this first)
devenv shell -- uv run forge-demo-validate

# Interactive walkthrough
devenv shell -- uv run forge-demo-run

# Free-explore with real vLLM backend
DEMO_VLLM_BASE_URL=http://your-vllm-server:8000/v1 \
  devenv shell -- uv run forge-demo-run-free-explore
```

The demo uses port 18080/18081 to avoid conflicts with a real forge instance
on the default ports.

---

## Troubleshooting

### Port already in use

```bash
# Check what's using the port
lsof -i :8080

# Kill the demo stack if it didn't clean up
devenv shell -- uv run forge-demo-cleanup
```

### kiln not found

Set the path explicitly:

```yaml
kiln:
  bin: /absolute/path/to/kiln
```

Or via env var:

```bash
FORGE_KILN_BIN=/path/to/kiln forge dev
```

### Agent can't connect to LLM

Check your model configuration:

```yaml
agent:
  llm_model: anthropic:claude-sonnet-4-20250514
```

For a local LLM (vLLM, Ollama, etc.):

```bash
FORGE_AGENT_LLM_MODEL=openai:local-model \
FORGE_AGENT_LLM_BASE_URL=http://localhost:8000/v1 \
  forge dev
```

The agent auto-detects the model from the `/v1/models` endpoint if the model
name is set to a generic value like `openai:auto`.

### jujutsu not initialized

The vault directory needs a jujutsu repo for undo/redo:

```bash
cd vault && jj git init
```

### Vault files not rebuilding

Check that kiln is running and watching the correct directory:

```bash
# The forge dev output should show:
# [kiln] watching /path/to/vault for changes
```

If using `forge serve` (overlay only), you need to run `forge generate`
separately to rebuild.
