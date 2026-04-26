# Forge Code Review

**Date:** 2026-04-16
**Commit:** `aec57cd` (v0.13.0)
**Branch:** `refactor/review-guide-no-phase3`
**Reviewer:** Claude (automated analysis)
**Scope:** Full codebase review — Go backend, JS/CSS frontend, architecture, security, testing

---

## Executive Summary

Forge is a well-structured static site generator for Obsidian vaults with ~28.7% overall test coverage. A significant refactoring effort (Steps 1.x through 8.x) has addressed many issues from a prior review — including HTML escaping, circular embed detection, path validation, error collection, and BuildContext introduction. However, several categories of issues remain:

- **1 critical SSE protocol bug** that breaks live reload
- **3 high-severity security issues** (path traversal, XSS, unescaped attributes)
- **Persistent global mutable state** despite BuildContext introduction
- **11 os.Exit calls** in custom build mode making it untestable
- **Low test coverage** in key packages (obsidian: 16.7%, bases: 5.9%, templates: 11.3%)
- **Significant JS code duplication** between layout files (~80% overlap)

### Severity Legend

| Tag | Meaning |
|-----|---------|
| **C** | Critical — crashes, data corruption, protocol violation |
| **H** | High — security vulnerability, silent wrong behavior |
| **M** | Medium — correctness concern, maintainability debt |
| **L** | Low — polish, style, minor improvement |

---

## Table of Contents

