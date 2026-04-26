# Forge Code Review

**Date:** 2026-04-12
**Scope:** Full codebase review (all Go, JS, CSS, templates, configuration, tests)
**Build status:** Compiles cleanly, `go vet` clean, all tests pass (including `-race`)
**Overall test coverage:** 21.4% of statements

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Architecture Overview](#architecture-overview)
3. [Critical Issues](#critical-issues)
4. [High-Severity Issues](#high-severity-issues)
5. [Medium-Severity Issues](#medium-severity-issues)
6. [Low-Severity Issues](#low-severity-issues)
7. [Test Coverage Analysis](#test-coverage-analysis)
8. [JavaScript & CSS Review](#javascript--css-review)
9. [Positive Patterns](#positive-patterns)
10. [Recommendations](#recommendations)

---

## Executive Summary

Forge is a well-structured Obsidian vault to static site generator with a clear package-per-domain architecture, good dependency choices, and solid features (incremental builds, image optimization, overlay dev tools, graph visualization). The codebase shows ambition and good instincts.

However, the review uncovered **5 critical issues**, **12 high-severity issues**, and numerous medium/low issues spanning architecture, correctness, error handling, and test coverage. The most systemic problems are:

1. **Mutable global state in the builder** makes the core of the application untestable and thread-unsafe
2. **Pervasive silent error swallowing** across nearly every package
3. **21.4% test coverage** with the builder (the most complex package) at 1.3%
4. **HTML output constructed via string concatenation** without escaping in multiple locations
5. **Massive functions** (450+ lines) that combine scanning, parsing, rendering, and I/O in a single codepath

The codebase is functional and works for its intended use case, but needs significant refactoring to be maintainable and reliable long-term.

---

## Architecture Overview

```
forge/
├── cmd/forge/main.go           Entry point (Cobra CLI)
├── cmd/kiln-palette/main.go    Utility: theme color palette generator
├── internal/
│   ├── builder/                 Core build pipeline (default + custom modes)
│   ├── cli/                     Command definitions (dev, serve, generate, etc.)
│   ├── config/                  YAML config loading
│   ├── i18n/                    Static label translations
│   ├── imgopt/                  Image optimization (AVIF/WebP/PNG)
│   ├── jsonld/                  Structured data generation
│   ├── linter/                  Broken link detection
│   ├── obsidian/                Vault scanning, link resolution, markdown processing
│   ├── ogimage/                 OpenGraph image generation
│   ├── ops/                     LLM agent tools + HTTP handlers for overlay
│   ├── overlay/                 Dev overlay injection, SSE events, static serving
│   ├── proxy/                   Reverse proxy for API backends
│   ├── rss/                     RSS feed generation
│   ├── search/                  Search index generation
│   ├── server/                  HTTP server + routing
│   ├── templates/               Templ-generated HTML templates
│   └── watch/                   File watching, dependency graph, incremental builds
├── assets/                      Embedded CSS/JS/fonts (go:embed)
└── static/                      Overlay UI source (ES6 modules)
```

**Dependencies are well-chosen:** goldmark, templ, cobra, chroma, fsnotify, minify. No unnecessary frameworks.

**Package boundaries are mostly clean** with one major exception: the builder package depends on nearly everything and uses global state to communicate configuration.

---

## Critical Issues

### C1. Mutable Global State in Builder Package
**File:** `internal/builder/builder.go:56-71`
**Impact:** Blocks testability, thread-unsafe, couples everything

```go
var (
    OutputDir         string
    InputDir          string
    FlatUrls          bool
    ThemeName         string
    // ... 10 more global variables
)
var RebuildFilter map[string]struct{}
```

All build configuration lives in package-level mutable variables. This means:
- **Cannot run tests in parallel** (tests would stomp each other's state)
- **Cannot run multiple builds concurrently** (e.g., preview + production)
- **No way to inject test doubles** for configuration
- **RebuildFilter** is a mutable global map with no synchronization — race condition if incremental builds overlap with full builds

**Fix:** Replace with a `BuildContext` struct passed to `Build()` and `IncrementalBuild()`.

---

### C2. Dead Code After log.Fatal()
**File:** `cmd/forge/main.go:24-25`

```go
if err := rootCmd.Execute(); err != nil {
    log.Fatal(err)
    os.Exit(1) // ← unreachable: log.Fatal already calls os.Exit(1)
}
```

`log.Fatal()` from charmbracelet/log calls `os.Exit(1)` internally. The `os.Exit(1)` on the next line is dead code. This reveals a misunderstanding of the logging library's API — either use `log.Error(err)` + `os.Exit(1)`, or just `log.Fatal(err)`.

---

### C3. JPEG Encoding Silently Produces PNG
**File:** `internal/imgopt/imgopt.go:247-250`

```go
case "jpeg":
    // Use png as fallback for simplicity; JPEG encoding would need
    // "image/jpeg" Encode which we can add later.
    return png.Encode(f, img)
```

When processing JPEG source images, the fallback encoder writes PNG format data into a file that may have a `.jpeg` extension. The result is a file whose extension lies about its format. Browsers and CDNs that trust file extensions will serve wrong `Content-Type` headers.

**Fix:** Import `"image/jpeg"` and use `jpeg.Encode(f, img, &jpeg.Options{Quality: quality})`. This is a one-line fix.

---

### C4. CleanOutputDir Has No Path Validation
**File:** `internal/builder/utils.go:47-48`

```go
func CleanOutputDir(log *slog.Logger) {
    err := os.RemoveAll(OutputDir)
```

`OutputDir` is a global variable. If it's ever empty string (which `""` resolves to current directory with `os.RemoveAll`), or set to `/` or a home directory by a bug elsewhere, this deletes everything. There is zero validation.

**Fix:** Add a guard: refuse to proceed if `OutputDir` is empty, `/`, a home directory, or doesn't contain an expected marker file.

---

### C5. Panic Risk: Deferred Close on Nil File
**File:** `internal/builder/builder_default.go` (multiple locations around lines 287-360)

```go
cssOut, err := os.Create(filepath.Join(OutputDir, "style.css"))
if err != nil {
    log.Error("Couldn't create 'style.css'", "error", err)
}
defer cssOut.Close()  // ← panics if cssOut is nil (when err != nil)
```

When `os.Create` fails, `cssOut` is nil. The code logs the error but does **not return or skip** — it falls through to `defer cssOut.Close()` and then to `template.Execute(cssOut, ...)`, both of which will panic on nil. This pattern is repeated for JS, graph, canvas, search, and link-preview asset files (6+ locations).

**Fix:** Return or continue after the error, or guard the defer.

---

## High-Severity Issues

### H1. buildDefault() Is 450+ Lines With Mixed Concerns
**File:** `internal/builder/builder_default.go`

This single function handles: vault scanning, markdown rendering, folder index generation, CSS/JS asset creation, search index building, graph JSON generation, canvas processing, OG image generation, and sitemap/RSS output. It's extremely difficult to reason about, test, or modify safely.

**Fix:** Extract into focused functions: `renderPages()`, `writeAssets()`, `buildSearchIndex()`, `processCanvasFiles()`, `generateOGImages()`, etc.

---

### H2. builder_custom.go validateFrontmatterField Is 174 Lines of Nested Switches
**File:** `internal/builder/builder_custom.go:941-1115`

A single function with nested `switch` statements covering 12+ field types. Each type has its own parsing, validation, and conversion logic inline. Adding a new field type means touching this massive function.

**Fix:** Use a `FieldValidator` interface with per-type implementations, or at minimum a map of type→handler functions.

---

### H3. HTML Output Via String Concatenation Without Escaping
**Files:** Multiple locations across the codebase

| Location | Issue |
|----------|-------|
| `obsidian/markdown/transformer.go:147` | Callout title injected raw: `cTitle + "</div>"` |
| `obsidian/markdown/wikilinks.go:580` | Broken embed link: `"<a href=\"" + webPath + "\">"` |
| `obsidian/markdown/toc.go:38` | TOC heading text unescaped in `<a>` tag |
| `obsidian/sitemap.go:51` | URLs written to XML without entity escaping |
| `obsidian/markdown/transformer.go:77` | Mermaid content in `data-original` attribute not properly quoted |

Any heading, title, or path containing `<`, `>`, `&`, or `"` will produce malformed HTML/XML. While this is an internal tool, it means vault content with these characters will render incorrectly or break page structure.

**Fix:** Use `html.EscapeString()` for HTML contexts, `url.PathEscape()` for URLs, and `xml.Marshal` for XML output.

---

### H4. Content-Length Not Recalculated After Overlay Injection
**File:** `internal/overlay/inject.go`

The injection middleware inserts CSS/JS `<link>` and `<script>` tags into HTML responses, increasing the body size. It correctly strips the old `Content-Length` header but never sets a new one. While HTTP/1.1 chunked encoding handles this gracefully in most cases, some clients or proxies that depend on `Content-Length` may truncate the response.

**Fix:** Set `Content-Length` to the new body length after injection.

---

### H5. Silent Error Swallowing Is Pervasive
This is the single most common code quality issue across the entire codebase:

| File | Line | What's swallowed |
|------|------|------------------|
| `builder/builder_default.go` | ~280 | Search index write errors |
| `builder/builder_default.go` | ~860 | OG image generation errors |
| `builder/stats.go` | 24 | `os.ReadFile` error: `_, _ =` |
| `obsidian/obsidian.go` | 196 | YAML parse errors (logged with `fmt.Printf`) |
| `linter/linter.go` | 90 | `os.ReadFile` error ignored |
| `linter/linter.go` | 17-19 | `WalkDir` errors returned as nil |
| `imgopt/imgopt.go` | 278-318 | Individual image processing errors dropped in parallel loop |
| `ops/handler.go` | 179 | `json.Encode` error ignored: `_ =` |
| `jsonld/jsonld.go` | 64-67 | `json.Marshal` error returns `""` |
| `cli/commands.go` | 119-123 | Config file errors produce empty config silently |

The pattern is: error is either completely ignored (`_ =`), logged at wrong level, or logged but execution continues as if nothing happened. The user has no way to know their build partially failed.

**Fix:** Establish a consistent error strategy: collect errors during build, report a summary at the end, and exit with non-zero status if any occurred.

---

### H6. Wikilink Path Matching Uses strings.Contains (Too Loose)
**File:** `internal/obsidian/markdown/wikilinks.go:103-109`

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

`strings.Contains` matches substrings: looking for `"Folder/Note"` would match a file at path `"MyFolder/NoteBook.md"`. This can resolve wikilinks to the wrong file.

**Fix:** Use `strings.HasSuffix(file.RelPath, "/"+dest)` or proper path matching.

---

### H7. Vault Scan Failure Hidden in Dev Mode
**File:** `internal/cli/dev.go:159-170`

```go
if err := vault.Scan(); err != nil {
    log.Error("failed to rescan vault", "err", err)
    return nil  // ← returns nil error, caller thinks success
}
```

During `forge dev`, if a vault rescan fails (disk full, permissions, etc.), the error is logged but `nil` is returned. The watcher continues with stale data, and the user sees no indication of the problem.

---

### H8. ops/tools.go Glob Pattern Matches Basename Only
**File:** `internal/ops/tools.go:116`

```go
filepath.Match(pattern, info.Name())
```

The `ListFiles` tool matches glob patterns against `info.Name()` (just the filename, e.g., `"note.md"`), not the full relative path. Patterns like `blog/*.md` or `**/test.md` won't work as expected — they can only match simple filenames.

**Fix:** Match against the full relative path: `filepath.Match(pattern, rel)`.

---

### H9. HTTP Client Created Per Request in Agent
**File:** `internal/ops/agent.go` (lines ~544, 581, 644)

New `http.Client` instances are created for each API call. This defeats connection pooling and keep-alive, leading to unnecessary TCP handshake overhead and potential connection exhaustion under load.

**Fix:** Create a single `http.Client` with appropriate timeouts and reuse it.

---

### H10. SSE Broker Silently Drops Messages
**File:** `internal/overlay/events.go:24-29`

```go
select {
case ch <- payload:
default: // dropped — subscriber too slow
}
```

If a subscriber's channel is full (buffer size 8), events are silently dropped. The subscriber has no way to know it missed events, which means the overlay UI could show stale state.

**Fix:** At minimum, track a drop counter. Better: send a "you missed events, please refresh" sentinel.

---

### H11. No Request Body Size Limit on API Handlers
**File:** `internal/ops/handler.go`

The JSON decoder reads request bodies without any size limit. A malformed or malicious request could send gigabytes of data.

**Fix:** Wrap the reader with `http.MaxBytesReader(w, r.Body, maxSize)`.

---

### H12. Circular Embed Detection Missing
**File:** `internal/obsidian/markdown/wikilinks.go`

If note A embeds note B and note B embeds note A, the embed rendering could recurse infinitely. There's no cycle detection or depth limit.

**Fix:** Track visited files during embed resolution and bail at a reasonable depth (e.g., 10 levels).

---

## Medium-Severity Issues

### M1. Config ValueOr/BoolOr Use Hardcoded Switch Statements
**File:** `internal/config/config.go`

Adding a new config field requires updating the struct, the switch in `ValueOr()`, and the switch in `BoolOr()`. If any are missed, the field silently returns the default value with no error. Use reflection or code generation to keep these in sync.

### M2. Global CLI Flag Variables
**File:** `internal/cli/commands.go:71-87`

All CLI flags are package-level `var` declarations shared across commands. Same testability and concurrency problems as the builder globals.

### M3. Dependency Graph Link Parsing Is Regex-Based on Raw Text
**File:** `internal/watch/depgraph.go:106-143`

Links in code blocks, HTML comments, or frontmatter are incorrectly treated as real links. Should parse the markdown AST (which is already parsed by goldmark during rendering) rather than regex on raw text.

### M4. Theme Definitions Hardcoded in Go Source
**File:** `internal/builder/themes.go:257-349`

11 color themes with 14 fields each are defined as Go struct literals. Adding or modifying a theme requires recompiling. Should be in a config file or embedded YAML.

### M5. Case Sensitivity Inconsistencies
Multiple packages lowercase names for comparison but inconsistently:
- `depgraph.parseWikilink` lowercases targets
- `obsidian/markdown/wikilinks.go` does case-insensitive index lookup with fallback
- `obsidian/bases/bases.go` `InFolder` comparison is case-sensitive
- Tag matching is sometimes case-sensitive, sometimes not

This leads to subtle bugs where `[[MyNote]]` and `[[mynote]]` may or may not resolve to the same file depending on the code path.

### M6. Slugify Only Replaces Spaces
**File:** `internal/obsidian/paths.go`

Slug generation only lowercases and replaces spaces with hyphens. Special characters like `(`, `)`, `?`, `#`, `&`, `'` survive into URLs. File named `"My (Draft) [v2].md"` becomes `"my-(draft)-[v2]"`.

### M7. RSS Entry Limit Hardcoded
**File:** `internal/obsidian/rss.go:23`

Magic number `50` for maximum RSS entries. Should be configurable.

### M8. Sitemap URLs Not XML-Escaped
**File:** `internal/obsidian/sitemap.go:51`

URLs are written directly into XML using `WriteString` without entity escaping. A URL containing `&` produces invalid XML.

### M9. No Cycle Detection in Dependency Graph
**File:** `internal/watch/changeset.go`

`ComputeChangeSet` follows dependents transitively but has no cycle guard. If the dependency graph has cycles (A→B→A), this could loop. In practice, the current graph structure makes this unlikely but not impossible.

### M10. Timer in Watcher Not Configurable
**File:** `internal/watch/watcher.go`

Debounce duration is hardcoded. CSS-only changes that could rebuild instantly must wait the same debounce period as full vault rescans.

### M11. Reverse Proxy Missing X-Forwarded Headers
**File:** `internal/proxy/reverse.go:21-24`

The Director only sets `URL.Scheme`, `URL.Host`, and `Host`. Standard proxy headers (`X-Forwarded-For`, `X-Forwarded-Proto`, `X-Real-IP`) are not set.

### M12. ops/agent.go Silent Type Assertion Failures
**File:** `internal/ops/agent.go:166-167`

```go
stopReason, _ := resp["stop_reason"].(string)
content, _ := resp["content"].([]any)
```

If the API response shape changes or has unexpected types, these silently return zero values. The agent could terminate prematurely or misinterpret responses.

### M13. Navbar Folder-File Name Collision
**File:** `internal/obsidian/navbar.go:81-97`

If both `docs.md` and `docs/` directory exist, the folder's path gets overwritten with the file's path. The user loses access to one of them in the navigation.

### M14. FlatURLs Comment/Name Mismatch
**File:** `internal/obsidian/paths.go:98`

Comment says "Handle **non** flat urls by using the slug path as a folder" but the code is inside `if o.FlatURLs {` (true). The logic is consistent across the codebase so it's probably working as intended, but the misleading comment makes the naming ambiguous. "FlatURLs" apparently means "clean/pretty URLs" (directory-based), not "flat file URLs".

### M15. Duplicate Template Rendering Code
**File:** `internal/builder/builder_default.go:287-360`

Six nearly identical blocks of: `os.Create()` → error check → `defer Close()` → `template.Execute()` → error check. Should be extracted into a helper.

---

## Low-Severity Issues

### L1. `strings.Title()` Is Deprecated
**File:** `internal/obsidian/markdown/transformer.go:110`
Use `cases.Title()` from `golang.org/x/text/cases` (Go 1.18+).

### L2. Logger Inconsistency
Some errors use `fmt.Printf`, others `log.Error`, others `slog.Warn`. Should standardize on `slog` throughout.

### L3. Highlight Regex Edge Case
**File:** `internal/obsidian/markdown/transformer.go:57`
Pattern `==([^=]+)==` won't match highlights containing `=` (e.g., `==a = b==`). Use non-greedy `==(.+?)==` instead.

### L4. Tag Regex Misses Unicode Characters
**File:** `internal/obsidian/obsidian.go:32`
Pattern `#[a-zA-Z0-9_\-]+` only matches ASCII. Tags with accented characters (e.g., `#café`) are not extracted.

### L5. old_app.js Should Be Removed
**File:** `assets/old_app.js`
393 lines of deprecated code with broken MathJax URLs and commented-out blocks. If the "old" layout is deprecated, remove the dead code.

### L6. Image Extension Lists Duplicated
`isImageExt` and `isAllowedExt` in `builder/utils.go` partially overlap with `isImageFile` in `obsidian/markdown/wikilinks.go:592`. Neither includes `.bmp`, `.ico`, or `.tiff`.

### L7. No Backpressure on Image Optimization
**File:** `internal/imgopt/imgopt.go`
`ProcessImages` creates a buffered channel of `len(jobs)` and spawns `maxWorkers` goroutines but doesn't limit total memory for decoded images.

### L8. bases.go InFolder Is Case-Sensitive
**File:** `internal/obsidian/bases/bases.go:268-274`
`infolder("Assets")` won't match files in `assets/` directory.

### L9. bases.go isTrue Only Accepts bool
**File:** `internal/obsidian/bases/bases.go:1284-1292`
Non-bool truthy values (non-zero integers, non-empty strings) return false. Comparison expressions that produce int/float results will be treated as false.

### L10. Missing Error Check on fmt.Sscanf
**File:** `cmd/kiln-palette/main.go`
Hex color parsing via `fmt.Sscanf` doesn't check the error return. Invalid hex silently falls through to magenta fallback.

### L11. Server Goroutine Shutdown Uses Different Context
**File:** `internal/server/server.go:89-91`
```go
go func() {
    <-ctx.Done()
    srv.Shutdown(context.Background())  // should use a timeout context
}
```

### L12. Search Index Not Debounced
**File:** `assets/search.js`
Search executes on every keystroke without debouncing. Fast typists trigger many unnecessary search operations.

---

## Test Coverage Analysis

### Coverage by Package

| Package | Coverage | Verdict |
|---------|----------|---------|
| `i18n` | 100.0% | Excellent |
| `proxy` | 100.0% | Excellent |
| `overlay` | 94.2% | Excellent |
| `search` | 93.1% | Excellent |
| `jsonld` | 92.3% | Excellent |
| `rss` | 87.5% | Good |
| `watch` | 86.7% | Good |
| `linter` | 86.9% | Good |
| `ogimage` | 86.0% | Good |
| `imgopt` | 80.7% | Good |
| `config` | 69.0% | Acceptable |
| `ops` | 59.0% | Needs work |
| `obsidian/markdown` | 47.5% | Needs work |
| `server` | 40.2% | Needs work |
| `obsidian` | 12.2% | Poor |
| `templates` | 11.3% | Poor |
| `builder` | **1.3%** | **Critical gap** |
| `cli` | 0.0% | None |
| `obsidian/bases` | 0.0% | None |

### Key Gaps

1. **Builder at 1.3%** — The most complex and important package has essentially no test coverage. The few existing tests only cover `shouldRebuild` filter logic and a small OG image test. The main `buildDefault()` and `buildCustom()` functions are completely untested.

2. **CLI at 0%** — No command-level tests. The entry points for `dev`, `serve`, `generate`, `clean`, `doctor`, `init`, and `stats` are untested.

3. **obsidian/bases at 0%** — The base file evaluation engine (used in custom mode for filtering, sorting, grouping) has zero tests despite containing complex type coercion and comparison logic.

4. **obsidian at 12.2%** — The vault scanning and link resolution core is mostly untested. Only backlink generation and a few link-related scenarios have tests.

5. **Templates at 11.3%** — Template helpers have good tests, but the actual rendered HTML output (the product the user sees) is essentially untested.

### Missing Test Categories

- **No integration tests** for CLI commands (end-to-end: input vault → generated site)
- **No tests for custom mode** field validation, collection configuration, or template rendering
- **No tests for incremental builds** with actual file mutations
- **No tests for error paths** in most packages (what happens when disk is full? permissions denied?)
- **No concurrent access tests** for the global builder state
- **No snapshot/golden-file tests** for rendered HTML output
- **Frontend: only 1 test file** (`static/src/__tests__/api.test.js`) covering API helpers. No tests for any UI components, modes, or event handling.

---

## JavaScript & CSS Review

### Structural Issues

**JS1. Massive Code Duplication Between Layouts (HIGH)**
`default_app.js` and `simple_app.js` share ~90% identical code: theme toggle, MathJax init, Mermaid init, copy buttons, lightbox. Extract shared functionality into a common module.

**JS2. Global Namespace Pollution (MEDIUM)**
`default_app.js` puts 14+ functions on the `window` object and uses `window._sidebarDelegationBound`, `window._panels`, etc. for state tracking. Use module pattern or classes.

**JS3. innerHTML Used Without Sanitization (MEDIUM)**
`canvas.js` uses `innerHTML` with `marked.parse()` output and user-provided data (node colors, URLs, file names) in 12+ locations. Template literal interpolation of `nodeData.url`, `nodeData.file`, `imgSrc` etc. could inject HTML if the source data contains special characters.

**JS4. No Debouncing on Input/Scroll Events (LOW)**
- Search input fires on every keystroke
- Back-to-top button checks scroll position without throttling
- Canvas/graph renders don't use requestAnimationFrame for drag operations

**JS5. Canvas Renderer Performance (LOW)**
- All nodes rendered regardless of viewport visibility (no culling)
- SVG arrow marker recreated on every render
- Bezier curves recalculated for every edge on every frame

### CSS Issues

**CSS1. Duplicate Styles Across Files**
Canvas, node, and theme styles appear in both `shared.css`, `old_style.css`, and layout-specific files with slight variations.

**CSS2. Legacy CSS Should Be Removed**
`old_style.css` (1400 lines) has commented-out blocks, Go template variables mixed in, and no clear separation from the active stylesheets.

### Overlay UI (static/src/)

The overlay module system is well-designed with clean separation:
- `main.js` → bootstrap, `api.js` → HTTP, `events.js` → SSE, `state.js` → state factory
- Mode modules (`command-mode.js`, `editor-mode.js`, etc.) are cleanly separated
- UI components (`modal.js`, `toast.js`, `sheet.js`) are simple and focused

Issues:
- **No focus trap in modals** — tab key escapes the modal
- **No keyboard ESC handler** to close modals
- **Toast notifications lack `aria-live`** for accessibility
- **No form validation** in new-page-mode
- **Hard-coded strings** throughout (no i18n preparation)
- **Auto-reload delay** of 450ms in command-mode is arbitrary

---

## Positive Patterns

The codebase is not all problems. Several patterns deserve recognition:

1. **Package organization** is clean and follows Go conventions. Each package has a single clear responsibility.
2. **Functional options pattern** in the obsidian package (`WithInputDir`, `WithOutputDir`, etc.) is idiomatic and extensible.
3. **Dependency choices** are excellent: goldmark, templ, cobra, chroma are all well-maintained, focused libraries.
4. **Incremental build system** (watch + depgraph + changeset + mtimestore) is well-designed with proper debouncing and dependency tracking.
5. **Overlay architecture** (events.go + inject.go + static.go) is clean, minimal, and well-tested (94.2% coverage).
6. **Proxy package** is simple and correct (100% coverage).
7. **i18n package** is complete with reflection-based validation test that ensures all fields are populated for all languages.
8. **ops/lock.go** is a clean, correct, minimal mutex implementation.
9. **ops/resolve.go** properly uses RWMutex for thread-safe path index lookups.
10. **Test quality where tests exist** is generally good — proper table-driven tests, edge cases, and assertions. The problem is coverage breadth, not test quality.
11. **Dev overlay** (static/src/) uses clean ES6 modules with proper separation of concerns.
12. **Image optimization** with AVIF/WebP/PNG fallback chain and responsive breakpoints is well-thought-out (minus the JPEG bug).

---

## Recommendations

### Phase 1: Fix Critical Bugs (Immediate)

1. **Remove dead `os.Exit(1)` after `log.Fatal()`** in `cmd/forge/main.go`
2. **Fix JPEG encoding** — import `"image/jpeg"` and use `jpeg.Encode()`
3. **Guard `CleanOutputDir`** — refuse empty/root/home paths
4. **Fix panic-on-nil in asset file creation** — return/continue after `os.Create` errors
5. **Add `html.EscapeString()`** to all HTML string concatenation in transformer.go, toc.go, wikilinks.go

### Phase 2: Architectural Refactoring (Next Sprint)

1. **Replace builder globals with BuildContext struct** — this unblocks testability for the entire core
2. **Break `buildDefault()` into 5-6 focused functions** — each under 80 lines
3. **Extract shared JS** between default_app.js and simple_app.js into a common module
4. **Implement error collection** — build functions return `[]error` or use an ErrorCollector
5. **Add integration test** that runs a full build on the demo vault and validates output

### Phase 3: Improve Coverage (Ongoing)

1. **Builder tests** — with BuildContext, write tests for each extracted function
2. **Custom mode tests** — field validation, collection sorting, template rendering
3. **CLI tests** — at least smoke tests that commands parse flags correctly
4. **bases package tests** — filter, sort, group operations with edge cases
5. **Golden-file tests** — snapshot a few rendered pages and diff against expected output

### Phase 4: Polish (Backlog)

1. Move theme definitions to embedded YAML
2. Standardize logging on slog throughout
3. Fix case sensitivity inconsistencies
4. Add XML escaping to sitemap generation
5. Remove deprecated old_app.js and old_style.css
6. Add debouncing to search input
7. Implement focus trapping in overlay modals
8. Make RSS entry limit and debounce duration configurable

---

*Review conducted via static analysis, test execution (`go vet`, `go test ./...`, `go test -race ./...`), coverage profiling, and comprehensive line-by-line reading of all source files.*
