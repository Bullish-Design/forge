# Forge Refactoring Guide

Step-by-step implementation plan for all fixes, improvements, and recommendations from CODE_REVIEW.md. Each step includes the exact files/lines to change, the transformation to apply, and how to validate correctness.

**Pre-requisite for every step:** Run `devenv shell -- go build ./...` and `devenv shell -- go test ./...` after each change to ensure nothing regresses.

---

## Table of Contents

- [Phase 1: Critical Bug Fixes](#phase-1-critical-bug-fixes) (5 steps)
- [Phase 2: High-Severity Correctness Fixes](#phase-2-high-severity-correctness-fixes) (12 steps)
- [Phase 3: Architectural Refactoring — Builder](#phase-3-architectural-refactoring--builder) (6 steps)
- [Phase 4: Architectural Refactoring — Error Handling](#phase-4-architectural-refactoring--error-handling) (4 steps)
- [Phase 5: Medium-Severity Fixes](#phase-5-medium-severity-fixes) (15 steps)
- [Phase 6: Test Coverage Expansion](#phase-6-test-coverage-expansion) (8 steps)
- [Phase 7: JavaScript & CSS Cleanup](#phase-7-javascript--css-cleanup) (8 steps)
- [Phase 8: Low-Severity Polish](#phase-8-low-severity-polish) (12 steps)

---

## Phase 1: Critical Bug Fixes

These are correctness bugs that can cause crashes, data loss, or silently wrong output. Each is a small, isolated change.

---

### Step 1.1 — Remove Dead Code After log.Fatal()

**Review item:** C2
**File:** `cmd/forge/main.go:23-25`

**Current code:**
```go
if err := rootCmd.Execute(); err != nil {
    log.Fatal(err)
    os.Exit(1) // unreachable
}
```

**Change:** Remove the `os.Exit(1)` line entirely. `log.Fatal()` (charmbracelet/log) already calls `os.Exit(1)`.

**Validation:**
1. `devenv shell -- go build ./cmd/forge` compiles.
2. Run `devenv shell -- go run ./cmd/forge nonexistent-command` — should exit with status 1 and print a useful error.
3. Run `devenv shell -- go vet ./cmd/forge` — no warnings.

---

### Step 1.3 — Guard CleanOutputDir Against Dangerous Paths

**Review item:** C4
**File:** `internal/builder/utils.go:47-54`

**Current code:**
```go
func CleanOutputDir(log *slog.Logger) {
    err := os.RemoveAll(OutputDir)
    ...
}
```

**Change:** Add validation before the `os.RemoveAll`:
```go
func CleanOutputDir(log *slog.Logger) {
    if OutputDir == "" {
        log.Error("OutputDir is empty, refusing to clean")
        return
    }
    abs, err := filepath.Abs(OutputDir)
    if err != nil {
        log.Error("cannot resolve OutputDir", "error", err)
        return
    }
    // Refuse to delete filesystem root or home directory
    home, _ := os.UserHomeDir()
    if abs == "/" || abs == home || abs == "." {
        log.Error("OutputDir resolves to a dangerous path, refusing to clean", "path", abs)
        return
    }
    err = os.RemoveAll(OutputDir)
    ...
}
```

**Validation:**
1. `devenv shell -- go build ./...` compiles.
2. Write a test `TestCleanOutputDir_RefusesDangerousPaths`:
   - Set `OutputDir = ""` → verify no deletion occurs.
   - Set `OutputDir = "/"` → verify no deletion occurs.
   - Set `OutputDir = os.UserHomeDir()` → verify no deletion occurs.
   - Set `OutputDir` to a temp directory, create a file in it, call `CleanOutputDir`, verify the directory is removed.
3. Existing `devenv shell -- go test ./internal/builder/...` passes.

---

### Step 1.4 — Fix Panic on Nil File in Asset Writing

**Review item:** C5
**File:** `internal/builder/builder_default.go:287-386`

There are 9 asset-writing blocks (style.css, shared.css, app.js, graph.js, canvas.js, search.js, link-preview.js, giscus-theme-light.css, giscus-theme-dark.css) that all follow this broken pattern:

```go
out, err := os.Create(path)
if err != nil {
    log.Error("Couldn't create ...", "error", err)
}
defer out.Close()          // panics if out is nil
err = tmpl.Execute(out, s) // panics if out is nil
```

**Change:** For each block, add a `return` or `continue` (depending on context) after the error log, so execution does not reach the nil file handle:

```go
out, err := os.Create(path)
if err != nil {
    log.Error("Couldn't create ...", "error", err)
    return // or: skip this asset and continue to next
}
defer out.Close()
```

**IMPORTANT:** Better yet — extract a helper (this also addresses M15 and H1):

```go
func writeTemplate(path string, tmpl *template.Template, data any, log *slog.Logger) error {
    f, err := os.Create(path)
    if err != nil {
        return fmt.Errorf("create %s: %w", path, err)
    }
    defer f.Close()
    if err := tmpl.Execute(f, data); err != nil {
        return fmt.Errorf("execute template for %s: %w", path, err)
    }
    return nil
}
```

Then replace each block with:
```go
if err := writeTemplate(filepath.Join(OutputDir, "style.css"), site.Layout.CssTemplate, site, log); err != nil {
    log.Error("asset write failed", "error", err)
}
```

**Affected lines:** Approximately 287-295, 298-305, 308-316, 319-327, 330-338, 341-349, 352-360, 364-373, 376-386.

**Validation:**
1. `devenv shell -- go build ./...` compiles.
2. `devenv shell -- go test ./internal/builder/...` passes.
3. Write a test for `writeTemplate`: pass a path in a non-existent directory → verify it returns an error (not a panic). Pass a valid path with a valid template → verify file is created with correct content.
4. Manual test: run `devenv shell -- go run ./cmd/forge generate` on the demo vault. Verify all asset files are created in `demo/public/`.

---

### Step 1.5 — Add HTML Escaping to String-Concatenated Output

**Review item:** H3
**Files:**
- `internal/obsidian/markdown/transformer.go` — callout title (line ~147), mermaid data-original (line ~78)
- `internal/obsidian/markdown/toc.go` — heading text and ID in `<a>` tag (line ~38)
- `internal/obsidian/markdown/wikilinks.go` — broken embed link (line ~580)

**Change for each location:**

1. Add `"html"` to imports where not already present.

2. **transformer.go callout title** (inside `transformCallouts`, the `sb.WriteString` that injects `cTitle`):
   ```go
   // Before:
   sb.WriteString(`<div class="callout-title-inner">` + cTitle + `</div>`)
   // After:
   sb.WriteString(`<div class="callout-title-inner">` + html.EscapeString(cTitle) + `</div>`)
   ```

3. **transformer.go mermaid data-original** (inside `transformMermaid`):
   The `data-original` attribute already uses `template.HTMLEscapeString(content)` for the attribute value, but the raw `content` is also injected as the div's inner text. Ensure the inner content is also escaped or wrapped in a `<code>` block that prevents rendering. Verify the current pattern — if `content` is already HTML-escaped for the attribute but raw for inner text, escape the inner text too.

4. **toc.go heading text** (line ~38):
   ```go
   // Before:
   fmt.Sprintf(`<li class="toc-level-%d"><a href="#%s">%s</a></li>`, h.Level, id, text)
   // After:
   fmt.Sprintf(`<li class="toc-level-%d"><a href="#%s">%s</a></li>`, h.Level, url.PathEscape(id), html.EscapeString(text))
   ```
   Add `"html"` and `"net/url"` to imports.

5. **wikilinks.go broken embed link** (line ~580):
   ```go
   // Before:
   w.WriteString("<a href=\"" + webPath + "\" class=\"broken-embed\">" + string(n.Target) + "</a>")
   // After:
   w.WriteString("<a href=\"" + html.EscapeString(webPath) + "\" class=\"broken-embed\">" + html.EscapeString(string(n.Target)) + "</a>")
   ```

**Validation:**
1. `devenv shell -- go build ./...` compiles.
2. `devenv shell -- go test ./internal/obsidian/...` passes.
3. Write test cases with special characters in:
   - A callout title containing `<script>alert(1)</script>` → verify the output contains `&lt;script&gt;` not raw `<script>`.
   - A heading containing `Heading with & and <angle>` → verify TOC renders `&amp;` and `&lt;angle&gt;`.
   - A broken wikilink target containing `"onclick="alert(1)` → verify the output attribute is properly escaped.
4. Build the demo vault and spot-check the HTML output for any rendering regressions.

---

## Phase 2: High-Severity Correctness Fixes

These fix incorrect behavior that doesn't crash but produces wrong results.

---

### Step 2.1 — Fix Wikilink Path Matching (Too Loose)

**Review item:** H6
**File:** `internal/obsidian/markdown/wikilinks.go:103-109`

**Current code:**
```go
if strings.Contains(dest, "/") || strings.Contains(dest, "\\") {
    for _, file := range candidates {
        if strings.Contains(file.RelPath, dest) {
            bestMatch = file
            break
        }
    }
}
```

**Change:** Replace `strings.Contains(file.RelPath, dest)` with a proper suffix match:
```go
if strings.HasSuffix(file.RelPath, "/"+dest) || file.RelPath == dest {
    bestMatch = file
    break
}
```

This ensures `Folder/Note` only matches `SomeFolder/Folder/Note` (suffix after `/`) or an exact match, and not `MyFolder/NoteBook` (substring).

**Validation:**
1. `devenv shell -- go test ./internal/obsidian/markdown/...` passes.
2. Add a test case to `wikilinks_test.go`:
   - Index contains `blog/Note.md` and `blog/NoteBook.md`.
   - Resolve `[[blog/Note]]` → should match `blog/Note.md`, NOT `blog/NoteBook.md`.
   - Resolve `[[Folder/Note]]` with files `Other/Folder/Note.md` and `Folder/NoteStuff.md` → should match the first, not the second.
3. Build demo vault, verify all wikilinks still resolve correctly.

---

### Step 2.2 — Propagate Vault Scan Errors in Dev Mode

**Review item:** H7
**File:** `internal/cli/dev.go:159-170`

**Current code:**
```go
if err := vault.Scan(); err != nil {
    log.Error("failed to rescan vault", "err", err)
    return nil  // ← hides error
}
```

**Change:** Return the error so the watcher's `OnRebuild` callback knows the rebuild failed:
```go
if err := vault.Scan(); err != nil {
    return fmt.Errorf("rescan vault: %w", err)
}
```

Ensure the watcher's error handling (in `watcher.go`, line ~94) logs rebuild errors prominently. The watcher already logs errors from the callback:
```go
if err := w.OnRebuild(); err != nil {
    w.Log.Warn("rebuild error", "err", err)
}
```
**NOTE:** Consider upgrading this to `w.Log.Error(...)` since a failed rebuild means the served site is stale.

**Validation:**
1. `devenv shell -- go build ./...` compiles.
2. Manual test: start `forge dev`, then make the input directory unreadable temporarily. Verify the error appears in the console at Error level, not silently swallowed.
3. Verify normal operation: start `forge dev`, edit a file, verify the rebuild succeeds and the page reloads.

---

### Step 2.3 — Fix ops/tools.go Glob to Match Full Path

**Review item:** H8
**File:** `internal/ops/tools.go:116`

**Current code:**
```go
filepath.Match(pattern, info.Name())
```

**Change:**
```go
filepath.Match(pattern, rel)
```

Where `rel` is the relative path already computed on line ~108 via `filepath.Rel(v.VaultDir, path)`.

Also note: `filepath.Match` does not support `**` (recursive glob). If recursive patterns are needed, use `doublestar` library or document the limitation.

**Validation:**
1. `devenv shell -- go test ./internal/ops/...` passes.
2. Add test cases to `tools_test.go`:
   - `ListFiles("blog/*.md")` with vault containing `blog/post.md` and `other/note.md` → should return only `blog/post.md`.
   - `ListFiles("*.md")` → should match only root-level `.md` files (not nested).
   - Verify the existing tests still pass (they likely use simple `*.md` patterns matching filenames).

---

### Step 2.4 — Reuse HTTP Client in Agent

**Review item:** H9
**File:** `internal/ops/agent.go` — lines 544, 581, 644

**Current code:** Three separate functions each create `&http.Client{Timeout: ...}`:
- `callAnthropic()` at line 544 (120s timeout)
- `resolveOpenAIModel()` at line 581 (30s timeout)
- `callOpenAIChatCompletion()` at line 644 (120s timeout)

**Change:** Create a package-level or struct-level client. Since `AgentConfig` is already passed around, add a client field:

```go
// In agent.go, near the type definitions
var defaultAgentClient = &http.Client{
    Timeout: 120 * time.Second,
    Transport: &http.Transport{
        MaxIdleConns:        10,
        IdleConnTimeout:     90 * time.Second,
        MaxIdleConnsPerHost: 5,
    },
}
```

Replace all `client := &http.Client{Timeout: ...}` with `client := defaultAgentClient`. For the model resolution call that needs a shorter timeout, use a per-request context with `context.WithTimeout` instead of a shorter client timeout.

**Validation:**
1. `devenv shell -- go build ./...` compiles.
2. `devenv shell -- go test ./internal/ops/...` passes.
3. If integration tests are available (`go test -tags=integration`), run those too to verify API calls still work.

---

### Step 2.5 — Add Drop Counter to SSE Broker

**Review item:** H10
**File:** `internal/overlay/events.go:24-29`

**Current code:**
```go
select {
case ch <- payload:
default: // dropped
}
```

**Change:** Add a counter and optionally a "stale" notification:

```go
type EventBroker struct {
    mu      sync.Mutex
    subs    map[chan string]struct{}
    dropped int64 // atomic counter
}
```

In the Publish method:
```go
select {
case ch <- payload:
default:
    atomic.AddInt64(&b.dropped, 1)
}
```

Optionally, in the Handler's SSE loop, periodically check the drop counter and send a refresh hint:
```go
case msg := <-ch:
    fmt.Fprintf(w, "data: %s\n\n", msg)
    f.Flush()
```

At minimum, log dropped events so the developer can see them in the console.

**Validation:**
1. `devenv shell -- go test ./internal/overlay/...` passes.
2. Add a test: create a broker, subscribe, publish 20 messages without reading the channel (buffer=8). Verify the first 8 are received and `b.dropped` equals 12.
3. Existing `TestBroker_PublishAndReceive` still passes.

---

### Step 2.6 — Add Request Body Size Limit to ops/handler.go

**Review item:** H11
**File:** `internal/ops/handler.go:60-73`

**Current code:**
```go
if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
```

**Change:** Wrap `r.Body` with a size limiter before decoding:
```go
const maxRequestBodySize = 1 << 20 // 1 MB
r.Body = http.MaxBytesReader(w, r.Body, maxRequestBodySize)
if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
```

Apply to both `handleApply` (line ~66) and `handleUndo` (line ~150, if it reads a body).

**Validation:**
1. `devenv shell -- go test ./internal/ops/...` passes.
2. Add a test to `handler_test.go`: send a request with a body larger than 1MB → verify a 413 or 400 response.
3. Send a normal-sized request → verify it succeeds as before.

---

### Step 2.7 — Add Circular Embed Detection

**Review item:** H12
**File:** `internal/obsidian/markdown/wikilinks.go` — `renderWikilink` function (lines ~457-590)

**Current code:** When an embed (`![[Note]]`) is encountered, it calls `r.ReadFile(file.RelPath)` to get the content and then renders it. If Note A embeds Note B which embeds Note A, this recurses infinitely.

**Change:** Add a visited set to `IndexResolver`:
```go
type IndexResolver struct {
    // ... existing fields ...
    embedDepth   int
    embedVisited map[string]bool
}
```

At the top of the embed rendering path (around line ~520 where the `!` hack is detected):
```go
const maxEmbedDepth = 10
if r.embedDepth >= maxEmbedDepth {
    w.WriteString(`<p class="embed-error">Embed depth limit reached</p>`)
    return ast.WalkContinue, nil
}
if r.embedVisited == nil {
    r.embedVisited = make(map[string]bool)
}
if r.embedVisited[file.RelPath] {
    w.WriteString(`<p class="embed-error">Circular embed detected</p>`)
    return ast.WalkContinue, nil
}
r.embedVisited[file.RelPath] = true
r.embedDepth++
defer func() {
    r.embedDepth--
    delete(r.embedVisited, file.RelPath)
}()
```

**Validation:**
1. `devenv shell -- go test ./internal/obsidian/markdown/...` passes.
2. Add a test: create two files A.md and B.md where A embeds B and B embeds A. Render A. Verify it terminates and contains the "Circular embed detected" message (not a stack overflow).
3. Add a test: create a deeply nested embed chain (A→B→C→D→...→K, 11 levels). Verify it stops at depth 10 with the depth limit message.
4. Normal embeds (A→B, no cycle) still render correctly.

---

### Step 2.8 — Fix Content-Length After Overlay Injection

**Review item:** H4
**File:** `internal/overlay/inject.go:38-48`

**Current code:** Copies headers (skipping old Content-Length), writes body, but never sets new Content-Length.

**Change:** After computing the final body, set the new Content-Length before writing:
```go
// After line where body is finalized:
w.Header().Set("Content-Length", strconv.Itoa(len(body)))
w.WriteHeader(rec.statusCode)
w.Write(body)
```

Add `"strconv"` to imports.

**Validation:**
1. `devenv shell -- go test ./internal/overlay/...` passes.
2. In `inject_test.go`, add an assertion that checks the `Content-Length` header on the response matches the actual body length.
3. Verify the existing test `TestInjectMiddleware` still passes — it should already check the body content.

---

### Step 2.9 — validateFrontmatterField: Extract Type Handlers

**Review item:** H2
**File:** `internal/builder/builder_custom.go:941-1115`

**Current code:** 174-line function with a massive switch on `fieldConfig.Type` (12 cases).

**Change:** Define a handler map:
```go
type fieldHandler func(value any, fieldConfig FieldConfig, currentPage *CustomPage, site *CustomSite) (FieldContent, error)

var fieldHandlers = map[FieldType]fieldHandler{
    TypeString:     handleStringField,
    TypeBoolean:    handleBooleanField,
    TypeDate:       handleDateField,
    TypeDateTime:   handleDateTimeField,
    TypeInteger:    handleIntegerField,
    TypeFloat:      handleFloatField,
    TypeImage:      handleImageField,
    TypeTag:        handleTagField,
    TypeTags:       handleTagsField,
    TypeReference:  handleReferenceField,
    TypeReferences: handleReferencesField,
    TypeEnum:       handleEnumField,
    TypeCustom:     handleCustomField,
}
```

Then `validateFrontmatterField` becomes:
```go
func (s *CustomSite) validateFrontmatterField(key string, value any, currentPage *CustomPage) (FieldContent, error) {
    fieldConfig, ok := currentPage.Config.Fields[key]
    if !ok {
        return FieldContent{}, nil
    }
    handler, ok := fieldHandlers[fieldConfig.Type]
    if !ok {
        return FieldContent{}, fmt.Errorf("unknown field type: %s", fieldConfig.Type)
    }
    return handler(value, fieldConfig, currentPage, s)
}
```

Each handler is 10-20 lines, extracted from the current switch cases. Keep them in the same file or a new `field_handlers.go`.

**Validation:**
1. `devenv shell -- go build ./...` compiles.
2. `devenv shell -- go test ./internal/builder/...` passes.
3. Write unit tests for each handler function:
   - `handleStringField`: valid string → returns FieldContent with String set. Non-string → returns ErrorParsing.
   - `handleIntegerField`: int → ok. String "42" → ok. String "abc" → error.
   - `handleDateField`: time.Time → ok. String "2026-01-15" → ok. Invalid string → error.
   - `handleEnumField`: allowed value → ok. Disallowed value → error.
   - `handleReferenceField`: valid page ref → ok. Wrong collection → ErrorReferenceWrongCollection.
4. Build demo vault in custom mode (if applicable) to verify end-to-end.

---

### Step 2.10 — Fix Sitemap XML Escaping

**Review item:** M8 (upgrading priority since it produces invalid XML)
**File:** `internal/obsidian/sitemap.go:26-46`

**Current code:** Uses `xml.MarshalIndent` per entry but wraps in manual `WriteString` for the root element.

**Analysis:** Actually looking at the current code more carefully — it uses `xml.MarshalIndent(entry, ...)` which **does** handle XML escaping for the `<loc>` content. However, the `SitemapEntry` struct at line 60-64 uses `xml:"loc"` tags, so MarshalIndent will properly escape `&` and `<` in the URL.

**Verify:** Read the actual `GenerateSitemap` output for a URL containing `&`. If `xml.MarshalIndent` is handling the entries, this may already be correct. The issue would only be if URLs are written via `WriteString` rather than through the XML encoder.

If the entries ARE properly escaped: mark this as already-handled and move on.
If any part uses raw `WriteString` with unescaped content: wrap in proper XML encoding.

**Validation:**
1. Add a test to sitemap tests: add an entry with URL containing `&param=value`. Verify the output contains `&amp;param=value`.
2. Add a test with URL containing `<tag>`. Verify proper escaping.

---

### Step 2.11 — Fix buildDefault() God Function

**Review item:** H1
**File:** `internal/builder/builder_default.go:28-455`

This is a large refactor. Break `buildDefault` into focused functions on the `DefaultSite` receiver. The sections from the structural analysis map to:

| Lines | Extracted Function | Responsibility |
|-------|--------------------|----------------|
| 28-91 | keep in `buildDefault` | Setup: theme, layout, vault, site init, minifier |
| 93-119 | `(s *DefaultSite) categorizeFiles(files)` | Sort files into notes, bases, canvas, static |
| 142-168 | `(s *DefaultSite) copyStaticAssets(files, log)` | Copy static files + image optimization |
| 172-276 | `(s *DefaultSite) renderAllPages(log)` | Render folders, canvas, bases, notes, tags |
| 278-283 | `(s *DefaultSite) buildSearchIndex(log)` | Search index JSON |
| 285-386 | `(s *DefaultSite) writeAssets(log)` | All CSS/JS template writes (uses `writeTemplate` helper from Step 1.4) |
| 388-448 | `(s *DefaultSite) writeMetaFiles(log)` | Graph, 404, sitemap, RSS, robots, CNAME, favicon, redirects |

After extraction, `buildDefault` becomes a ~40-line orchestrator:
```go
func buildDefault(log *slog.Logger) {
    // setup (theme, layout, vault, site, minifier)
    ...
    site.categorizeFiles(obs.Vault.Files)
    site.copyStaticAssets(staticFiles, log)
    site.renderAllPages(log)
    site.buildSearchIndex(log)
    site.writeAssets(log)
    site.writeMetaFiles(log)
}
```

**Validation:**
1. `devenv shell -- go build ./...` compiles.
2. `devenv shell -- go test ./internal/builder/...` passes.
3. Build demo vault: `devenv shell -- go run ./cmd/forge generate`. Diff the `demo/public/` output against a snapshot taken before the refactor — should be identical.
4. Each extracted function can now be unit-tested independently (new tests can be added in Phase 6).

---

### Step 2.12 — Fix Orphaned File Handling in Navbar

**Review item:** M13 (upgrading since files silently disappear)
**File:** `internal/obsidian/navbar.go:81-97, 124`

**Current code:** If `docs.md` and `docs/` both exist, folder path is overwritten. Orphaned files in unmapped folders are logged at Debug level and lost.

**Change:**
1. For the collision: when a file name matches a folder name, mark the folder as having both `IsNote=true` and keep the folder's children. The current code does this but overwrites `folder.Path` — verify it's the file's web path (correct, since the folder should link to the file page). This is actually correct behavior for Obsidian conventions. Document this with a comment.

2. For orphaned files: upgrade the log from Debug to Warn so the user notices:
   ```go
   o.log.Warn("File found in unmapped folder — skipped from navbar", "path", file.RelPath)
   ```

**Validation:**
1. Create a test vault with `docs.md` and `docs/` containing `docs/child.md`. Build navbar. Verify:
   - `docs` node exists in navbar with `IsNote=true` and links to `docs.md`'s web path.
   - `docs/child.md` appears as a child of the `docs` folder.
2. Create a file in a folder not present in `Vault.Folders`. Verify a Warn log appears.

---

## Phase 3: Architectural Refactoring — Builder

The biggest structural improvement: eliminate global mutable state. This must be done carefully to avoid breaking the CLI integration.

---

### Step 3.1 — Define BuildContext Struct

**Review item:** C1
**File:** `internal/builder/builder.go`

**Change:** Create a new struct to hold all build configuration:

```go
type BuildContext struct {
    OutputDir         string
    InputDir          string
    FlatUrls          bool
    ThemeName         string
    FontName          string
    BaseURL           string
    SiteName          string
    Mode              string
    LayoutName        string
    DisableTOC        bool
    DisableLocalGraph bool
    DisableBacklinks  bool
    Lang              string
    AccentColorName   string
    Log               *slog.Logger
}
```

Do NOT delete the global variables yet. This step only adds the struct.

**Validation:**
1. `devenv shell -- go build ./...` compiles (no behavior change yet).

---

### Step 3.2 — Update Build() and IncrementalBuild() Signatures

**File:** `internal/builder/builder.go`

**Change:** Update signatures to accept `BuildContext`:
```go
func Build(ctx BuildContext) { ... }
func IncrementalBuild(ctx BuildContext, rebuild []string, remove []string) { ... }
```

Inside these functions, copy `ctx` fields to the existing globals for now (shim layer):
```go
func Build(ctx BuildContext) {
    OutputDir = ctx.OutputDir
    InputDir = ctx.InputDir
    // ... all fields ...
    // dispatch to buildDefault or buildCustom
}
```

This is a temporary bridge. The globals will be removed in Step 3.5.

**Validation:**
1. `devenv shell -- go build ./...` — will fail because callers still use old signature.

---

### Step 3.3 — Update CLI Callers

**Files:**
- `internal/cli/generate.go:86-87` — currently `builder.Build(log)`
- `internal/cli/dev.go:109-114` — currently `builder.Build(log)` and `builder.IncrementalBuild(log, ...)`
- `internal/cli/clean.go` — uses `builder.CleanOutputDir(log)` and `builder.OutputDir`
- `internal/cli/init.go` — uses `builder.Init(log)` and `builder.InputDir`
- `internal/cli/stats.go` — uses `builder.Stats(log)` and `builder.InputDir`

**Change:** In each CLI command, construct a `BuildContext` from the resolved flags and pass it:

```go
// In generate.go runGenerate():
ctx := builder.BuildContext{
    OutputDir:         outputDir,
    InputDir:          inputDir,
    FlatUrls:          flatUrls,
    ThemeName:         themeName,
    // ... all fields ...
    Log:               getLogger(),
}
builder.Build(ctx)
```

Remove the block of `builder.OutputDir = outputDir` assignments (lines ~71-84 in generate.go, ~94-107 in dev.go).

For `clean.go`, `init.go`, `stats.go`: update their functions to accept the relevant paths directly instead of reading globals:
```go
builder.CleanOutputDir(outputDir, log)
builder.Init(inputDir, log)
builder.Stats(inputDir, log)
```

**Validation:**
1. `devenv shell -- go build ./...` compiles.
2. `devenv shell -- go test ./...` passes.
3. Run each command against demo vault:
   - `forge generate` — produces output
   - `forge clean` — removes output
   - `forge init` — creates input dir
   - `forge stats` — prints stats
   - `forge dev` — builds and serves

---

### Step 3.4 — Thread BuildContext Into buildDefault and buildCustom

**Files:**
- `internal/builder/builder_default.go` — `buildDefault(log)`
- `internal/builder/builder_custom.go` — `buildCustom(log)`
- All functions that read globals (`OutputDir`, `InputDir`, `FlatUrls`, etc.)

**Change:** Update signatures:
```go
func buildDefault(ctx BuildContext) { ... }
func buildCustom(ctx BuildContext) { ... }
```

Inside these functions, replace all reads of globals with `ctx.FieldName`. This is a mechanical search-and-replace:
- `OutputDir` → `ctx.OutputDir`
- `InputDir` → `ctx.InputDir`
- `FlatUrls` → `ctx.FlatUrls`
- etc.

Also update `shouldRebuild` to take the filter as a parameter:
```go
func shouldRebuild(relPath string, filter map[string]struct{}) bool {
    if filter == nil { return true }
    _, ok := filter[relPath]
    return ok
}
```

And move `RebuildFilter` from a global into `IncrementalBuild`'s local scope, passed down through function arguments.

**Validation:**
1. `devenv shell -- go build ./...` compiles.
2. `devenv shell -- go test ./internal/builder/...` passes.
3. Rebuild demo vault and diff output — should be identical to before.

---

### Step 3.5 — Remove Global Variables

**File:** `internal/builder/builder.go:56-71`

**Change:** Delete the entire `var (...)` block and the `var RebuildFilter` line. Also remove globals from `internal/cli/commands.go:71-87` if they were only used as intermediaries to set builder globals.

**Validation:**
1. `devenv shell -- go build ./...` compiles with no references to deleted globals.
2. `devenv shell -- go test ./...` all pass.
3. `devenv shell -- go vet ./...` no warnings.
4. `devenv shell -- go test -race ./...` passes — confirms no race conditions remain.

---

### Step 3.6 — Update CleanOutputDir, Init, Stats Signatures

**Files:**
- `internal/builder/utils.go` — `CleanOutputDir`, `Init`, `shouldRebuild`
- `internal/builder/stats.go` — `Stats`

**Change:** These functions currently read globals. Update them to accept explicit parameters:

```go
func CleanOutputDir(outputDir string, log *slog.Logger) { ... }
func Init(inputDir string, log *slog.Logger) { ... }
func Stats(inputDir string, log *slog.Logger) { ... }
```

The validation from Step 1.3 (dangerous path guard) should use the `outputDir` parameter.

**Validation:**
1. `devenv shell -- go build ./...` compiles.
2. All existing builder tests pass.
3. Run `forge clean`, `forge init`, `forge stats` to verify behavior unchanged.

---

## Phase 4: Architectural Refactoring — Error Handling

Establish a consistent error strategy across the codebase.

---

### Step 4.1 — Create ErrorCollector Utility

**Review item:** H5
**File:** New file `internal/builder/errors.go`

```go
package builder

import (
    "fmt"
    "strings"
    "sync"
)

type ErrorCollector struct {
    mu     sync.Mutex
    errors []error
}

func (ec *ErrorCollector) Add(err error) {
    if err == nil { return }
    ec.mu.Lock()
    defer ec.mu.Unlock()
    ec.errors = append(ec.errors, err)
}

func (ec *ErrorCollector) Addf(format string, args ...any) {
    ec.Add(fmt.Errorf(format, args...))
}

func (ec *ErrorCollector) HasErrors() bool {
    ec.mu.Lock()
    defer ec.mu.Unlock()
    return len(ec.errors) > 0
}

func (ec *ErrorCollector) Error() string {
    ec.mu.Lock()
    defer ec.mu.Unlock()
    msgs := make([]string, len(ec.errors))
    for i, e := range ec.errors {
        msgs[i] = e.Error()
    }
    return strings.Join(msgs, "; ")
}

func (ec *ErrorCollector) Errors() []error {
    ec.mu.Lock()
    defer ec.mu.Unlock()
    cp := make([]error, len(ec.errors))
    copy(cp, ec.errors)
    return cp
}
```

**Validation:**
1. `devenv shell -- go build ./...` compiles.
2. Write unit tests: Add 3 errors, verify HasErrors=true, Error() contains all 3 messages, Errors() returns 3 items. Test concurrent Add from multiple goroutines with `-race`.

---

### Step 4.2 — Use ErrorCollector in buildDefault

**File:** `internal/builder/builder_default.go`

**Change:** Create an `ErrorCollector` at the top of `buildDefault` and pass it to the extracted functions from Step 2.11. Each function adds errors instead of just logging:

```go
func buildDefault(ctx BuildContext) {
    errs := &ErrorCollector{}
    // ...
    site.writeAssets(ctx, errs)
    site.writeMetaFiles(ctx, errs)
    // ...
    if errs.HasErrors() {
        ctx.Log.Error("Build completed with errors", "count", len(errs.Errors()))
        for _, e := range errs.Errors() {
            ctx.Log.Error("  " + e.Error())
        }
    }
}
```

**Validation:**
1. `devenv shell -- go build ./...` compiles.
2. Temporarily break a template to produce an error. Run `forge generate`. Verify the error summary appears at the end of output.
3. Fix the template. Run again. Verify no error summary.

---

### Step 4.3 — Fix Silent Errors in Supporting Packages

**Review item:** H5 (specific instances)
**Files and changes:**

| File | Line | Current | Fix |
|------|------|---------|-----|
| `builder/stats.go:24` | `_, _ :=` | Silently ignores ReadFile error | Log warning and skip file |
| `obsidian/obsidian.go:196-197` | `fmt.Printf("Warning...")` | Uses wrong logging function | Change to `o.log.Warn("YAML parse error", "file", f.RelPath, "error", err)` |
| `linter/linter.go:90` | `_, _ :=` ReadFile | Silently ignores unreadable files | Log warning with file path and continue |
| `imgopt/imgopt.go:299` | `continue` on error | Drops failed images silently | Return error map alongside results: `map[string]*Result, map[string]error` |
| `ops/handler.go:179` | `_ = json.Encode` | Ignores write error | Log the error: `if err := json.NewEncoder(w).Encode(v); err != nil { log.Warn(...) }` |
| `jsonld/jsonld.go:64-67, 97-100` | Returns `""` on Marshal error | Swallows encoding failure | Return `(string, error)` from both functions. Callers check error. |
| `cli/commands.go:119-123` | Returns empty config on error | User doesn't know config was ignored | Log at Warn level with the specific error |

Each of these is a small change. Do them as a batch.

**Validation:**
1. `devenv shell -- go build ./...` compiles (note: changing `jsonld` function signatures requires updating callers in builder).
2. `devenv shell -- go test ./...` passes.
3. For jsonld: update existing tests to check the new error return value.
4. For imgopt: update `TestProcessImages` to verify the error map is populated when an image fails.

---

### Step 4.4 — Fix linter.BrokenLinks to Return Error Count

**File:** `internal/linter/linter.go:74-150`

**Current:** Function logs broken links but returns nothing. Caller has no way to know if links are broken.

**Change signature:**
```go
func BrokenLinks(inputDir string, notes map[string]bool, log *slog.Logger) int {
    // ... existing logic ...
    return issuesFound
}
```

Or return `[]BrokenLink` for structured access.

Also fix the WalkDir error swallowing on line ~17-19: return the error from `CollectNotes` so callers know if the walk failed.

**Validation:**
1. `devenv shell -- go build ./...` compiles.
2. `devenv shell -- go test ./internal/linter/...` passes.
3. Update `linter_test.go` to check the return value matches the expected number of broken links.

---

## Phase 5: Medium-Severity Fixes

Smaller correctness and quality improvements.

---

### Step 5.1 — Config: Replace Hardcoded Switches with Reflection

**Review item:** M1
**File:** `internal/config/config.go:75-122`

**Change:** Replace the manual switch in `ValueOr` and `BoolOr` with reflection using the `yaml` struct tags:
```go
func (c *Config) ValueOr(field, fallback string) string {
    if c == nil { return fallback }
    v := reflect.ValueOf(*c)
    t := v.Type()
    for i := 0; i < t.NumField(); i++ {
        if tag := t.Field(i).Tag.Get("yaml"); tag == field {
            if s, ok := v.Field(i).Interface().(string); ok && s != "" {
                return s
            }
            return fallback
        }
    }
    return fallback
}
```

Do the same for `BoolOr`.

**Validation:**
1. `devenv shell -- go test ./internal/config/...` passes — existing tests cover all the current fields.
2. Add a new field to Config struct with a yaml tag. Verify `ValueOr` returns it without any switch update needed.

---

### Step 5.2 — Fix Case Sensitivity Inconsistencies

**Review item:** M5
**Files:**
- `internal/obsidian/bases/bases.go:268-274` — `InFolder` uses case-sensitive comparison
- `internal/watch/depgraph.go:128` — lowercases targets
- `internal/obsidian/markdown/wikilinks.go` — case-insensitive with fallback

**Change:** Establish a rule: **all name comparisons are case-insensitive**. Apply `strings.ToLower` or `strings.EqualFold` consistently:

1. `bases.go InFolder`: use `strings.EqualFold` for equality, `strings.HasPrefix(strings.ToLower(...))` for prefix.
2. Document the case-insensitivity convention in a comment in `obsidian/obsidian.go` where the file index is built.

**Validation:**
1. `devenv shell -- go test ./...` passes.
2. Add tests for `InFolder("Assets")` matching file in `assets/` folder.
3. Add test for wikilink `[[MyNote]]` matching file `mynote.md`.

---

### Step 5.3 — Improve Slugify

**Review item:** M6
**File:** `internal/obsidian/paths.go:14-18`

**Current:**
```go
func Slugify(s string) string {
    s = strings.ToLower(s)
    s = strings.ReplaceAll(s, " ", "-")
    return s
}
```

**Change:** Strip characters that are problematic in URLs:
```go
var slugUnsafe = regexp.MustCompile(`[^a-z0-9\-/.]`)

func Slugify(s string) string {
    s = strings.ToLower(s)
    s = strings.ReplaceAll(s, " ", "-")
    s = slugUnsafe.ReplaceAllString(s, "")
    s = strings.ReplaceAll(s, "--", "-") // collapse double dashes
    return s
}
```

Keep `/` and `.` since those are valid in URL paths. Remove `()[]{}?#&'"+` etc.

**WARNING:** This changes output URLs. Any existing links or bookmarks to pages with special characters in their filenames will break. Consider making this opt-in via config or adding redirects.

**Validation:**
1. `devenv shell -- go test ./internal/obsidian/...` passes.
2. Add tests:
   - `Slugify("My (Draft) [v2]")` → `"my-draft-v2"` (parens/brackets stripped)
   - `Slugify("Hello World")` → `"hello-world"` (unchanged behavior)
   - `Slugify("café")` → `"caf"` (accented char stripped — or keep Unicode? Decide on convention)
3. Build demo vault and verify all page URLs are still valid.

---

### Step 5.4 — Fix FlatURLs Comment Mismatch

**Review item:** M14
**File:** `internal/obsidian/paths.go:98`

**Change:** Fix the misleading comment:
```go
// When FlatURLs is enabled, use directory-based clean URLs (e.g., /page/index.html → /page/)
if o.FlatURLs {
```

This is documentation-only, no behavior change.

**Validation:** None needed beyond code review.

---

### Step 5.5 — Make RSS Entry Limit Configurable

**Review item:** M7
**File:** `internal/obsidian/rss.go:23`

**Change:** Accept the limit as a parameter (with default 50):
```go
func (o *Obsidian) GenerateRSS(maxEntries int) error {
    if maxEntries <= 0 { maxEntries = 50 }
    // ...
    if len(entries) > maxEntries {
        entries = entries[:maxEntries]
    }
```

Thread through from config if desired, or just use the default for now and remove the magic number.

**Validation:**
1. `devenv shell -- go build ./...` compiles (update callers).
2. Existing RSS tests pass.

---

### Step 5.6 — Move Theme Definitions to Embedded YAML

**Review item:** M4
**File:** `internal/builder/themes.go:258-349`

**Change:**
1. Create `assets/themes.yaml` containing all theme color definitions.
2. Embed it via `//go:embed themes.yaml`.
3. Replace the hardcoded `themes` map with YAML parsing at init time:
```go
//go:embed themes.yaml
var themesYAML []byte

var themes map[string]*Theme

func init() {
    if err := yaml.Unmarshal(themesYAML, &themes); err != nil {
        panic("failed to parse embedded themes: " + err.Error())
    }
}
```

The YAML structure would be:
```yaml
default:
  light:
    bg: "#ffffff"
    text: "#1e1e1e"
    # ...
  dark:
    bg: "#1e1e1e"
    text: "#d4d4d4"
    # ...
```

**Validation:**
1. `devenv shell -- go build ./...` compiles.
2. `devenv shell -- go test ./internal/builder/...` passes.
3. Build demo vault with each theme name. Verify the CSS output contains the correct colors by spot-checking a few themes.
4. Add a test that loads the YAML and verifies all 8+ themes are present with all 14 color fields populated.

---

### Step 5.7 — Add Cycle Detection to Dependency Graph

**Review item:** M9
**File:** `internal/watch/changeset.go:23-28`

**Change:** Track visited nodes during dependent expansion:
```go
visited := make(map[string]bool)
var expandDeps func(name string)
expandDeps = func(name string) {
    if visited[name] { return }
    visited[name] = true
    for _, dep := range graph.Dependents(name) {
        rebuildSet[dep] = struct{}{}
        expandDeps(dep)
    }
}

for _, relPath := range changed {
    name := nameFromRelPath(relPath)
    rebuildSet[relPath] = struct{}{}
    expandDeps(name)
}
```

**Validation:**
1. `devenv shell -- go test ./internal/watch/...` passes.
2. Add test: create a graph where A→B and B→A. Call `ComputeChangeSet(["a.md"], nil, graph)`. Verify it terminates and returns both files (no infinite loop).

---

### Step 5.8 — Make Watcher Debounce Configurable

**Review item:** M10
**File:** `internal/watch/watcher.go`

**Change:** Add a `Debounce` field to the `Watcher` struct (or its config), defaulting to the current value (e.g., 300ms). Use it in the timer reset instead of the hardcoded constant.

**Validation:**
1. `devenv shell -- go test ./internal/watch/...` passes.
2. Existing debounce test still verifies that rapid changes are batched.

---

### Step 5.9 — Add X-Forwarded Headers to Reverse Proxy

**Review item:** M11
**File:** `internal/proxy/reverse.go:20-26`

**Change:** In the Director function:
```go
Director: func(req *http.Request) {
    req.URL.Scheme = target.Scheme
    req.URL.Host = target.Host
    req.Host = target.Host
    // Preserve client information
    if clientIP, _, err := net.SplitHostPort(req.RemoteAddr); err == nil {
        if prior := req.Header.Get("X-Forwarded-For"); prior != "" {
            clientIP = prior + ", " + clientIP
        }
        req.Header.Set("X-Forwarded-For", clientIP)
    }
    req.Header.Set("X-Forwarded-Proto", "http")
},
```

**Validation:**
1. `devenv shell -- go test ./internal/proxy/...` passes.
2. Add a test: make a request through the proxy, verify the backend receives `X-Forwarded-For` and `X-Forwarded-Proto` headers.

---

### Step 5.10 — Fix ops/agent.go Silent Type Assertions

**Review item:** M12
**File:** `internal/ops/agent.go:166-167`

**Change:** Check the ok flag and log/error on unexpected types:
```go
stopReason, ok := resp["stop_reason"].(string)
if !ok && resp["stop_reason"] != nil {
    cfg.log().Warn("unexpected stop_reason type", "value", resp["stop_reason"])
}
content, ok := resp["content"].([]any)
if !ok && resp["content"] != nil {
    return nil, fmt.Errorf("unexpected content type in API response: %T", resp["content"])
}
```

Apply this pattern at all type assertion sites (lines ~166, 167, 261, 664-669).

**Validation:**
1. `devenv shell -- go build ./...` compiles.
2. `devenv shell -- go test ./internal/ops/...` passes.
3. Add a test: call the agent response parser with a response where `stop_reason` is an int instead of string. Verify it logs a warning rather than silently returning "".

---

### Step 5.11 — Standardize Logging on slog

**Review item:** L2
**Files:** All files that use `fmt.Printf` or `log.Error` (charmbracelet) instead of `slog`:

| File | Line | Current | Fix |
|------|------|---------|-----|
| `obsidian/obsidian.go:196-197` | `fmt.Printf("Warning: ...")` | Use `o.log.Warn(...)` |
| `builder/themes.go:469-470, 475-476` | `log.Error(...)` | Already uses slog, but verify consistency |

Grep for `fmt.Print` in all Go files to find any remaining instances:
```
devenv shell -- grep -rn 'fmt\.Print' internal/
```

Replace each with the appropriate `slog` call using the logger that's in scope.

**Validation:**
1. `devenv shell -- go build ./...` compiles.
2. Grep confirms no `fmt.Print` calls remain in production code (test files are ok).

---

### Step 5.12 — Fix Dependency Graph Regex-Based Link Parsing

**Review item:** M3
**File:** `internal/watch/depgraph.go:71-85`

**Current:** `UpdateFiles` reads `file.Links` and `file.Embeds` which are raw link strings extracted by `processMarkdown`. These are then parsed by `parseTarget` using regex.

**Issue:** The links in `file.Links` are already extracted from markdown context (in `obsidian.go` lines 212-258), so they're not raw text from code blocks. The regex in depgraph is just normalizing the already-extracted links. This is actually less broken than the review suggested.

**Real fix needed:** Ensure `processMarkdown` doesn't extract links from code blocks. Check if the wikilink/markdown link regexes in `obsidian.go:26-30` match inside fenced code blocks.

**Change:** In `obsidian.go`, strip fenced code blocks before extracting links:
```go
// Before link extraction:
cleanBody := stripCodeBlocks(bodyString)
wikilinkMatches := wikilinkRegex.FindAllStringSubmatch(cleanBody, -1)
```

Where `stripCodeBlocks` removes ``` fenced blocks and `inline code`.

**Validation:**
1. Add test: markdown containing ` ```\n[[NotALink]]\n``` `. Verify `file.Links` does not contain `NotALink`.
2. Add test: markdown containing `` `[[NotALink]]` ``. Verify it's excluded.
3. Normal links outside code blocks still extracted.

---

### Step 5.13 — Fix Global CLI Flag Variables

**Review item:** M2
**File:** `internal/cli/commands.go:71-87`

After Phase 3 (BuildContext refactor), the CLI flag variables only need to live within each command's `Run` function, not as package globals. Convert them to local variables in `runGenerate`, `runDev`, etc.

**Change:** Move the variable declarations into each `Run` function. Use Cobra's `cmd.Flags().GetString(FlagTheme)` pattern instead of binding to package-level vars.

Alternatively, create a `flagSet` struct that's populated from cobra flags:
```go
type flagSet struct {
    themeName         string
    fontName          string
    // ...
}

func resolveFlagSet(cmd *cobra.Command, cfg *config.Config) flagSet {
    fs := flagSet{}
    fs.themeName = resolveStringFlag(cmd, FlagTheme, cfg, DefaultThemeName)
    // ...
    return fs
}
```

**Validation:**
1. `devenv shell -- go build ./...` compiles.
2. All CLI commands work as before.

---

### Step 5.14 — Fix Missing Error Check on fmt.Sscanf

**Review item:** L10
**File:** `cmd/kiln-palette/main.go:192, 194`

**Change:**
```go
n, err := fmt.Sscanf(s, "%02x%02x%02x", &c.R, &c.G, &c.B)
if err != nil || n != 3 {
    // return a visible error color or log warning
    return color.RGBA{R: 255, A: 255} // red indicates parse error
}
```

**Validation:**
1. `devenv shell -- go build ./cmd/kiln-palette` compiles.
2. Test with valid hex `#ff0000` → red. Invalid hex `#xyz` → returns error color.

---

### Step 5.15 — Fix Server Shutdown Context

**Review item:** L11
**File:** `internal/server/server.go:88-92`

**Current:**
```go
go func() {
    <-ctx.Done()
    srv.Shutdown(context.Background())
}()
```

**Change:** Use a timeout context for graceful shutdown:
```go
go func() {
    <-ctx.Done()
    shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
    defer cancel()
    srv.Shutdown(shutdownCtx)
}()
```

**Validation:**
1. `devenv shell -- go build ./...` compiles.
2. `devenv shell -- go test ./internal/server/...` passes.
3. Manual test: start `forge dev`, press Ctrl+C, verify clean shutdown within 5 seconds.

---

## Phase 6: Test Coverage Expansion

Target: raise coverage from 21.4% to 50%+ by covering the highest-impact gaps.

---

### Step 6.1 — Builder Integration Test (Golden File)

**File:** New file `internal/builder/builder_integration_test.go`

Create a test that:
1. Copies the `demo/vault` to a temp directory.
2. Constructs a `BuildContext` with known configuration.
3. Calls `Build(ctx)`.
4. Verifies key output files exist: `index.html`, `style.css`, `app.js`, `search-index.json`, `graph.json`, `sitemap.xml`, `feed.xml`.
5. Verifies `index.html` contains expected content (page title, navigation).
6. Optionally: golden-file comparison against `demo/public/` for a few key pages.

**Validation:**
1. `devenv shell -- go test ./internal/builder/ -run TestBuildIntegration` passes.
2. Coverage for builder package increases from 1.3% to 15%+.

---

### Step 6.2 — Custom Mode Field Validation Tests

**File:** New file `internal/builder/field_handlers_test.go` (or extend `builder_test.go`)

Write table-driven tests for each field handler (from Step 2.9):
- TypeString: valid, non-string
- TypeBoolean: true, false, non-bool
- TypeInteger: int, string-int, invalid
- TypeFloat: float, string-float, invalid
- TypeDate: time.Time, string date, invalid format
- TypeEnum: allowed value, disallowed value
- TypeReference: valid ref, wrong collection, missing page
- TypeTags: single, multiple, nested arrays

**Validation:**
1. All tests pass.
2. Coverage for `builder_custom.go` validation code reaches 80%+.

---

### Step 6.3 — CLI Smoke Tests

**File:** New file `internal/cli/cli_test.go`

Test that each command parses flags correctly:
```go
func TestGenerateCommand_Flags(t *testing.T) {
    cmd := Init()
    cmd.SetArgs([]string{"generate", "--theme", "dracula", "--input", "/tmp/test"})
    // Don't execute (it would try to build), just verify flag parsing
    genCmd, _, err := cmd.Find([]string{"generate"})
    require.NoError(t, err)
    // Verify flags are registered
    require.NotNil(t, genCmd.Flags().Lookup("theme"))
}
```

**Validation:**
1. `devenv shell -- go test ./internal/cli/...` passes.
2. CLI coverage goes from 0% to 30%+.

---

### Step 6.4 — obsidian/bases Package Tests

**File:** New file `internal/obsidian/bases/bases_test.go`

Test the core evaluation engine:
- `FilterFiles` with various conditions (string equality, contains, startswith, numeric comparison)
- `GroupFiles` by tag, by folder, by custom field
- `InFolder` case sensitivity (from Step 5.2)
- `isTrue` with bool, int, string
- `cleanLink` with wikilinks, embeds, anchored links
- `toString` with all types
- `toFloat` with int, float, string-that-looks-like-number

**Validation:**
1. `devenv shell -- go test ./internal/obsidian/bases/...` passes.
2. Coverage goes from 0% to 60%+.

---

### Step 6.5 — Obsidian Package Tests (Vault Scanning)

**File:** Extend `internal/obsidian/obsidian_links_test.go` or create new test file.

Test:
- `Scan()` on a temp vault with known structure → verify Files, Folders, Tags populated correctly.
- `processMarkdown()` extracts correct Links, Embeds, Tags from a sample markdown file.
- `GenerateBacklinks()` creates correct backlink entries.
- Tag extraction with the regex (including edge cases: tags in code blocks, tags at start of line, tags mid-sentence).

**Validation:**
1. `devenv shell -- go test ./internal/obsidian/...` passes.
2. Coverage for obsidian package rises from 12.2% to 40%+.

---

### Step 6.6 — Server Package Tests

**File:** Extend `internal/server/server_test.go`

Test:
- Clean URL handling: request `/page` serves `page.html` if it exists.
- Custom 404 page: request for nonexistent path serves 404.html content.
- Base URL prefix: paths are correctly prefixed/stripped.
- Path traversal: `/../etc/passwd` returns 404/403 (FileServer handles this, but verify).

**Validation:**
1. `devenv shell -- go test ./internal/server/...` passes.
2. Coverage rises from 40.2% to 70%+.

---

### Step 6.7 — Markdown Transformer Tests

**File:** Extend `internal/obsidian/markdown/` test files.

Test the transformers specifically:
- `transformHighlights`: `==text==` → `<mark>text</mark>`. Edge: `==a = b==` (from L3 fix).
- `transformMermaid`: code block with `mermaid` language → `<div class="mermaid">`.
- `transformCallouts`: `> [!info] Title\n> Body` → proper callout HTML.
- `transformTags`: `#tag` → linked tag. `#123` → NOT a tag (number-only).
- `extractTOC`: headings → nav with correct IDs and nesting.

**Validation:**
1. `devenv shell -- go test ./internal/obsidian/markdown/...` passes.
2. Coverage rises from 47.5% to 70%+.

---

### Step 6.8 — Frontend Test Expansion

**File:** `static/src/__tests__/` — add new test files.

Add tests using Node.js test runner (matching existing `api.test.js` pattern):
- `events.test.js`: mock EventSource, verify subscribe/unsubscribe.
- `state.test.js`: verify createState returns correct initial shape.
- `page-context.test.js`: mock DOM meta tags, verify readPageContext.

**Validation:**
1. Run JS tests: `devenv shell -- node --test static/src/__tests__/*.test.js` — all pass.

---

## Phase 7: JavaScript & CSS Cleanup

---

### Step 7.1 — Extract Shared JS Functions

**Review item:** JS1
**Files:** `assets/default_app.js`, `assets/simple_app.js`

**Change:** Create `assets/shared_app.js` containing:
- `loadScript()` (identical in both)
- `initMermaid()` (identical)
- `changeGiscusTheme()` (identical)
- `initThemeToggle()` (identical)
- `addCopyButtons()` (identical)
- `initCanvasMode()` (identical)
- `initNavFolderAnimation()` (identical)
- Giscus postMessage listener (identical)
- `initMathJax(containerSelector)` — parameterized (default uses `#content`, simple uses `.markdown-body`)
- `initLightbox(animated)` — parameterized (default has animation, simple doesn't)
- `initBackToTop(scrollContainer)` — parameterized

Each layout file then imports the shared functions and calls them with layout-specific parameters, keeping only the layout-specific code (sidebar delegation vs panel system).

**Note:** Since these are embedded via Go templates (not ES modules), use IIFE pattern or `window.shared = {}` namespace.

Update `assets/assets.go` to include the new `shared_app.js` embed.
Update `internal/builder/builder_default.go` to write the shared JS alongside the layout JS.

**Validation:**
1. `devenv shell -- go build ./...` compiles.
2. Build demo vault with default layout. Open in browser. Verify: theme toggle, MathJax, Mermaid, copy buttons, lightbox, canvas, graph, navigation all work.
3. Build with simple layout. Same verification.
4. Verify the two layout JS files are significantly smaller (~150 lines each instead of ~500).

---

### Step 7.2 — Remove Legacy old_app.js and old_style.css

**Review item:** L5, CSS2
**Files:** `assets/old_app.js`, `assets/old_style.css`

**Change:**
1. Check if "old" layout is still referenced anywhere:
   ```
   grep -rn '"old"' internal/ assets/
   ```
2. If the "old" layout is still a valid option in the layout registry (`builder/layouts.go`), either:
   - a) Remove it from the registry and delete the files.
   - b) Keep it but fix the broken MathJax URL and remove commented-out code.
3. Remove from `assets/assets.go` embed directives if deleting.

**Validation:**
1. `devenv shell -- go build ./...` compiles.
2. If layout was removed: `forge generate --layout old` should error with "unknown layout".
3. If layout was kept: verify it renders correctly with the fixed MathJax URL.

---

### Step 7.3 — Add Focus Trap and ESC Handler to Modal

**Review item:** Overlay UI issues
**File:** `static/src/ui/modal.js`

**Change:** Add keyboard handling:
```javascript
function trapFocus(modal) {
    const focusable = modal.querySelectorAll('button, input, select, textarea, [tabindex]:not([tabindex="-1"])');
    if (focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    modal.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') { closeModal(modal); return; }
        if (e.key !== 'Tab') return;
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    });
    first.focus();
}
```

Add `aria-modal="true"` and `role="dialog"` to the modal element in `createModalRoot()`.

Call `trapFocus(modal)` after creating the modal.

**Validation:**
1. Manual test: open a modal, press Tab repeatedly → focus should cycle within the modal.
2. Press Escape → modal closes.
3. Screen reader test (or check with browser accessibility inspector): modal is announced as a dialog.

---

### Step 7.4 — Add aria-live to Toast

**File:** `static/src/ui/toast.js`

**Change:**
```javascript
el.setAttribute("role", "status");
el.setAttribute("aria-live", "polite");
el.setAttribute("aria-atomic", "true");
```

**Validation:**
1. Manual test: trigger a toast, verify it appears.
2. Browser accessibility inspector shows the element has `role="status"` and `aria-live="polite"`.

---

### Step 7.5 — Add Form Validation to new-page-mode

**File:** `static/src/modes/new-page-mode.js:53-70`

**Change:** Before the API call:
```javascript
createBtn.addEventListener("click", async () => {
    if (!form.reportValidity()) return; // native HTML5 validation
    createBtn.disabled = true;
    createBtn.textContent = "Creating...";
    // ... existing API call ...
    createBtn.disabled = false;
    createBtn.textContent = "Create";
});
```

Ensure required fields in the form have the `required` attribute (set in `form.js` when creating fields from template definitions).

**Validation:**
1. Manual test: try to create a page with empty required fields → browser shows validation message.
2. Create with valid fields → succeeds as before.
3. Button shows loading state during creation.

---

### Step 7.6 — Add Debouncing to Search Input

**Review item:** JS4
**File:** `assets/search.js:246-250`

**Change:**
```javascript
var searchTimer = null;
modalInput.addEventListener("input", function (e) {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(function () {
        var term = e.target.value.trim();
        var results = searchEntries(term);
        showResults(results, term);
    }, 150); // 150ms debounce
});
```

150ms is fast enough to feel instant but prevents thrashing on fast typing.

**Validation:**
1. Build demo vault, open search modal, type quickly. Verify:
   - Results appear after a brief pause (not on every keystroke).
   - Final results are correct.
   - No visual lag or jank.

---

### Step 7.7 — Sanitize innerHTML in canvas.js

**Review item:** JS3
**File:** `assets/canvas.js` — 12+ innerHTML usages

**Change:** For user-controlled data (nodeData.url, nodeData.file, nodeData.text), use text escaping:

```javascript
function escapeHTML(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}
```

Apply to:
- Line 164: `headerEl.innerHTML` — escape `cleanName`
- Line 186-188: fallback — escape `nodeData.file`
- Line 205: link header — escape `nodeData.url`
- Lines 130-132: `marked.parse()` output is already HTML (from markdown) — this is intentional, but the surrounding template literals should escape other interpolated values.

For `marked.parse()` output (line 130): this is expected to contain HTML. Add a comment explaining why innerHTML is used here.

**Validation:**
1. Build demo vault with canvas files. Verify canvas renders correctly.
2. Create a test canvas with a node whose text contains `<script>alert(1)</script>`. Verify it renders as text, not as a script.

---

### Step 7.8 — Consolidate Duplicate CSS

**Review item:** CSS1
**Files:** `assets/shared.css`, `assets/old_style.css`, layout-specific CSS

**Change:** After removing old_style.css (Step 7.2), audit shared.css for any styles that are duplicated in the layout-specific Tailwind input files. Move truly shared styles (canvas, markdown rendering) into shared.css and remove duplicates from layout files.

**Validation:**
1. Build with each active layout. Verify visual appearance is unchanged.
2. No duplicate CSS rules visible in browser DevTools "Computed" tab.

---

## Phase 8: Low-Severity Polish

---

### Step 8.1 — Replace Deprecated strings.Title()

**Review item:** L1
**File:** `internal/obsidian/markdown/transformer.go:110`

**Change:**
```go
import "golang.org/x/text/cases"
import "golang.org/x/text/language"

// Replace:
strings.Title(cType)
// With:
cases.Title(language.English).String(cType)
```

**Validation:** `devenv shell -- go build ./...` compiles. Existing tests pass.

---

### Step 8.2 — Fix Highlight Regex Edge Case

**Review item:** L3
**File:** `internal/obsidian/markdown/transformer.go:57`

**Change:**
```go
// Before:
re := regexp.MustCompile(`==([^=]+)==`)
// After:
re := regexp.MustCompile(`==(.+?)==`)
```

**Validation:** Add test: `==a = b==` → `<mark>a = b</mark>`.

---

### Step 8.3 — Fix Tag Regex to Support Unicode

**Review item:** L4
**File:** `internal/obsidian/obsidian.go:32`

**Change:**
```go
// Before:
tagRegex = regexp.MustCompile(`(?m)(?:^|\s)(#[a-zA-Z0-9_\-]+)`)
// After:
tagRegex = regexp.MustCompile(`(?m)(?:^|\s)(#[\p{L}\p{N}_\-]+)`)
```

`\p{L}` matches any Unicode letter, `\p{N}` matches any Unicode digit.

**Validation:** Add test: `#café` → extracted as tag. `#日本語` → extracted. `#123` → still extracted (decide if number-only tags should be excluded).

---

### Step 8.4 — Consolidate Image Extension Lists

**Review item:** L6
**Files:** `internal/builder/utils.go:65-82`, `internal/obsidian/markdown/wikilinks.go:593-596`

**Change:** Create a shared set in a common location (e.g., `internal/obsidian/filetypes.go`):
```go
var ImageExts = map[string]bool{
    ".png": true, ".jpg": true, ".jpeg": true, ".gif": true,
    ".webp": true, ".svg": true, ".avif": true, ".bmp": true,
    ".ico": true, ".tiff": true,
}

func IsImageExt(ext string) bool {
    return ImageExts[strings.ToLower(ext)]
}
```

Replace `isImageExt` in builder and `isImageFile` in wikilinks with calls to the shared function.

**Validation:** `devenv shell -- go test ./...` passes. No behavior change for existing extensions; `.bmp`/`.ico`/`.tiff` now recognized.

---

### Step 8.5 — Fix bases.go InFolder Case Sensitivity

**Review item:** L8
**File:** `internal/obsidian/bases/bases.go:268-274`

**Change:** (Already part of Step 5.2, but listed here for completeness.) Use `strings.EqualFold` and `strings.ToLower` for folder comparisons.

---

### Step 8.6 — Fix bases.go isTrue to Handle Truthy Values

**Review item:** L9
**File:** `internal/obsidian/bases/bases.go:1284-1292`

**Change:**
```go
func isTrue(v any) bool {
    if v == nil { return false }
    switch val := v.(type) {
    case bool:
        return val
    case int:
        return val != 0
    case int64:
        return val != 0
    case float64:
        return val != 0
    case string:
        return val != ""
    }
    return false
}
```

**Validation:** Add tests in bases_test.go: `isTrue(0)` → false, `isTrue(1)` → true, `isTrue("")` → false, `isTrue("x")` → true, `isTrue(nil)` → false, `isTrue(true)` → true.

---

### Step 8.7 — Add Backpressure Awareness to imgopt

**Review item:** L7
**File:** `internal/imgopt/imgopt.go:278-318`

**Change:** Add a memory-aware limit. The simplest approach: limit the buffered channel to `maxWorkers` instead of `len(jobs)`:
```go
jobCh := make(chan ImageJob, maxWorkers) // was: len(jobs)
```

This ensures at most `maxWorkers` jobs are buffered at a time. The sender goroutine will block when the channel is full, creating natural backpressure.

Also return an error map (from Step 4.3):
```go
func ProcessImages(jobs []ImageJob, breakpoints []int, maxWorkers int) (map[string]*Result, map[string]error) {
```

**Validation:**
1. `devenv shell -- go test ./internal/imgopt/...` passes.
2. Verify existing image processing still works on demo vault.

---

### Step 8.8 — Add Debouncing to Back-to-Top Button

**File:** `assets/default_app.js` (initBackToTop function, ~line 458-476)

**Change:** Use `requestAnimationFrame` or a simple throttle:
```javascript
var scrollTicking = false;
container.addEventListener("scroll", function () {
    if (!scrollTicking) {
        requestAnimationFrame(function () {
            btn.classList.toggle("show", container.scrollTop > 300);
            scrollTicking = false;
        });
        scrollTicking = true;
    }
});
```

**Validation:** Manual test: scroll quickly, verify button appears/disappears smoothly without jank.

---

### Step 8.9 — Document FlatURLs Convention

**File:** `docs/Features/Configuration File.md` (or relevant doc)

Add a clear explanation of what `flat-urls: true` means:
> When `flat-urls` is enabled, pages are generated as directory-based clean URLs (`/page/index.html` served as `/page/`). When disabled, pages are generated as direct HTML files (`/page.html`).

**Validation:** Documentation review only.

---

### Step 8.10 — Clean Up Commented-Out Code

**Files:** Search all Go and JS files for large blocks of commented-out code:
```
grep -rn '// *TODO\|// *FIXME\|// *HACK' internal/
```

Remove any dead code blocks that are clearly no longer needed. Leave meaningful TODOs.

**Validation:** `devenv shell -- go build ./...` compiles.

---

### Step 8.11 — Add Missing Encoder Handling in imgopt

**File:** `internal/imgopt/imgopt.go`

When `cwebp` or `avifenc` are not installed, the functions return `ErrNoEncoder`. But `ProcessImage` doesn't clearly communicate this to the user. Add a startup check in the CLI:

In `internal/cli/generate.go` (or dev.go), at startup:
```go
if _, err := exec.LookPath("cwebp"); err != nil {
    log.Warn("cwebp not found — WebP image optimization disabled")
}
if _, err := exec.LookPath("avifenc"); err != nil {
    log.Warn("avifenc not found — AVIF image optimization disabled")
}
```

**Validation:** Manual test: remove cwebp from PATH, run `forge generate`. Verify warning appears.

---

### Step 8.12 — Make Command-Mode Reload Delay Configurable

**File:** `static/src/modes/command-mode.js:77`

**Change:** Replace hardcoded `450` with a constant at the top of the file:
```javascript
const RELOAD_DELAY_MS = 450;
```

This makes it easy to tune and documents the intent.

**Validation:** No behavior change. Code clarity improvement only.

---

## Appendix: Recommended Execution Order

For maximum safety and minimum risk, execute phases in order. Within each phase, steps can be done in any order unless noted. Key dependencies:

- **Phase 3 (Steps 3.1-3.6) must be sequential** — each step builds on the previous.
- **Step 2.11 (extract buildDefault)** should happen after Step 1.4 (writeTemplate helper) since the helper is used during extraction.
- **Phase 6 (test expansion)** should happen after Phase 3 (BuildContext) since the tests depend on being able to construct a BuildContext.
- **Step 7.1 (shared JS)** should happen before Step 7.2 (remove old JS) to avoid temporarily breaking layouts.

**Estimated scope:** ~70 steps total. Each step is independently committable and testable. A reasonable pace is 3-5 steps per session, completing the full guide in approximately 15-20 sessions.
