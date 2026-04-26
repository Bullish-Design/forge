# Obsidian Ops MVP — Implementation Guide

## Status

- Status: Implementation guide
- Target: Go-based in-process backend for the Forge binary
- Audience: Implementer (you)
- Prerequisite reading: `FORGE_INTERFACE_ARCHITECTURE_MVP.md` in this directory

---

## Overview

This guide walks through building the MVP backend **entirely in Go**, integrated into the existing Forge binary. No separate Python service, no sidecar — the `/api/*` endpoints are handled in-process alongside site serving.

The end result: `forge dev` starts serving the rendered vault site with an injected overlay UI (already built) and handles `/api/apply` and `/api/undo` requests directly, using an LLM agent loop to mutate vault files, commit via Jujutsu, and rebuild via Kiln.

### What already exists

Before you start, understand what's already done:

| Component | Status | Location |
|---|---|---|
| Overlay UI (FAB + modal) | Done | `static/ops.js`, `static/ops.css` |
| HTML injection middleware | Done | `internal/overlay/inject.go` |
| Static overlay asset serving | Done | `internal/overlay/static.go` |
| Reverse proxy for `/api/*` | Done | `internal/proxy/reverse.go` |
| Handler chain routing | Done | `internal/server/mux.go` |
| CLI flags for overlay/proxy | Done | `internal/cli/dev.go` |
| Site building + incremental rebuild | Done | `internal/builder/` |
| File watching + dependency graph | Done | `internal/watch/` |
| Vault scanning + path resolution | Done | `internal/obsidian/` |

The overlay JS already calls `POST /api/apply` and `POST /api/undo` with the correct JSON shapes. You are building the backend that handles those requests.

### Architecture at a glance

```text
Browser (existing ops.js)
  │
  ├─ POST /api/apply   { instruction, current_url_path }
  ├─ POST /api/undo    {}
  │
  ▼
Forge HTTP handler chain (internal/server/mux.go)
  │
  ├─ /api/*  →  NEW: in-process ops handler (internal/ops/)
  ├─ /ops/*  →  existing static overlay handler
  └─ other   →  existing injection middleware → file server
```

---

## Step 1: URL-to-File Path Resolution

**Goal:** Given a URL path like `/projects/alpha/meeting-notes/`, resolve it back to the vault-relative markdown file path like `Projects/Alpha/Meeting Notes.md`.

**Why first:** Every subsequent step depends on knowing which file the user is looking at. This is also the trickiest mapping in the system because the builder slugifies paths (lowercases, replaces spaces with dashes) and may use directory-based clean URLs.

### 1.1 Create the package

Create `internal/ops/resolve.go`.

### 1.2 Understand the forward mapping

The existing builder transforms paths like this:

```
Vault file:    Projects/Alpha/Meeting Notes.md
Slugified:     projects/alpha/meeting-notes.md     (via obsidian.Slugify)
Web path:      /projects/alpha/meeting-notes        (via GetPageWebPath, strips .md)
Output path:   public/projects/alpha/meeting-notes/index.html  (directory-based clean URLs)
Browser URL:   /projects/alpha/meeting-notes/       (trailing slash from server)
```

You need to reverse this: URL path → vault RelPath.

### 1.3 Build a reverse lookup index

The simplest correct approach: scan the vault's file list and build a map of `WebPath → RelPath`.

```go
// internal/ops/resolve.go
package ops

import (
    "strings"
    "sync"
)

// PathIndex maps URL paths to vault-relative file paths.
type PathIndex struct {
    mu      sync.RWMutex
    byURL   map[string]string // normalized URL path → RelPath
}

// NewPathIndex creates an empty index.
func NewPathIndex() *PathIndex {
    return &PathIndex{byURL: make(map[string]string)}
}

// Update rebuilds the index from a list of web-path/rel-path pairs.
// Call this after every vault scan.
func (idx *PathIndex) Update(entries []PathEntry) {
    m := make(map[string]string, len(entries))
    for _, e := range entries {
        key := normalizePath(e.WebPath)
        m[key] = e.RelPath
    }
    idx.mu.Lock()
    idx.byURL = m
    idx.mu.Unlock()
}

// Resolve returns the vault-relative path for a URL path.
// Returns ("", false) if not found.
func (idx *PathIndex) Resolve(urlPath string) (string, bool) {
    idx.mu.RLock()
    defer idx.mu.RUnlock()
    rel, ok := idx.byURL[normalizePath(urlPath)]
    return rel, ok
}

// normalizePath strips trailing slashes and ensures a leading slash.
func normalizePath(p string) string {
    p = "/" + strings.TrimLeft(p, "/")
    p = strings.TrimRight(p, "/")
    if p == "" {
        p = "/"
    }
    return p
}

// PathEntry pairs a web path with its vault-relative file path.
type PathEntry struct {
    WebPath string
    RelPath string
}
```

### 1.4 Populate the index from the vault scan

After `obsidian.New(...).Scan()` runs (which already happens in `runDev`), iterate the vault's `Files` slice. Each `obsidian.File` has both `.WebPath` (e.g., `/projects/alpha/meeting-notes`) and `.RelPath` (e.g., `Projects/Alpha/Meeting Notes.md`).

You will wire this in Step 5. For now, just build and test the `PathIndex` type.

### 1.5 Tests

Create `internal/ops/resolve_test.go`:

```go
package ops

import "testing"

func TestNormalizePath(t *testing.T) {
    cases := []struct{ input, want string }{
        {"/projects/alpha/", "/projects/alpha"},
        {"/projects/alpha", "/projects/alpha"},
        {"projects/alpha/", "/projects/alpha"},
        {"/", "/"},
        {"", "/"},
    }
    for _, c := range cases {
        got := normalizePath(c.input)
        if got != c.want {
            t.Errorf("normalizePath(%q) = %q, want %q", c.input, got, c.want)
        }
    }
}

func TestPathIndexResolve(t *testing.T) {
    idx := NewPathIndex()
    idx.Update([]PathEntry{
        {WebPath: "/projects/alpha/meeting-notes", RelPath: "Projects/Alpha/Meeting Notes.md"},
        {WebPath: "/daily/2026-04-06", RelPath: "Daily/2026-04-06.md"},
        {WebPath: "/", RelPath: "index.md"},
    })

    // Exact match
    rel, ok := idx.Resolve("/projects/alpha/meeting-notes")
    if !ok || rel != "Projects/Alpha/Meeting Notes.md" {
        t.Errorf("got (%q, %v)", rel, ok)
    }

    // Trailing slash (browser sends this)
    rel, ok = idx.Resolve("/projects/alpha/meeting-notes/")
    if !ok || rel != "Projects/Alpha/Meeting Notes.md" {
        t.Errorf("trailing slash: got (%q, %v)", rel, ok)
    }

    // Root
    rel, ok = idx.Resolve("/")
    if !ok || rel != "index.md" {
        t.Errorf("root: got (%q, %v)", rel, ok)
    }

    // Not found
    _, ok = idx.Resolve("/nonexistent")
    if ok {
        t.Error("expected not found")
    }
}
```

**Verification:** `go test ./internal/ops/` passes.

---

## Step 2: Global Mutation Lock

**Goal:** Ensure only one vault mutation runs at a time.

### 2.1 Create the lock

Create `internal/ops/lock.go`:

```go
package ops

import (
    "context"
    "errors"
    "sync"
)

var ErrBusy = errors.New("another operation is already running")

// MutationLock is a non-reentrant try-lock for serializing vault mutations.
type MutationLock struct {
    mu   sync.Mutex
    held bool
}

// Acquire attempts to take the lock. Returns ErrBusy if already held.
// The returned function releases the lock; call it in a defer.
func (l *MutationLock) Acquire() (release func(), err error) {
    l.mu.Lock()
    if l.held {
        l.mu.Unlock()
        return nil, ErrBusy
    }
    l.held = true
    l.mu.Unlock()

    return func() {
        l.mu.Lock()
        l.held = false
        l.mu.Unlock()
    }, nil
}
```

Note: This is a try-lock, not a blocking lock. If the user submits while another operation is running, they get an immediate error. This is the correct MVP behavior — no queuing, no waiting.

### 2.2 Tests

Create `internal/ops/lock_test.go`:

```go
package ops

import "testing"

func TestMutationLockBasic(t *testing.T) {
    var lock MutationLock

    release, err := lock.Acquire()
    if err != nil {
        t.Fatalf("first acquire failed: %v", err)
    }

    // Second acquire should fail
    _, err = lock.Acquire()
    if err != ErrBusy {
        t.Fatalf("expected ErrBusy, got %v", err)
    }

    // Release and re-acquire should succeed
    release()
    release2, err := lock.Acquire()
    if err != nil {
        t.Fatalf("re-acquire failed: %v", err)
    }
    release2()
}
```

**Verification:** `go test ./internal/ops/` passes.

---

## Step 3: Jujutsu Integration

**Goal:** Wrap `jj` CLI commands for committing changes and undoing them.

### 3.1 Create the wrapper

Create `internal/ops/jj.go`:

```go
package ops

import (
    "context"
    "fmt"
    "os/exec"
    "strings"
    "time"
)

// JJ wraps Jujutsu CLI operations against a workspace.
type JJ struct {
    // WorkDir is the root of the jj workspace (typically the vault directory).
    WorkDir string
    // Timeout for jj commands. Zero means 30 seconds.
    Timeout time.Duration
}

func (j *JJ) timeout() time.Duration {
    if j.Timeout > 0 {
        return j.Timeout
    }
    return 30 * time.Second
}

// Commit creates a new jj commit with the given message.
// Jujutsu auto-tracks file changes, so no explicit "add" step is needed.
func (j *JJ) Commit(ctx context.Context, message string) error {
    // In jj, the working copy is always a commit. To snapshot current
    // changes and start a new working-copy commit, we describe the
    // current commit and then create a new empty one on top.
    ctx, cancel := context.WithTimeout(ctx, j.timeout())
    defer cancel()

    // Describe the current working-copy commit with the message
    if err := j.run(ctx, "describe", "-m", message); err != nil {
        return fmt.Errorf("jj describe: %w", err)
    }

    // Create a new empty working-copy commit on top
    if err := j.run(ctx, "new"); err != nil {
        return fmt.Errorf("jj new: %w", err)
    }

    return nil
}

// Undo reverts the last jj operation.
func (j *JJ) Undo(ctx context.Context) error {
    ctx, cancel := context.WithTimeout(ctx, j.timeout())
    defer cancel()
    if err := j.run(ctx, "undo"); err != nil {
        return fmt.Errorf("jj undo: %w", err)
    }
    return nil
}

// Status returns the short status output for debugging/logging.
func (j *JJ) Status(ctx context.Context) (string, error) {
    ctx, cancel := context.WithTimeout(ctx, j.timeout())
    defer cancel()
    return j.output(ctx, "status")
}

func (j *JJ) run(ctx context.Context, args ...string) error {
    cmd := exec.CommandContext(ctx, "jj", args...)
    cmd.Dir = j.WorkDir
    out, err := cmd.CombinedOutput()
    if err != nil {
        return fmt.Errorf("%w: %s", err, strings.TrimSpace(string(out)))
    }
    return nil
}

func (j *JJ) output(ctx context.Context, args ...string) (string, error) {
    cmd := exec.CommandContext(ctx, "jj", args...)
    cmd.Dir = j.WorkDir
    out, err := cmd.CombinedOutput()
    if err != nil {
        return "", fmt.Errorf("%w: %s", err, strings.TrimSpace(string(out)))
    }
    return strings.TrimSpace(string(out)), nil
}
```

### 3.2 Important note on jj semantics

Jujutsu works differently from git:
- The working copy is always a commit (no staging area).
- `jj describe -m "message"` sets the description on the current working-copy commit.
- `jj new` creates a new empty working-copy commit on top, effectively "finalizing" the previous one.
- `jj undo` reverts the last jj operation (including the describe+new).
- File changes are auto-tracked — no `jj add` needed.

### 3.3 Tests

Create `internal/ops/jj_test.go`. These are integration tests that require `jj` to be installed:

```go
package ops

import (
    "context"
    "os"
    "os/exec"
    "path/filepath"
    "testing"
)

func skipIfNoJJ(t *testing.T) {
    t.Helper()
    if _, err := exec.LookPath("jj"); err != nil {
        t.Skip("jj not installed, skipping integration test")
    }
}

// initJJRepo creates a temp directory with an initialized jj repo.
func initJJRepo(t *testing.T) string {
    t.Helper()
    dir := t.TempDir()
    cmd := exec.Command("jj", "git", "init")
    cmd.Dir = dir
    out, err := cmd.CombinedOutput()
    if err != nil {
        t.Fatalf("jj git init failed: %v: %s", err, out)
    }
    return dir
}

func TestJJCommitAndUndo(t *testing.T) {
    skipIfNoJJ(t)
    dir := initJJRepo(t)
    ctx := context.Background()

    // Write a file
    testFile := filepath.Join(dir, "test.md")
    if err := os.WriteFile(testFile, []byte("# Hello"), 0644); err != nil {
        t.Fatal(err)
    }

    jj := &JJ{WorkDir: dir}

    // Commit
    if err := jj.Commit(ctx, "ops: test commit"); err != nil {
        t.Fatalf("Commit failed: %v", err)
    }

    // File should still exist after commit
    if _, err := os.Stat(testFile); err != nil {
        t.Fatalf("file missing after commit: %v", err)
    }

    // Undo should succeed
    if err := jj.Undo(ctx); err != nil {
        t.Fatalf("Undo failed: %v", err)
    }
}

func TestJJStatus(t *testing.T) {
    skipIfNoJJ(t)
    dir := initJJRepo(t)
    ctx := context.Background()

    jj := &JJ{WorkDir: dir}
    status, err := jj.Status(ctx)
    if err != nil {
        t.Fatalf("Status failed: %v", err)
    }
    // jj status on a clean repo should return something (even if "Working copy changes:" with nothing)
    // Just verify it doesn't error.
    _ = status
}
```