- [Critical Issues](#critical-issues) (C1–C3)
- [High-Severity Issues](#high-severity-issues) (H1–H8)
- [Medium-Severity Issues](#medium-severity-issues) (M1–M13)
- [Low-Severity Issues](#low-severity-issues) (L1–L10)
- [Test Coverage Analysis](#test-coverage-analysis)
- [Architecture Assessment](#architecture-assessment)
- [Previously Fixed Issues](#previously-fixed-issues)

---

## Critical Issues

### C1 — SSE Newline Escape Bug Breaks Live Reload

**File:** `internal/overlay/events.go:72`

```go
_, _ = fmt.Fprintf(w, "data: %s\\n\\n", msg)
```

In Go, `\\n` in a double-quoted string literal produces the two-character sequence `\n` (literal backslash + n), **not** a newline. The SSE specification requires actual newline characters (`\n`) to delimit messages. This means:

- Clients receive `data: {"type":"rebuilt"}\n\n` as a single unterminated line
- The browser's `EventSource` never sees a complete SSE message
- **Live reload is broken** — the overlay UI never receives rebuild notifications

The existing test (`events_test.go:41`) only checks `strings.Contains(body, "data: ...")` which matches the substring regardless of newline handling, masking the bug.

**Fix:** Change `\\n` to `\n`:
```go
_, _ = fmt.Fprintf(w, "data: %s\n\n", msg)
```

**Priority:** Immediate — this is a functionality-breaking bug in the core dev workflow.

---

### C2 — Path Traversal in Clean URL Handler

**File:** `internal/server/server.go:45-59`

```go
if filepath.Ext(path) == "" {
    htmlPath := filepath.Join(outputDir, path+".html")
    if _, err := os.Stat(htmlPath); err == nil {
        http.ServeFile(w, r, htmlPath)
        return
    }
    localPath := filepath.Join(outputDir, path)
    // ...
}
```

`path` comes directly from `r.URL.Path`. Go's `filepath.Join` normalizes `..` components, so `filepath.Join("/var/www/public", "/../../../etc/passwd")` resolves to `/etc/passwd`. While `http.ServeFile` has its own path traversal protections (it checks for `..` in the *request* path), the code constructs filesystem paths manually and calls `os.Stat` on them before `http.ServeFile` — the `Stat` call itself leaks information about file existence outside the output directory.

**Fix:** Validate the resolved path stays within `outputDir`:
```go
abs, _ := filepath.Abs(filepath.Join(outputDir, path+".html"))
if !strings.HasPrefix(abs, filepath.Clean(outputDir)+string(filepath.Separator)) {
    http.NotFound(w, r)
    return
}
```

**Priority:** High — information disclosure at minimum; potential file read depending on `http.ServeFile` behavior with pre-validated paths.

---

### C3 — Nil Pointer Dereference in Custom Mode Render

**File:** `internal/builder/builder_custom.go:436-439`

```go
} else {
    config := s.ConfigsLookup[page.Collection]
    tmpl = config.Template          // panics if config is nil
    tmplPath = filepath.Base(config.LayoutPath)
}
```

If `page.Collection` is empty or doesn't exist in `ConfigsLookup`, `config` is nil, and the next line panics. This can be triggered by a markdown file in custom mode that doesn't belong to any configured collection.

**Fix:** Add a nil check:
```go
config, ok := s.ConfigsLookup[page.Collection]
if !ok {
    log.Error("page has no matching collection config", "page", page.RelPath, "collection", page.Collection)
    return
}
```

---

## High-Severity Issues

### H1 — XSS: Unescaped Tag Name in href Attribute

**File:** `internal/obsidian/markdown/transformer.go:47-52`

```go
return fmt.Sprintf(
    `%s<span class="inline-tag"><a href="/tags/%s">%s</a></span>`,
    separator,
    tagName,   // NOT escaped
    fullTag,
)
```

A crafted tag like `#test"onclick="alert(1)` would produce:
```html
<a href="/tags/test"onclick="alert(1)">...</a>
```

This breaks out of the href attribute and injects an event handler.

**Note:** The callout *title* was properly escaped in Step 1.5, but the tag href was missed.

**Fix:** `html.EscapeString(tagName)` or better, `url.PathEscape(tagName)`.

---

### H2 — XSS: Unescaped Callout Type in data-callout Attribute

**File:** `internal/obsidian/markdown/transformer.go:135, 142`

```go
sb.WriteString(`<details class="callout" data-callout="` + cType + `"`)
// ...
sb.WriteString(`<div class="callout" data-callout="` + cType + `">`)
```

The callout *title* is properly escaped on line 148 (`html.EscapeString(cTitle)`), but `cType` is injected raw into the `data-callout` attribute. A callout like `> [!test"><img src=x onerror=alert(1)>] Title` would inject HTML.

**Fix:** `html.EscapeString(cType)`.

---

### H3 — Global Mutable State Persists Despite BuildContext

**File:** `internal/builder/builder.go:76-110`

The `BuildContext` struct was introduced (Step 3.1) and `Build()`/`IncrementalBuild()` accept it, but `applyBuildContext()` still copies every field into package-level global variables:

```go
func applyBuildContext(ctx BuildContext) {
    OutputDir = ctx.OutputDir
    InputDir = ctx.InputDir
    // ... 12 more globals
}
```

These globals are read throughout `buildDefault`, `buildCustom`, and utility functions. This means:
- **No concurrent builds** — two `Build()` calls would race on globals
- **Test pollution** — tests that call `Build()` modify shared state
- **The refactoring is incomplete** — `BuildContext` exists but isn't threaded through

The globals and `applyBuildContext` should be removed; `BuildContext` (or a derived struct) should be passed to all functions that currently read globals.

---

### H4 — 11 os.Exit() Calls in buildCustom Make It Untestable

**File:** `internal/builder/builder_custom.go:477-565`

`buildCustom()` calls `os.Exit(1)` on every error (11 times), while `buildDefault()` uses an `ErrorCollector` pattern. This means:
- Custom mode **cannot be integration-tested** without exiting the test process
- Errors **cannot be recovered from** — partial builds are impossible
- The CLI can never provide a graceful "build failed, here's what went wrong" summary

Each `os.Exit(1)` should be replaced with error returns, matching `buildDefault`'s pattern.

---

### H5 — Font Loading Returns Nil, Causes Downstream Panic

**File:** `internal/builder/themes.go:417-450`

`LoadFontFace()` returns `nil` on error (lines 429, 436, 446) rather than propagating the error. The nil `font.Face` is stored in `DefaultSite.OGFontFace` (builder_default.go:82) and later used for OG image generation, which will panic on nil dereference.

**Fix:** Return `(font.Face, error)` and handle the error in the caller (skip OG image generation if font is unavailable).

---

### H6 — Silent Font Extraction Failures

**File:** `internal/builder/themes.go:461-477`

Font extraction to the output directory logs errors but continues execution:
```go
if err := os.MkdirAll(fontsDir, 0755); err != nil {
    log.Error("Failed to create fonts directory", "error", err)
    // continues — writes to non-existent directory
}
```

The build silently produces a site with missing or zero-byte font files.

---

### H7 — Duplicate Slugify Implementations (Inconsistent Behavior)

**Files:**
- `internal/obsidian/paths.go:17-25` — Exported `Slugify()` with regex sanitization
- `internal/obsidian/markdown/wikilinks.go:644-648` — Unexported `slugify()` without sanitization

The wikilinks version only lowercases and replaces spaces. The paths version also strips unsafe URL characters via regex. This means wikilink-generated URLs can contain characters that page URLs don't, causing broken links.

**Fix:** Delete the wikilinks copy and import the canonical version.

---

### H8 — link_preview.js Sets innerHTML from Fetched HTML (IGNORE)

**File:** `assets/link_preview.js:119`

```javascript
tooltip.innerHTML = content;
```

`content` is raw HTML fetched from another page via `fetch()`. If a previewed page contains malicious scripts (e.g., from user-generated content in the vault), they execute in the context of the current page.

**Fix:** Use a DOMParser and sanitize, or use a sandboxed iframe.

---

## Medium-Severity Issues

### M1 — notFoundRecorder Doesn't Implement http.Flusher

**File:** `internal/server/server.go:120-138`

The `notFoundRecorder` type wraps `http.ResponseWriter` but doesn't forward optional interfaces (`http.Flusher`, `http.Hijacker`). If the file server or any middleware attempts to call `w.(http.Flusher)`, the type assertion fails. This isn't currently triggered in the server flow, but it's fragile.

---

### M2 — SSE Event Drops Are Silent to Clients

**File:** `internal/overlay/events.go:26-31`

When a subscriber's channel buffer (8 entries) is full, events are dropped and counted (`atomic.AddInt64(&b.dropped, 1)`) but the client has no way to know it missed updates. The overlay UI may show stale content after rapid rebuilds.

**Consider:** Sending a "stale" event after detecting drops, or using `DroppedCount()` to log a warning.

---

### M3 — Missing X-Forwarded-Host in Reverse Proxy

**File:** `internal/proxy/reverse.go:22-40`

The proxy sets `X-Forwarded-For` and `X-Forwarded-Proto` but not `X-Forwarded-Host`. The backend can't reconstruct the original request URL for redirects or CORS.

---

### M4 — Injection Middleware Buffers Entire Response Body

**File:** `internal/overlay/inject.go`

The injection middleware reads the entire response body into memory to check for `</head>` and inject overlay tags. For large HTML files, this could consume significant memory. No size limit is enforced on the buffered body.

---

### M5 — Unchecked Type Assertions in Agent Tool Execution

**File:** `internal/ops/agent.go:498-528`

```go
path, _ := input["path"].(string)
content, _ := input["content"].(string)
pattern, _ := input["pattern"].(string)
```

If the LLM sends incorrect types (e.g., an integer for `path`), the assertion silently returns the zero value. For `write_file`, this means writing empty content to an empty path.

**Fix:** Check the `ok` flag and return descriptive errors.

---

### M6 — Rebuild Event Sent Even When Build Fails

**File:** `internal/cli/dev.go:160`

```go
eventBroker.Publish(`{"type":"rebuilt"}`)
```

This event is published regardless of whether the build encountered errors. The overlay UI assumes the page is up-to-date when it may not be.

---

### M7 — Linter WalkDir Return Value Ignored

**File:** `internal/linter/linter.go:81`

`filepath.WalkDir()` return value is discarded. The function returns an `int` (issue count) but cannot distinguish between "0 issues found" and "walk failed".

---

### M8 — linter.go filepath.Rel Errors Ignored

**File:** `internal/linter/linter.go:31, 97`

```go
rel, _ := filepath.Rel(inputDir, path)
```

If `filepath.Rel` fails, `rel` is empty, producing incorrect map keys and broken link reports.

---

### M9 — Config Reflection Lookup Is O(n) Per Field

**File:** `internal/config/config.go:82-89`

`ValueOr()` iterates all struct fields via reflection to find a matching yaml tag. With ~15 config fields and multiple lookups per build, this is unnecessarily slow. A `map[string]int` built once at init time would make lookups O(1).

---

### M10 — Simple Layout Missing Scroll Debounce

**File:** `assets/simple_app.js:378-384`

The back-to-top scroll handler fires on every scroll event without `requestAnimationFrame` throttling. The default layout (`default_app.js:464-478`) properly uses a `scrollTicking` flag. This inconsistency likely comes from the massive code duplication.

---

### M11 — Canvas mousemove Not Throttled

**File:** `assets/canvas.js:537-538`

```javascript
window.addEventListener("mousemove", this.handleMouseMove);
```

Mouse move events fire hundreds of times per second. No `requestAnimationFrame` throttling is applied, causing unnecessary DOM updates and potential jank.

---

### M12 — search.js Missing Fetch Error Handler

**File:** `assets/search.js:14-15`

```javascript
return fetch(BASE_URL + "/search-index.json")
    .then(function (r) { return r.json(); })
```

No `.catch()` handler. If the fetch fails or JSON parsing fails, the promise rejects silently.

---

### M13 — link_preview.js Scroll Handler Not Throttled

**File:** `assets/link_preview.js:186`

```javascript
window.addEventListener("scroll", onScroll, true);
```

`positionTooltip()` is called on every scroll event without throttling.

---

## Low-Severity Issues

### L1 — Massive JS Duplication Between Layout Files

**Files:**
- `assets/default_app.js` (545 lines)
- `assets/simple_app.js` (437 lines)

~80% of the code is duplicated: `loadScript()`, `initMathJax()`, `initMermaid()`, `changeGiscusTheme()`, `initThemeToggle()`, `addCopyButtons()`, `initCanvasMode()`, `initLightbox()`, `initNavFolderAnimation()`, `initBackToTop()`, and the Giscus event listener.

This duplication is the root cause of M10 — fixes applied to one layout are missed in the other.

**Fix:** Extract shared functions into a `shared_app.js` with layout-specific parameterization.

---

### L2 — CSS Scrollbar Rules Duplicated 5+ Times

**File:** `assets/shared.css` — lines 16-37, 39-46, 48-55, 963-976, 1074-1087

The same scrollbar styling pattern is repeated for each scrollable container. A shared `.custom-scrollbar` class would eliminate the duplication.

---

### L3 — Search Modal Missing ARIA Attributes

**File:** `assets/search.js:110-124`

The search overlay has no `aria-modal`, `aria-label`, or `role="dialog"`. The input has only a placeholder, no `aria-label`. Results container has no `role="listbox"`.

---

### L4 — Graph Overlay Missing Focus Trap

**File:** `assets/default_app.js:252-284`

The graph overlay modal has no focus trap, `aria-modal`, or keyboard dismiss. Only the close button has `aria-label`.

---

### L5 — Hardcoded Magic Numbers in JS

Multiple files use unexplained numeric constants:
- `default_app.js:472` — scroll threshold `300`
- `default_app.js:194, 212` — breakpoint `1280`
- `search.js:255` — debounce delay `120` (should be a named constant)
- `canvas.js:433` — zoom bounds `0.1` and `5`
- `graph.js:236-238` — force simulation parameters

---

### L6 — Canvas Commented-Out Code

**File:** `assets/canvas.js:252-253`

```javascript
// el.innerHTML = `<a href="${nodeData.url}" target="_blank"...`;
// break;
```

Dead code that should be removed.

---

### L7 — Clipboard Write Error Silently Swallowed

**File:** `assets/default_app.js:365`

```javascript
.catch((err) => {});
```

Clipboard write failures are ignored without any user feedback.

---

### L8 — imgopt os.Remove Error Ignored

**File:** `internal/imgopt/imgopt.go:264`

```go
os.Remove(path)  // error ignored
```

Minor — temp file cleanup failure isn't critical, but should be explicitly `_ = os.Remove(path)` for clarity.

---

### L9 — kiln-palette Unchecked Reflection Field Access

**File:** `cmd/kiln-palette/main.go:131, 148`

```go
hexLight := v.FieldByName(fieldName).String()
```

`FieldByName` on a non-existent field returns a zero `Value`. If the theme struct fields are renamed, this panics at runtime.

---

### L10 — graph.js MutationObserver Not Debounced

**File:** `assets/graph.js:49-72`

Theme observer calls `initGraph()` on every mutation without debouncing, potentially triggering multiple graph fetches and re-renders.

---

## Test Coverage Analysis

**Overall: 28.7%**

| Package | Coverage | Assessment |
|---------|----------|------------|
| `fileext` | 100.0% | Excellent |
| `i18n` | 100.0% | Excellent |
| `overlay` | 93.2% | Excellent |
| `search` | 93.1% | Excellent |
| `jsonld` | 92.3% | Excellent |
| `proxy` | 90.0% | Good |
| `rss` | 87.5% | Good |
| `watch` | 86.7% | Good |
| `ogimage` | 86.0% | Good |
| `config` | 83.7% | Good |
| `imgopt` | 83.1% | Good |
| `linter` | 83.3% | Good |
| `obsidian/markdown` | 60.1% | Fair |
| `ops` | 58.6% | Fair |
| `server` | 39.3% | Needs work |
| `builder` | 29.3% | Needs work |
| `cli` | 27.1% | Needs work |
| `obsidian` | 16.7% | Poor |
| `templates` | 11.3% | Poor |
| `obsidian/bases` | 5.9% | Poor |
| `cmd/forge` | 0.0% | None |
| `cmd/kiln-palette` | 0.0% | None |

### Key Coverage Gaps

1. **obsidian/bases (5.9%)** — The database view engine (filtering, grouping, sorting) is almost entirely untested. This is a complex subsystem with type coercion, operator evaluation, and recursive structures.

2. **obsidian (16.7%)** — Vault scanning, file processing, frontmatter parsing, backlink generation, navbar construction — all critical paths with minimal coverage.

3. **templates (11.3%)** — Template rendering logic is largely untested.

4. **builder (29.3%)** — Custom mode is effectively untestable due to os.Exit calls (H4). Default mode integration tests exist but don't cover many code paths.

5. **server (39.3%)** — Path traversal (C2) and clean URL edge cases are not covered by tests.

### Recommended Test Priorities

1. **obsidian/bases** — Table-driven tests for `FilterFiles`, `GroupFiles`, `SortFiles`, `InFolder`, type coercion functions
2. **obsidian** — `Scan()` on synthetic vaults, `processMarkdown()` link extraction, backlink generation
3. **server** — Path traversal attempts, clean URL resolution, 404 handling
4. **builder** — Fix os.Exit first (H4), then add custom mode integration tests

---

## Architecture Assessment

### What's Working Well

1. **BuildContext introduction** — The struct exists and is passed to `Build()`/`IncrementalBuild()`. This is the right direction even though globals persist.

2. **ErrorCollector pattern** — `buildDefault()` properly collects errors and reports them at the end. Much better than the previous silent-fail approach.

3. **writeTemplate helper** — Extracted from 9 duplicated blocks, eliminates nil panic risk.

4. **Field handler map** — `validateFrontmatterField` now uses a `map[FieldType]fieldHandler` dispatch instead of a 174-line switch. Each handler is focused and testable.

5. **Circular embed protection** — Depth limit + visited set properly prevents infinite recursion.

6. **HTTP client reuse** — Single `defaultAgentClient` with connection pooling, proper timeouts.

7. **Request body size limits** — `http.MaxBytesReader` properly applied to the ops handler.

8. **Watcher debounce** — Clean timer-based implementation with proper drain logic.

9. **Dependency graph cycle detection** — Visited set prevents infinite expansion.

### What Needs Attention

1. **Global state removal** — The `applyBuildContext()` shim should be eliminated. All functions should accept `BuildContext` (or a subset) as parameters. This is the single largest architectural debt.

2. **Custom mode error handling** — `buildCustom()` needs the same `ErrorCollector` treatment that `buildDefault()` received. The 11 `os.Exit` calls are the main barrier to testability.

3. **JS deduplication** — The ~80% overlap between `default_app.js` and `simple_app.js` is a maintenance hazard. Fixes in one file are routinely missed in the other (evidence: M10).

4. **HTML generation safety** — Several string-concatenation sites still lack escaping (H1, H2). A systematic audit of all `fmt.Sprintf` and `WriteString` calls that produce HTML would catch remaining gaps.

---

## Previously Fixed Issues

The following issues from the prior review have been addressed:

| Step | Issue | Status |
|------|-------|--------|
| 1.1 | Dead code after log.Fatal | Fixed |
| 1.3 | CleanOutputDir dangerous path guard | Fixed (`utils.go:48-77`) |
| 1.4 | writeTemplate helper (nil panic) | Fixed |
| 1.5 | HTML escaping (callout title, mermaid, TOC, broken embed) | Fixed (partial — H1, H2 remain) |
| 2.1 | Wikilink path matching too loose | Fixed (`HasSuffix`) |
| 2.2 | Vault rescan error propagation | Fixed |
| 2.3 | Glob matching vault-relative paths | Fixed |
| 2.4 | HTTP client reuse | Fixed |
| 2.5 | SSE drop counter | Fixed |
| 2.6 | Request body size limit | Fixed |
| 2.7 | Circular embed detection | Fixed |
| 2.8 | Content-Length after injection | Fixed |
| 2.9 | Field handler extraction | Fixed |
| 2.10 | Sitemap XML escaping | Fixed |
| 2.11 | buildDefault god function split | Fixed |
| 2.12 | Navbar orphan file warning | Fixed |
| 3.1 | BuildContext struct | Fixed (but globals remain — H3) |
| 4.1-4.4 | ErrorCollector, silent errors | Fixed (default mode only) |
| 5.1-5.15 | Medium fixes (config reflection, case sensitivity, slugify, RSS, etc.) | Fixed |
| 7.2 | Remove legacy old_app.js/old_style.css | Fixed |
| 7.3-7.6 | Modal focus trap, toast a11y, form validation, search debounce | Fixed |
| 7.7 | Canvas HTML sanitization | Fixed |
| 8.1-8.12 | Polish items | Fixed |

---

## Summary: Top 10 Action Items

| Priority | ID | Issue | Effort |
|----------|----|-------|--------|
| 1 | C1 | Fix SSE newline escape (live reload broken) | 1 line |
| 2 | C2 | Fix path traversal in clean URL handler | Small |
| 3 | H1 | Escape tag name in href attribute | 1 line |
| 4 | H2 | Escape callout type in data-callout attribute | 2 lines |
| 5 | C3 | Nil check on custom mode config lookup | Small |
| 6 | H4 | Replace os.Exit with error returns in buildCustom | Medium |
| 7 | H3 | Remove global variables, thread BuildContext through | Large |
| 8 | H7 | Remove duplicate slugify, use canonical version | Small |
| 9 | L1 | Extract shared JS functions from layout files | Medium |
| 10 | — | Expand test coverage for obsidian, bases, server | Large |