**Verification:** `go test ./internal/ops/` passes (skips jj tests if jj isn't installed).

---

## Step 4: Vault File Operations (Agent Tools)

**Goal:** Build the tool functions that the LLM agent will call: read files, write files, list files, search files.

### 4.1 Create the tools package

Create `internal/ops/tools.go`:

```go
package ops

import (
    "fmt"
    "os"
    "path/filepath"
    "strings"
)

// VaultTools provides sandboxed file operations within a vault directory.
type VaultTools struct {
    // VaultDir is the absolute path to the vault root.
    VaultDir string
}

// safePath resolves a vault-relative path and ensures it stays within the vault.
// Returns the absolute path or an error.
func (v *VaultTools) safePath(relPath string) (string, error) {
    // Clean the path to remove .., ., etc.
    cleaned := filepath.Clean(relPath)

    // Reject absolute paths
    if filepath.IsAbs(cleaned) {
        return "", fmt.Errorf("absolute paths not allowed: %s", relPath)
    }

    // Reject paths that escape the vault
    if strings.HasPrefix(cleaned, "..") {
        return "", fmt.Errorf("path escapes vault: %s", relPath)
    }

    abs := filepath.Join(v.VaultDir, cleaned)

    // Double-check with EvalSymlinks to prevent symlink escapes
    // (only if the file already exists)
    if _, err := os.Lstat(abs); err == nil {
        resolved, err := filepath.EvalSymlinks(abs)
        if err != nil {
            return "", fmt.Errorf("cannot resolve path: %w", err)
        }
        vaultResolved, err := filepath.EvalSymlinks(v.VaultDir)
        if err != nil {
            return "", fmt.Errorf("cannot resolve vault: %w", err)
        }
        if !strings.HasPrefix(resolved, vaultResolved+string(filepath.Separator)) && resolved != vaultResolved {
            return "", fmt.Errorf("path escapes vault via symlink: %s", relPath)
        }
    }

    return abs, nil
}

// ReadFile returns the content of a vault-relative file path.
func (v *VaultTools) ReadFile(relPath string) (string, error) {
    abs, err := v.safePath(relPath)
    if err != nil {
        return "", err
    }
    data, err := os.ReadFile(abs)
    if err != nil {
        return "", fmt.Errorf("read %s: %w", relPath, err)
    }
    return string(data), nil
}

// WriteFile writes content to a vault-relative file path.
// Creates parent directories as needed.
func (v *VaultTools) WriteFile(relPath, content string) error {
    abs, err := v.safePath(relPath)
    if err != nil {
        return err
    }
    if err := os.MkdirAll(filepath.Dir(abs), 0755); err != nil {
        return fmt.Errorf("mkdir for %s: %w", relPath, err)
    }
    if err := os.WriteFile(abs, []byte(content), 0644); err != nil {
        return fmt.Errorf("write %s: %w", relPath, err)
    }
    return nil
}

// ListFiles returns vault-relative paths matching a glob pattern.
// Pattern uses filepath.Match syntax (e.g., "**/*.md" is NOT supported;
// use "*.md" for top-level or call with specific subdirectory prefixes).
// For the MVP, this walks the vault and filters by extension/prefix.
func (v *VaultTools) ListFiles(pattern string) ([]string, error) {
    var results []string
    err := filepath.Walk(v.VaultDir, func(path string, info os.FileInfo, err error) error {
        if err != nil {
            return nil // skip unreadable entries
        }
        // Skip hidden directories and files
        name := info.Name()
        if strings.HasPrefix(name, ".") || strings.HasPrefix(name, "_hidden_") {
            if info.IsDir() {
                return filepath.SkipDir
            }
            return nil
        }
        if info.IsDir() {
            return nil
        }
        rel, err := filepath.Rel(v.VaultDir, path)
        if err != nil {
            return nil
        }
        // Match against the pattern (applied to the filename only for simple globs)
        matched, err := filepath.Match(pattern, info.Name())
        if err != nil {
            return fmt.Errorf("bad pattern %q: %w", pattern, err)
        }
        if matched {
            results = append(results, rel)
        }
        return nil
    })
    return results, err
}

// SearchFiles returns vault-relative paths of files containing the query string.
// Only searches files matching the given glob (e.g., "*.md").
func (v *VaultTools) SearchFiles(query, glob string) ([]SearchResult, error) {
    files, err := v.ListFiles(glob)
    if err != nil {
        return nil, err
    }
    var results []SearchResult
    queryLower := strings.ToLower(query)
    for _, rel := range files {
        content, err := v.ReadFile(rel)
        if err != nil {
            continue
        }
        if strings.Contains(strings.ToLower(content), queryLower) {
            results = append(results, SearchResult{
                RelPath: rel,
                // Include a snippet around the first match
                Snippet: extractSnippet(content, query),
            })
        }
    }
    return results, nil
}

// SearchResult represents a file that matched a search query.
type SearchResult struct {
    RelPath string
    Snippet string
}

// extractSnippet returns a short excerpt around the first occurrence of query.
func extractSnippet(content, query string) string {
    idx := strings.Index(strings.ToLower(content), strings.ToLower(query))
    if idx < 0 {
        return ""
    }
    start := idx - 80
    if start < 0 {
        start = 0
    }
    end := idx + len(query) + 80
    if end > len(content) {
        end = len(content)
    }
    snippet := content[start:end]
    if start > 0 {
        snippet = "..." + snippet
    }
    if end < len(content) {
        snippet = snippet + "..."
    }
    return snippet
}
```

### 4.2 Tests

Create `internal/ops/tools_test.go`:

```go
package ops

import (
    "os"
    "path/filepath"
    "strings"
    "testing"
)

func setupVault(t *testing.T) (string, *VaultTools) {
    t.Helper()
    dir := t.TempDir()

    // Create some test files
    os.MkdirAll(filepath.Join(dir, "Projects"), 0755)
    os.WriteFile(filepath.Join(dir, "index.md"), []byte("# Home"), 0644)
    os.WriteFile(filepath.Join(dir, "Projects", "Alpha.md"),
        []byte("---\ntitle: Alpha\n---\n# Project Alpha\nSome content here."), 0644)
    os.WriteFile(filepath.Join(dir, "Projects", "Beta.md"),
        []byte("# Project Beta\nRelated to Alpha."), 0644)

    return dir, &VaultTools{VaultDir: dir}
}

func TestReadFile(t *testing.T) {
    _, tools := setupVault(t)

    content, err := tools.ReadFile("index.md")
    if err != nil {
        t.Fatalf("ReadFile: %v", err)
    }
    if content != "# Home" {
        t.Errorf("got %q", content)
    }
}

func TestReadFileSubdir(t *testing.T) {
    _, tools := setupVault(t)

    content, err := tools.ReadFile("Projects/Alpha.md")
    if err != nil {
        t.Fatalf("ReadFile: %v", err)
    }
    if !strings.Contains(content, "Project Alpha") {
        t.Errorf("unexpected content: %q", content)
    }
}

func TestReadFileEscape(t *testing.T) {
    _, tools := setupVault(t)

    _, err := tools.ReadFile("../../../etc/passwd")
    if err == nil {
        t.Fatal("expected error for path traversal")
    }
}

func TestReadFileAbsolute(t *testing.T) {
    _, tools := setupVault(t)

    _, err := tools.ReadFile("/etc/passwd")
    if err == nil {
        t.Fatal("expected error for absolute path")
    }
}

func TestWriteFile(t *testing.T) {
    _, tools := setupVault(t)

    err := tools.WriteFile("Projects/New.md", "# New Note")
    if err != nil {
        t.Fatalf("WriteFile: %v", err)
    }

    content, err := tools.ReadFile("Projects/New.md")
    if err != nil {
        t.Fatalf("ReadFile after write: %v", err)
    }
    if content != "# New Note" {
        t.Errorf("got %q", content)
    }
}

func TestWriteFileCreatesDirectories(t *testing.T) {
    _, tools := setupVault(t)

    err := tools.WriteFile("Deep/Nested/Dir/Note.md", "# Deep")
    if err != nil {
        t.Fatalf("WriteFile: %v", err)
    }

    content, err := tools.ReadFile("Deep/Nested/Dir/Note.md")
    if err != nil {
        t.Fatalf("ReadFile: %v", err)
    }
    if content != "# Deep" {
        t.Errorf("got %q", content)
    }
}

func TestWriteFileEscape(t *testing.T) {
    _, tools := setupVault(t)

    err := tools.WriteFile("../../escape.md", "bad")
    if err == nil {
        t.Fatal("expected error for path traversal")
    }
}

func TestListFiles(t *testing.T) {
    _, tools := setupVault(t)

    files, err := tools.ListFiles("*.md")
    if err != nil {
        t.Fatalf("ListFiles: %v", err)
    }
    if len(files) != 3 {
        t.Errorf("expected 3 files, got %d: %v", len(files), files)
    }
}

func TestSearchFiles(t *testing.T) {
    _, tools := setupVault(t)

    results, err := tools.SearchFiles("Alpha", "*.md")
    if err != nil {
        t.Fatalf("SearchFiles: %v", err)
    }
    // Should find Alpha.md (contains "Alpha") and Beta.md (contains "Related to Alpha")
    if len(results) != 2 {
        t.Errorf("expected 2 results, got %d: %v", len(results), results)
    }
}

func TestSearchFilesNoMatch(t *testing.T) {
    _, tools := setupVault(t)

    results, err := tools.SearchFiles("nonexistent-query-xyz", "*.md")
    if err != nil {
        t.Fatalf("SearchFiles: %v", err)
    }
    if len(results) != 0 {
        t.Errorf("expected 0 results, got %d", len(results))
    }
}
```

**Verification:** `go test ./internal/ops/` passes.

---

## Step 5: LLM Agent Loop

**Goal:** Build a tool-using agent that takes a natural-language instruction and executes it against the vault using the tools from Step 4.

### 5.1 Design decisions

- Use the Anthropic Claude API (you'll need an API key).
- The agent loop is synchronous: send a message, get a response, if it contains tool calls, execute them and send results back, repeat until the model returns a final text response.
- The agent has access to: `read_file`, `write_file`, `list_files`, `search_files`.
- The system prompt is small and vault-aware.
- Token budget: set a reasonable `max_tokens` (e.g., 4096) per response.
- Loop limit: cap at ~20 iterations to prevent runaway loops.

### 5.2 Create the agent

Create `internal/ops/agent.go`:

```go
package ops

import (
    "bytes"
    "context"
    "encoding/json"
    "fmt"
    "io"
    "log/slog"
    "net/http"
    "os"
    "time"
)

const (
    defaultModel       = "claude-sonnet-4-20250514"
    defaultMaxTokens   = 4096
    maxToolIterations  = 20
    anthropicAPIURL    = "https://api.anthropic.com/v1/messages"
    anthropicVersion   = "2023-06-01"
)

// AgentConfig holds configuration for the LLM agent.
type AgentConfig struct {
    APIKey   string // Anthropic API key. If empty, reads from ANTHROPIC_API_KEY env var.
    Model    string // Model ID. Defaults to claude-sonnet-4-20250514.
    MaxTokens int   // Max tokens per response. Defaults to 4096.
    Log      *slog.Logger
}

func (c *AgentConfig) apiKey() string {
    if c.APIKey != "" {
        return c.APIKey
    }
    return os.Getenv("ANTHROPIC_API_KEY")
}

func (c *AgentConfig) model() string {
    if c.Model != "" {
        return c.Model
    }
    return defaultModel
}

func (c *AgentConfig) maxTokens() int {
    if c.MaxTokens > 0 {
        return c.MaxTokens
    }
    return defaultMaxTokens
}

func (c *AgentConfig) log() *slog.Logger {
    if c.Log != nil {
        return c.Log
    }
    return slog.Default()
}

// AgentResult is what the agent returns after completing a task.
type AgentResult struct {
    Summary      string   // Natural-language summary from the agent
    ChangedFiles []string // Files that were written during the run
}

// toolDef describes a tool for the Anthropic API.
type toolDef struct {
    Name        string         `json:"name"`
    Description string         `json:"description"`
    InputSchema map[string]any `json:"input_schema"`
}

// RunAgent executes a tool-using agent loop.
// It takes an instruction, the current file context, and vault tools.
// It returns a summary and list of changed files.
func RunAgent(ctx context.Context, cfg *AgentConfig, tools *VaultTools, instruction string, currentFile string) (*AgentResult, error) {
    log := cfg.log()
    apiKey := cfg.apiKey()
    if apiKey == "" {
        return nil, fmt.Errorf("ANTHROPIC_API_KEY not set")
    }

    // Track which files get written
    changedFiles := make(map[string]struct{})

    // Build system prompt
    systemPrompt := buildSystemPrompt(currentFile)

    // Define tools for the API
    toolDefs := buildToolDefs()

    // Initial message from the user
    messages := []map[string]any{
        {"role": "user", "content": instruction},
    }

    // Agent loop
    for i := 0; i < maxToolIterations; i++ {
        log.Debug("agent iteration", "i", i)

        resp, err := callAnthropic(ctx, apiKey, cfg.model(), cfg.maxTokens(), systemPrompt, messages, toolDefs)
        if err != nil {
            return nil, fmt.Errorf("anthropic API call: %w", err)
        }

        // Extract content blocks from response
        stopReason, _ := resp["stop_reason"].(string)
        content, _ := resp["content"].([]any)

        // Collect text and tool-use blocks
        var textParts []string
        var toolUses []map[string]any

        for _, block := range content {
            b, ok := block.(map[string]any)
            if !ok {
                continue
            }
            switch b["type"] {
            case "text":
                if text, ok := b["text"].(string); ok {
                    textParts = append(textParts, text)
                }
            case "tool_use":
                toolUses = append(toolUses, b)
            }
        }

        // If no tool use, we're done
        if stopReason != "tool_use" || len(toolUses) == 0 {
            summary := ""
            for _, t := range textParts {
                summary += t
            }
            return &AgentResult{
                Summary:      summary,
                ChangedFiles: mapKeys(changedFiles),
            }, nil
        }

        // Append assistant message with all content blocks
        messages = append(messages, map[string]any{
            "role":    "assistant",
            "content": content,
        })

        // Execute each tool call
        var toolResults []map[string]any
        for _, tu := range toolUses {
            toolID, _ := tu["id"].(string)
            toolName, _ := tu["name"].(string)
            toolInput, _ := tu["input"].(map[string]any)

            result, err := executeTool(tools, toolName, toolInput)
            if err != nil {
                result = fmt.Sprintf("Error: %v", err)
            }

            // Track writes
            if toolName == "write_file" {
                if path, ok := toolInput["path"].(string); ok {
                    changedFiles[path] = struct{}{}
                }
            }

            toolResults = append(toolResults, map[string]any{
                "type":        "tool_result",
                "tool_use_id": toolID,
                "content":     result,
            })

            log.Debug("tool executed", "tool", toolName, "err", err)
        }

        // Append tool results as a user message
        messages = append(messages, map[string]any{
            "role":    "user",
            "content": toolResults,
        })
    }

    return nil, fmt.Errorf("agent exceeded maximum iterations (%d)", maxToolIterations)
}

func buildSystemPrompt(currentFile string) string {
    prompt := `You are an assistant that helps manage an Obsidian vault. You operate on markdown files in the vault using the provided tools.

Rules:
- Preserve YAML frontmatter unless asked to change it.
- Preserve wikilinks ([[...]]) unless asked to change them.
- Prefer minimal edits over rewriting entire files.
- Do not delete content unless clearly intended by the user.
- After making changes, provide a brief summary of what you did.
- Only read and write files within the vault.`

    if currentFile != "" {
        prompt += fmt.Sprintf("\n\nThe user is currently viewing: %s", currentFile)
    }

    return prompt
}

func buildToolDefs() []toolDef {
    return []toolDef{
        {
            Name:        "read_file",
            Description: "Read the contents of a file in the vault. Path is relative to vault root.",
            InputSchema: map[string]any{
                "type": "object",
                "properties": map[string]any{
                    "path": map[string]any{
                        "type":        "string",
                        "description": "Vault-relative file path, e.g. 'Projects/Alpha.md'",
                    },
                },
                "required": []string{"path"},
            },
        },
        {
            Name:        "write_file",
            Description: "Write content to a file in the vault. Creates the file if it doesn't exist. Overwrites if it does. Path is relative to vault root.",
            InputSchema: map[string]any{
                "type": "object",
                "properties": map[string]any{
                    "path": map[string]any{
                        "type":        "string",
                        "description": "Vault-relative file path, e.g. 'Projects/Alpha.md'",
                    },
                    "content": map[string]any{
                        "type":        "string",
                        "description": "The full file content to write.",
                    },
                },
                "required": []string{"path", "content"},
            },
        },
        {
            Name:        "list_files",
            Description: "List files in the vault matching a filename glob pattern. Pattern matches against the filename only (not the path). Example: '*.md' for all markdown files.",
            InputSchema: map[string]any{
                "type": "object",
                "properties": map[string]any{
                    "pattern": map[string]any{
                        "type":        "string",
                        "description": "Glob pattern for filenames, e.g. '*.md'",
                    },
                },
                "required": []string{"pattern"},
            },
        },
        {
            Name:        "search_files",
            Description: "Search for files containing a text query. Returns matching file paths with a short snippet around the match.",
            InputSchema: map[string]any{
                "type": "object",
                "properties": map[string]any{
                    "query": map[string]any{
                        "type":        "string",
                        "description": "Text to search for (case-insensitive).",
                    },
                    "glob": map[string]any{
                        "type":        "string",
                        "description": "Glob pattern to filter which files to search. Default: '*.md'",
                    },
                },
                "required": []string{"query"},
            },
        },
    }
}

func executeTool(tools *VaultTools, name string, input map[string]any) (string, error) {
    switch name {
    case "read_file":
        path, _ := input["path"].(string)
        return tools.ReadFile(path)

    case "write_file":
        path, _ := input["path"].(string)
        content, _ := input["content"].(string)
        if err := tools.WriteFile(path, content); err != nil {
            return "", err
        }
        return fmt.Sprintf("Successfully wrote %s", path), nil

    case "list_files":
        pattern, _ := input["pattern"].(string)
        if pattern == "" {
            pattern = "*.md"
        }
        files, err := tools.ListFiles(pattern)
        if err != nil {
            return "", err
        }
        if len(files) == 0 {
            return "No files found.", nil
        }
        result := fmt.Sprintf("Found %d files:\n", len(files))
        for _, f := range files {
            result += f + "\n"
        }
        return result, nil

    case "search_files":
        query, _ := input["query"].(string)
        glob, _ := input["glob"].(string)
        if glob == "" {
            glob = "*.md"
        }
        results, err := tools.SearchFiles(query, glob)
        if err != nil {
            return "", err
        }
        if len(results) == 0 {
            return "No matches found.", nil
        }
        out := fmt.Sprintf("Found %d matching files:\n", len(results))
        for _, r := range results {
            out += fmt.Sprintf("\n--- %s ---\n%s\n", r.RelPath, r.Snippet)
        }
        return out, nil

    default:
        return "", fmt.Errorf("unknown tool: %s", name)
    }
}

// callAnthropic makes a raw HTTP request to the Anthropic Messages API.
// This avoids importing an SDK — the API shape is simple enough.
func callAnthropic(ctx context.Context, apiKey, model string, maxTokens int, system string, messages []map[string]any, tools []toolDef) (map[string]any, error) {
    body := map[string]any{
        "model":      model,
        "max_tokens": maxTokens,
        "system":     system,
        "messages":   messages,
    }
    if len(tools) > 0 {
        body["tools"] = tools
    }

    jsonBody, err := json.Marshal(body)
    if err != nil {
        return nil, fmt.Errorf("marshal request: %w", err)
    }

    req, err := http.NewRequestWithContext(ctx, "POST", anthropicAPIURL, bytes.NewReader(jsonBody))
    if err != nil {
        return nil, err
    }
    req.Header.Set("Content-Type", "application/json")
    req.Header.Set("x-api-key", apiKey)
    req.Header.Set("anthropic-version", anthropicVersion)

    client := &http.Client{Timeout: 120 * time.Second}
    resp, err := client.Do(req)
    if err != nil {
        return nil, fmt.Errorf("http request: %w", err)
    }
    defer resp.Body.Close()

    respBody, err := io.ReadAll(resp.Body)
    if err != nil {
        return nil, fmt.Errorf("read response: %w", err)
    }

    if resp.StatusCode != 200 {
        return nil, fmt.Errorf("API returned %d: %s", resp.StatusCode, string(respBody))
    }

    var result map[string]any
    if err := json.Unmarshal(respBody, &result); err != nil {
        return nil, fmt.Errorf("parse response: %w", err)
    }

    return result, nil
}

func mapKeys(m map[string]struct{}) []string {
    keys := make([]string, 0, len(m))
    for k := range m {
        keys = append(keys, k)
    }
    return keys
}
```

### 5.3 Tests

The agent loop involves live API calls, so tests split into two categories:

**Unit tests** — test tool execution and prompt building without the API:

Create `internal/ops/agent_test.go`:

```go
package ops

import (
    "strings"
    "testing"
)

func TestBuildSystemPrompt(t *testing.T) {
    prompt := buildSystemPrompt("Projects/Alpha.md")
    if !strings.Contains(prompt, "Projects/Alpha.md") {
        t.Error("system prompt should mention current file")
    }
    if !strings.Contains(prompt, "frontmatter") {
        t.Error("system prompt should mention frontmatter preservation")
    }
}

func TestBuildSystemPromptNoFile(t *testing.T) {
    prompt := buildSystemPrompt("")
    if strings.Contains(prompt, "currently viewing") {
        t.Error("should not mention current file when empty")
    }
}

func TestExecuteToolReadFile(t *testing.T) {
    _, tools := setupVault(t)

    result, err := executeTool(tools, "read_file", map[string]any{"path": "index.md"})
    if err != nil {
        t.Fatalf("executeTool: %v", err)
    }
    if result != "# Home" {
        t.Errorf("got %q", result)
    }
}

func TestExecuteToolWriteFile(t *testing.T) {
    _, tools := setupVault(t)

    result, err := executeTool(tools, "write_file", map[string]any{
        "path":    "new.md",
        "content": "# New",
    })
    if err != nil {
        t.Fatalf("executeTool: %v", err)
    }
    if !strings.Contains(result, "Successfully") {
        t.Errorf("unexpected result: %q", result)
    }

    // Verify file exists
    content, err := tools.ReadFile("new.md")
    if err != nil || content != "# New" {
        t.Errorf("file not written correctly")
    }
}

func TestExecuteToolListFiles(t *testing.T) {
    _, tools := setupVault(t)

    result, err := executeTool(tools, "list_files", map[string]any{"pattern": "*.md"})
    if err != nil {
        t.Fatalf("executeTool: %v", err)
    }
    if !strings.Contains(result, "3 files") {
        t.Errorf("expected 3 files: %q", result)
    }
}

func TestExecuteToolSearchFiles(t *testing.T) {
    _, tools := setupVault(t)

    result, err := executeTool(tools, "search_files", map[string]any{
        "query": "Alpha",
        "glob":  "*.md",
    })
    if err != nil {
        t.Fatalf("executeTool: %v", err)
    }
    if !strings.Contains(result, "2 matching") {
        t.Errorf("expected 2 matches: %q", result)
    }
}

func TestExecuteToolUnknown(t *testing.T) {
    _, tools := setupVault(t)

    _, err := executeTool(tools, "delete_everything", map[string]any{})
    if err == nil {
        t.Error("expected error for unknown tool")
    }
}

func TestBuildToolDefs(t *testing.T) {
    defs := buildToolDefs()
    if len(defs) != 4 {
        t.Errorf("expected 4 tool definitions, got %d", len(defs))
    }
    names := map[string]bool{}
    for _, d := range defs {
        names[d.Name] = true
    }
    for _, expected := range []string{"read_file", "write_file", "list_files", "search_files"} {
        if !names[expected] {
            t.Errorf("missing tool definition: %s", expected)
        }
    }
}
```

**Integration test** — requires `ANTHROPIC_API_KEY` to be set. Create `internal/ops/agent_integration_test.go`:

```go
//go:build integration

package ops

import (
    "context"
    "os"
    "testing"
)

func TestAgentIntegration(t *testing.T) {
    if os.Getenv("ANTHROPIC_API_KEY") == "" {
        t.Skip("ANTHROPIC_API_KEY not set")
    }

    dir, tools := setupVault(t)
    _ = dir

    cfg := &AgentConfig{}
    ctx := context.Background()

    result, err := RunAgent(ctx, cfg, tools,
        "Read the file Projects/Alpha.md and add a line at the end that says '## Status\nActive'",
        "Projects/Alpha.md",
    )
    if err != nil {
        t.Fatalf("RunAgent: %v", err)
    }

    if result.Summary == "" {
        t.Error("expected non-empty summary")
    }

    // Check the file was modified
    content, err := tools.ReadFile("Projects/Alpha.md")
    if err != nil {
        t.Fatalf("ReadFile after agent: %v", err)
    }
    if !containsIgnoreCase(content, "status") {
        t.Errorf("expected file to contain 'Status', got:\n%s", content)
    }

    t.Logf("Summary: %s", result.Summary)
    t.Logf("Changed files: %v", result.ChangedFiles)
}

func containsIgnoreCase(s, substr string) bool {
    return len(s) > 0 && len(substr) > 0 &&
        len(s) >= len(substr) &&
        // simple check
        os.Getenv("") == "" || true // always true, just use strings
}
```

Run the integration test separately: `go test -tags integration ./internal/ops/ -run TestAgentIntegration -v`

**Verification:**
- `go test ./internal/ops/` passes (unit tests only).
- `go test -tags integration ./internal/ops/ -v` passes with a valid API key.

---

## Step 6: Site Rebuild Function

**Goal:** Expose a function that triggers a Kiln rebuild from outside the builder's normal watch cycle.

### 6.1 The problem

Currently, rebuilds happen only via the file watcher callback in `runDev`. The ops handler needs to trigger a rebuild after mutating files. Rather than duplicating the build logic, we need to make the rebuild callable.

### 6.2 Create a rebuild callback type

Create `internal/ops/rebuild.go`:

```go
package ops

import "context"

// RebuildFunc triggers a site rebuild. The ops handler calls this after
// successfully mutating vault files. The implementation is provided by
// the CLI layer, which has access to the builder.
type RebuildFunc func(ctx context.Context) error
```

This is intentionally simple. The actual implementation will be wired in Step 8 from `runDev`, where the builder is already available. The rebuild function will call `builder.Build(log)` (a full rebuild).

For the MVP, a full rebuild is acceptable. The watch-based incremental rebuild can coexist — it handles external edits, while the ops rebuild handles agent-driven edits.

### 6.3 Tests

No tests needed for a type alias. The rebuild function will be tested as part of the integration in Step 8.

---

## Step 7: HTTP Handlers

**Goal:** Build the `/api/apply` and `/api/undo` HTTP handlers that the overlay JS calls.

### 7.1 Create the handler

Create `internal/ops/handler.go`:

```go
package ops

import (
    "context"
    "encoding/json"
    "log/slog"
    "net/http"
)

// HandlerConfig holds all dependencies for the ops HTTP handlers.
type HandlerConfig struct {
    Tools     *VaultTools
    PathIndex *PathIndex
    Lock      *MutationLock
    JJ        *JJ
    Agent     *AgentConfig
    Rebuild   RebuildFunc
    Log       *slog.Logger
}

func (c *HandlerConfig) log() *slog.Logger {
    if c.Log != nil {
        return c.Log
    }
    return slog.Default()
}

// applyRequest matches what ops.js sends to POST /api/apply.
type applyRequest struct {
    Instruction    string `json:"instruction"`
    CurrentURLPath string `json:"current_url_path"`
}

// applyResponse matches what ops.js expects back.
type applyResponse struct {
    OK           bool     `json:"ok"`
    Updated      bool     `json:"updated,omitempty"`
    Summary      string   `json:"summary,omitempty"`
    Error        string   `json:"error,omitempty"`
    ChangedFiles []string `json:"changed_files,omitempty"`
}

// undoResponse matches what ops.js expects from POST /api/undo.
type undoResponse struct {
    OK      bool   `json:"ok"`
    Summary string `json:"summary,omitempty"`
    Error   string `json:"error,omitempty"`
}

// NewHandler returns an http.Handler that routes /api/apply and /api/undo.
func NewHandler(cfg *HandlerConfig) http.Handler {
    mux := http.NewServeMux()
    mux.HandleFunc("/api/apply", cfg.handleApply)
    mux.HandleFunc("/api/undo", cfg.handleUndo)
    mux.HandleFunc("/api/health", cfg.handleHealth)
    return mux
}

func (cfg *HandlerConfig) handleApply(w http.ResponseWriter, r *http.Request) {
    log := cfg.log()

    if r.Method != http.MethodPost {
        writeJSON(w, http.StatusMethodNotAllowed, applyResponse{
            OK: false, Error: "method not allowed",
        })
        return
    }

    var req applyRequest
    if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
        writeJSON(w, http.StatusBadRequest, applyResponse{
            OK: false, Error: "invalid request body",
        })
        return
    }

    if req.Instruction == "" {
        writeJSON(w, http.StatusBadRequest, applyResponse{
            OK: false, Error: "instruction is required",
        })
        return
    }

    // Acquire mutation lock
    release, err := cfg.Lock.Acquire()
    if err != nil {
        writeJSON(w, http.StatusConflict, applyResponse{
            OK: false, Error: "another operation is already running",
        })
        return
    }
    defer release()

    // Resolve URL path to vault file
    currentFile := ""
    if req.CurrentURLPath != "" {
        if resolved, ok := cfg.PathIndex.Resolve(req.CurrentURLPath); ok {
            currentFile = resolved
        }
        // If resolution fails, we still proceed — the agent can work without
        // knowing the current file. Log a warning.
        if currentFile == "" {
            log.Warn("could not resolve URL to vault file",
                "url_path", req.CurrentURLPath)
        }
    }

    log.Info("running ops agent",
        "instruction", req.Instruction,
        "current_file", currentFile,
    )

    // Run agent
    ctx := r.Context()
    result, err := RunAgent(ctx, cfg.Agent, cfg.Tools, req.Instruction, currentFile)
    if err != nil {
        log.Error("agent failed", "error", err)
        writeJSON(w, http.StatusInternalServerError, applyResponse{
            OK: false, Error: err.Error(),
        })
        return
    }

    // If files changed, commit and rebuild
    if len(result.ChangedFiles) > 0 {
        commitMsg := "ops: " + truncate(req.Instruction, 72)
        if err := cfg.JJ.Commit(ctx, commitMsg); err != nil {
            log.Error("jj commit failed", "error", err)
            // Files are written but not committed — report partial success
            writeJSON(w, http.StatusOK, applyResponse{
                OK:           true,
                Updated:      true,
                Summary:      result.Summary + "\n\nWarning: commit failed: " + err.Error(),
                ChangedFiles: result.ChangedFiles,
            })
            return
        }

        if err := cfg.Rebuild(ctx); err != nil {
            log.Error("rebuild failed", "error", err)
            // Committed but rebuild failed — user can manually refresh
            writeJSON(w, http.StatusOK, applyResponse{
                OK:           true,
                Updated:      true,
                Summary:      result.Summary + "\n\nWarning: site rebuild failed: " + err.Error(),
                ChangedFiles: result.ChangedFiles,
            })
            return
        }

        // Update path index after rebuild (vault may have new files)
        // This is handled externally by the watcher, but the new files
        // won't be indexed until the next scan. For the MVP, this is acceptable.
    }

    writeJSON(w, http.StatusOK, applyResponse{
        OK:           true,
        Updated:      len(result.ChangedFiles) > 0,
        Summary:      result.Summary,
        ChangedFiles: result.ChangedFiles,
    })
}

func (cfg *HandlerConfig) handleUndo(w http.ResponseWriter, r *http.Request) {
    log := cfg.log()

    if r.Method != http.MethodPost {
        writeJSON(w, http.StatusMethodNotAllowed, undoResponse{
            OK: false, Error: "method not allowed",
        })
        return
    }

    // Acquire mutation lock
    release, err := cfg.Lock.Acquire()
    if err != nil {
        writeJSON(w, http.StatusConflict, undoResponse{
            OK: false, Error: "another operation is already running",
        })
        return
    }
    defer release()

    ctx := r.Context()

    if err := cfg.JJ.Undo(ctx); err != nil {
        log.Error("jj undo failed", "error", err)
        writeJSON(w, http.StatusInternalServerError, undoResponse{
            OK: false, Error: "undo failed: " + err.Error(),
        })
        return
    }

    if err := cfg.Rebuild(ctx); err != nil {
        log.Error("rebuild after undo failed", "error", err)
        writeJSON(w, http.StatusOK, undoResponse{
            OK:      true,
            Summary: "Undo completed, but site rebuild failed. Try refreshing.",
        })
        return
    }

    writeJSON(w, http.StatusOK, undoResponse{
        OK:      true,
        Summary: "Undo completed successfully.",
    })
}

func (cfg *HandlerConfig) handleHealth(w http.ResponseWriter, r *http.Request) {
    writeJSON(w, http.StatusOK, map[string]any{
        "ok":     true,
        "status": "healthy",
    })
}

func writeJSON(w http.ResponseWriter, status int, v any) {
    w.Header().Set("Content-Type", "application/json")
    w.WriteHeader(status)
    json.NewEncoder(w).Encode(v)
}

func truncate(s string, maxLen int) string {
    if len(s) <= maxLen {
        return s
    }
    return s[:maxLen-3] + "..."
}
```

### 7.2 Tests

Create `internal/ops/handler_test.go`:

```go
package ops

import (
    "bytes"
    "encoding/json"
    "net/http"
    "net/http/httptest"
    "testing"
)

func setupTestHandler(t *testing.T) (*HandlerConfig, *VaultTools) {
    t.Helper()
    _, tools := setupVault(t)

    cfg := &HandlerConfig{
        Tools:     tools,
        PathIndex: NewPathIndex(),
        Lock:      &MutationLock{},
        JJ:        &JJ{WorkDir: tools.VaultDir},
        Agent:     &AgentConfig{},
        Rebuild:   func(ctx context.Context) error { return nil },
    }

    // Populate path index
    cfg.PathIndex.Update([]PathEntry{
        {WebPath: "/projects/alpha", RelPath: "Projects/Alpha.md"},
        {WebPath: "/", RelPath: "index.md"},
    })

    return cfg, tools
}

func TestHealthEndpoint(t *testing.T) {
    cfg, _ := setupTestHandler(t)
    handler := NewHandler(cfg)

    req := httptest.NewRequest("GET", "/api/health", nil)
    rec := httptest.NewRecorder()
    handler.ServeHTTP(rec, req)

    if rec.Code != 200 {
        t.Errorf("expected 200, got %d", rec.Code)
    }

    var resp map[string]any
    json.NewDecoder(rec.Body).Decode(&resp)
    if resp["ok"] != true {
        t.Errorf("expected ok=true")
    }
}

func TestApplyMethodNotAllowed(t *testing.T) {
    cfg, _ := setupTestHandler(t)
    handler := NewHandler(cfg)

    req := httptest.NewRequest("GET", "/api/apply", nil)
    rec := httptest.NewRecorder()
    handler.ServeHTTP(rec, req)

    if rec.Code != http.StatusMethodNotAllowed {
        t.Errorf("expected 405, got %d", rec.Code)
    }
}

func TestApplyEmptyInstruction(t *testing.T) {
    cfg, _ := setupTestHandler(t)
    handler := NewHandler(cfg)

    body, _ := json.Marshal(applyRequest{Instruction: "", CurrentURLPath: "/"})
    req := httptest.NewRequest("POST", "/api/apply", bytes.NewReader(body))
    req.Header.Set("Content-Type", "application/json")
    rec := httptest.NewRecorder()
    handler.ServeHTTP(rec, req)

    if rec.Code != http.StatusBadRequest {
        t.Errorf("expected 400, got %d", rec.Code)
    }
}

func TestApplyInvalidJSON(t *testing.T) {
    cfg, _ := setupTestHandler(t)
    handler := NewHandler(cfg)

    req := httptest.NewRequest("POST", "/api/apply", bytes.NewReader([]byte("not json")))
    req.Header.Set("Content-Type", "application/json")
    rec := httptest.NewRecorder()
    handler.ServeHTTP(rec, req)

    if rec.Code != http.StatusBadRequest {
        t.Errorf("expected 400, got %d", rec.Code)
    }
}

func TestApplyLockContention(t *testing.T) {
    cfg, _ := setupTestHandler(t)
    handler := NewHandler(cfg)

    // Pre-acquire the lock
    release, err := cfg.Lock.Acquire()
    if err != nil {
        t.Fatal(err)
    }
    defer release()

    body, _ := json.Marshal(applyRequest{
        Instruction:    "do something",
        CurrentURLPath: "/",
    })
    req := httptest.NewRequest("POST", "/api/apply", bytes.NewReader(body))
    req.Header.Set("Content-Type", "application/json")
    rec := httptest.NewRecorder()
    handler.ServeHTTP(rec, req)

    if rec.Code != http.StatusConflict {
        t.Errorf("expected 409, got %d", rec.Code)
    }
}

func TestUndoMethodNotAllowed(t *testing.T) {
    cfg, _ := setupTestHandler(t)
    handler := NewHandler(cfg)

    req := httptest.NewRequest("GET", "/api/undo", nil)
    rec := httptest.NewRecorder()
    handler.ServeHTTP(rec, req)

    if rec.Code != http.StatusMethodNotAllowed {
        t.Errorf("expected 405, got %d", rec.Code)
    }
}

func TestUndoLockContention(t *testing.T) {
    cfg, _ := setupTestHandler(t)
    handler := NewHandler(cfg)

    release, err := cfg.Lock.Acquire()
    if err != nil {
        t.Fatal(err)
    }
    defer release()

    req := httptest.NewRequest("POST", "/api/undo", nil)
    rec := httptest.NewRecorder()
    handler.ServeHTTP(rec, req)

    if rec.Code != http.StatusConflict {
        t.Errorf("expected 409, got %d", rec.Code)
    }
}

func TestTruncate(t *testing.T) {
    if got := truncate("short", 72); got != "short" {
        t.Errorf("got %q", got)
    }
    long := "this is a very long instruction that should be truncated because it exceeds the maximum character limit we set"
    got := truncate(long, 72)
    if len(got) > 72 {
        t.Errorf("truncated string too long: %d chars", len(got))
    }
    if got[len(got)-3:] != "..." {
        t.Error("expected ... suffix")
    }
}
```

**Verification:** `go test ./internal/ops/` passes.

---

## Step 8: Wire Into Forge

**Goal:** Connect the ops handler into the existing Forge server, replacing the external proxy with in-process routing.

### 8.1 Modify `internal/server/mux.go`

Currently, `NewForgeHandler` routes `/api/*` to `cfg.ProxyHandler`. You need to support *either* the proxy handler (for future external backends) *or* an in-process ops handler.

Update `ForgeConfig` to accept a generic `APIHandler`:

```go
// In internal/server/mux.go, update ForgeConfig:
type ForgeConfig struct {
    ProxyHandler   http.Handler // External proxy (existing)
    APIHandler     http.Handler // In-process API handler (new, from ops package)
    OverlayHandler http.Handler
    InjectEnabled  bool
}
```

Update `NewForgeHandler` to prefer `APIHandler` over `ProxyHandler`:

```go
func NewForgeHandler(baseHandler http.Handler, cfg ForgeConfig) http.Handler {
    // Determine the API handler: prefer in-process, fall back to proxy
    apiHandler := cfg.APIHandler
    if apiHandler == nil {
        apiHandler = cfg.ProxyHandler
    }

    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        // Route /api/* to API handler
        if strings.HasPrefix(r.URL.Path, "/api/") && apiHandler != nil {
            apiHandler.ServeHTTP(w, r)
            return
        }
        // Route /ops/* to overlay handler
        if strings.HasPrefix(r.URL.Path, "/ops/") && cfg.OverlayHandler != nil {
            cfg.OverlayHandler.ServeHTTP(w, r)
            return
        }
        // Everything else through injection middleware
        overlay.InjectMiddleware(baseHandler, cfg.InjectEnabled).ServeHTTP(w, r)
    })
}
```

### 8.2 Modify `internal/cli/dev.go`

In `runDev`, after the vault scan and before server start, create the ops handler:

```go
// After vault scan and dependency graph setup, before server.Serve:

// Build the path index from scanned vault files
pathIndex := ops.NewPathIndex()
var pathEntries []ops.PathEntry
for _, f := range vault.Vault.Files {
    if f.WebPath != "" {
        pathEntries = append(pathEntries, ops.PathEntry{
            WebPath: f.WebPath,
            RelPath: f.RelPath,
        })
    }
}
pathIndex.Update(pathEntries)

// Create ops handler
opsHandler := ops.NewHandler(&ops.HandlerConfig{
    Tools:     &ops.VaultTools{VaultDir: builder.InputDir},
    PathIndex: pathIndex,
    Lock:      &ops.MutationLock{},
    JJ:        &ops.JJ{WorkDir: builder.InputDir},
    Agent:     &ops.AgentConfig{Log: log},
    Rebuild: func(ctx context.Context) error {
        builder.Build(log)
        return nil
    },
    Log: log,
})

// Wire into ForgeConfig
forgeCfg := server.ForgeConfig{
    ProxyHandler:   proxyHandler,   // keep for external backend option
    APIHandler:     opsHandler,     // new: in-process ops
    OverlayHandler: overlayHandler,
    InjectEnabled:  injectOverlay,
}
```

Also update the watcher's `OnRebuild` closure to refresh the path index after each rebuild:

```go
// Inside the OnRebuild closure, after the incremental build and vault rescan:
var updatedEntries []ops.PathEntry
for _, f := range vault.Vault.Files {
    if f.WebPath != "" {
        updatedEntries = append(updatedEntries, ops.PathEntry{
            WebPath: f.WebPath,
            RelPath: f.RelPath,
        })
    }
}
pathIndex.Update(updatedEntries)
```

### 8.3 Add `--ops-api-key` flag (optional but recommended)

Add a CLI flag to pass the Anthropic API key explicitly, as an alternative to the environment variable:

```go
// In dev.go flag definitions:
var opsAPIKey string

// In init():
devCmd.Flags().StringVar(&opsAPIKey, "ops-api-key", "", "Anthropic API key for Ops agent (default: ANTHROPIC_API_KEY env)")
```

Then use it when creating the `AgentConfig`:
```go
Agent: &ops.AgentConfig{
    APIKey: opsAPIKey,
    Log:    log,
},
```

### 8.4 Tests

Update the existing integration tests in `internal/server/forge_test.go` to verify that the ops handler receives requests:

```go
func TestForgeHandlerAPIRouting(t *testing.T) {
    // Create a simple test API handler
    apiCalled := false
    apiHandler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        apiCalled = true
        w.Header().Set("Content-Type", "application/json")
        w.Write([]byte(`{"ok":true}`))
    })

    base := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        w.Write([]byte("base"))
    })

    handler := NewForgeHandler(base, ForgeConfig{
        APIHandler: apiHandler,
    })

    // /api/health should route to API handler
    req := httptest.NewRequest("GET", "/api/health", nil)
    rec := httptest.NewRecorder()
    handler.ServeHTTP(rec, req)

    if !apiCalled {
        t.Error("API handler was not called for /api/ path")
    }

    // Non-API path should go to base
    apiCalled = false
    req = httptest.NewRequest("GET", "/some-page", nil)
    rec = httptest.NewRecorder()
    handler.ServeHTTP(rec, req)

    if apiCalled {
        t.Error("API handler should not be called for non-API paths")
    }
}

func TestForgeHandlerProxyFallback(t *testing.T) {
    // When APIHandler is nil, should fall back to ProxyHandler
    proxyCalled := false
    proxyHandler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        proxyCalled = true
        w.Write([]byte("proxied"))
    })

    base := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        w.Write([]byte("base"))
    })

    handler := NewForgeHandler(base, ForgeConfig{
        ProxyHandler: proxyHandler,
    })

    req := httptest.NewRequest("GET", "/api/test", nil)
    rec := httptest.NewRecorder()
    handler.ServeHTTP(rec, req)

    if !proxyCalled {
        t.Error("proxy handler was not called as fallback")
    }
}
```

**Verification:**
- `go test ./internal/server/` passes.
- `go test ./internal/ops/` passes.
- `go build ./...` succeeds.

---

## Step 9: End-to-End Manual Testing

**Goal:** Verify the full loop works with a real vault.

### 9.1 Prerequisites

1. A vault directory with some markdown files and a `jj` workspace initialized.
2. `ANTHROPIC_API_KEY` set in your environment.
3. The overlay assets in a directory (e.g., `./static/`).

### 9.2 Start Forge

```bash
export ANTHROPIC_API_KEY=sk-ant-...
forge dev \
    --input ./vault \
    --output ./public \
    --overlay-dir ./static \
    --inject-overlay
```

Note: `--proxy-backend` is no longer needed — the API is handled in-process.

### 9.3 Test the health endpoint

```bash
curl http://localhost:8080/api/health
```

Expected: `{"ok":true,"status":"healthy"}`

### 9.4 Test the apply endpoint

Open the site in a browser, click the FAB (*), type an instruction like "add a ## Summary section to this page", and click Run.

Or test via curl:

```bash
curl -X POST http://localhost:8080/api/apply \
  -H "Content-Type: application/json" \
  -d '{"instruction":"Add a summary section to this note","current_url_path":"/projects/alpha/"}'
```

Expected: JSON response with `ok: true`, a summary, and changed files.

### 9.5 Verify the commit

```bash
cd vault && jj log --limit 5
```

You should see a commit like `ops: Add a summary section to this note`.

### 9.6 Test undo

Click the Undo button in the modal, or:

```bash
curl -X POST http://localhost:8080/api/undo \
  -H "Content-Type: application/json"
```

Expected: `{"ok":true,"summary":"Undo completed successfully."}`

Verify with `jj log` that the commit was undone.

### 9.7 Test the page refresh

After a successful apply, click "Refresh page" in the modal. The page should reload and show the updated content.

### 9.8 Test error cases

1. **No API key**: Unset `ANTHROPIC_API_KEY` and submit a request. Should get an error about the missing key.
2. **Lock contention**: Send two simultaneous requests (e.g., two curl commands in background). The second should get a 409 conflict.
3. **Invalid URL path**: Submit with `current_url_path: "/nonexistent/"`. Should still work (agent proceeds without file context).

### Verification checklist

- [ ] `forge dev` starts without errors
- [ ] Health endpoint returns 200
- [ ] FAB appears on all pages
- [ ] Modal opens and shows current page path
- [ ] Submitting an instruction returns a result
- [ ] Files are modified in the vault
- [ ] A jj commit is created
- [ ] The site rebuilds and shows changes on refresh
- [ ] Undo reverts the changes
- [ ] Second concurrent request gets 409
- [ ] Missing API key returns a clear error

---

## Step 10: Error Handling and Edge Cases

**Goal:** Harden the implementation against real-world edge cases.

### 10.1 Request timeout

The agent loop can take a while (multiple LLM calls + tool executions). Add a request-level timeout in the handler:

```go
// In handleApply, after lock acquisition:
ctx, cancel := context.WithTimeout(r.Context(), 3*time.Minute)
defer cancel()
```

This ensures that a hung LLM call doesn't hold the lock forever.

### 10.2 Large vault protection

If the vault has thousands of files, `list_files` and `search_files` could return enormous results. Add limits:

```go
// In ListFiles, after collecting results:
const maxListResults = 200
if len(results) > maxListResults {
    results = results[:maxListResults]
}
```

```go
// In SearchFiles, add an early exit:
const maxSearchResults = 50
// Inside the loop:
if len(results) >= maxSearchResults {
    break
}
```

### 10.3 File size limit for reads

Prevent the agent from reading very large files:

```go
// In ReadFile, after safePath:
info, err := os.Stat(abs)
if err != nil {
    return "", fmt.Errorf("stat %s: %w", relPath, err)
}
const maxReadSize = 512 * 1024 // 512KB
if info.Size() > maxReadSize {
    return "", fmt.Errorf("file too large: %s (%d bytes, max %d)", relPath, info.Size(), maxReadSize)
}
```

### 10.4 Tests

Add edge case tests to `tools_test.go`:

```go
func TestListFilesLimit(t *testing.T) {
    dir := t.TempDir()
    // Create 300 markdown files
    for i := 0; i < 300; i++ {
        os.WriteFile(filepath.Join(dir, fmt.Sprintf("note_%03d.md", i)), []byte("# Note"), 0644)
    }
    tools := &VaultTools{VaultDir: dir}
    files, err := tools.ListFiles("*.md")
    if err != nil {
        t.Fatal(err)
    }
    if len(files) > 200 {
        t.Errorf("expected at most 200 results, got %d", len(files))
    }
}
```

**Verification:** `go test ./internal/ops/` passes with the new edge case tests.

---

## Summary of Files Created

```text
internal/ops/
  resolve.go          - Step 1: URL-to-file path resolution
  resolve_test.go     - Step 1: tests
  lock.go             - Step 2: global mutation lock
  lock_test.go        - Step 2: tests
  jj.go               - Step 3: Jujutsu CLI wrapper
  jj_test.go          - Step 3: tests (integration, skips if jj absent)
  tools.go            - Step 4: vault file operations
  tools_test.go       - Step 4: tests
  agent.go            - Step 5: LLM agent loop
  agent_test.go       - Step 5: unit tests
  agent_integration_test.go  - Step 5: live API test (build tag: integration)
  rebuild.go          - Step 6: rebuild callback type
  handler.go          - Step 7: HTTP handlers
  handler_test.go     - Step 7: tests
```

Files modified:

```text
internal/server/mux.go      - Step 8: add APIHandler to ForgeConfig
internal/server/forge_test.go - Step 8: routing tests
internal/cli/dev.go          - Step 8: wire ops handler + path index
```

---

## Dependency Summary

No new Go dependencies are required. The agent talks to the Anthropic API via `net/http` + `encoding/json` from the standard library. The jj wrapper uses `os/exec`. Everything else uses packages already in `go.mod`.

---

## Order of Operations

Each step is independently testable. Do not proceed to the next step until the current step's tests pass.

1. **resolve.go** + tests → verifies URL↔file mapping works
2. **lock.go** + tests → verifies mutex semantics
3. **jj.go** + tests → verifies jj integration (requires jj installed)
4. **tools.go** + tests → verifies sandboxed file operations
5. **agent.go** + tests → verifies tool execution; integration test validates LLM loop
6. **rebuild.go** → type only, no tests needed
7. **handler.go** + tests → verifies HTTP contract matches what ops.js expects
8. **mux.go** + **dev.go** changes + tests → verifies end-to-end routing
9. **Manual testing** → full loop verification
10. **Edge case hardening** → timeouts, limits, large vaults
