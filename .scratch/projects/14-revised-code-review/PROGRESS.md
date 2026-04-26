# Code Review Fix Progress

**Review source:** `CODE_REVIEW.md` (commit `aec57cd`, branch `refactor/review-guide-no-phase3`)
**Fix branch:** `refactor/review-guide-no-phase3`

**Closure reconciliation (2026-04-24):**
- Remaining deferred/top-10 items in this historical tracker were completed in project `15-execution-queue-closure`:
  - H3 (`BuildContext` threading/global removal) -> M2 steps `3.4`/`3.5`
  - L1 (shared JS extraction) -> M4 step `7.1`
  - Test expansion item -> review guide Phase 6 completion
- This document remains as historical implementation notes; current closure source of truth is `.scratch/projects/13-code-review/REVIEW_REFACTORING_STATUS.md`.

---

## Completed

### C1 — SSE Newline Escape Bug (Live Reload Broken)
**Files:** `internal/overlay/events.go:72`, `internal/overlay/events_test.go:41`

`"data: %s\\n\\n"` was producing literal `\n` characters instead of actual newlines, violating the SSE spec. The browser's `EventSource` never received a complete event, breaking live reload entirely.

- Fixed format string from `\\n\\n` → `\n\n`
- Fixed test assertion from `strings.Contains(body, "data: ...")` to `strings.Contains(body, "data: ...\n\n")` — the old test matched the prefix regardless of newline format, masking the bug

---

### C2 — Path Traversal in Clean URL Handler
**Files:** `internal/server/server.go:45-66`, `internal/server/server_test.go`

`filepath.Join(outputDir, path+".html")` was called with unsanitized `r.URL.Path`. `filepath.Join` normalizes `..` components, so a path like `/../../../etc/passwd` could resolve outside the output directory. The `os.Stat` call on the resolved path leaked file existence information even before `http.ServeFile`'s own protections ran.

- Added `filepath.Abs` + `strings.HasPrefix(abs, outputDirClean)` boundary check before each `os.Stat` call
- Applied the same guard to both the `.html` path and the directory index path lookups
- Added `TestCleanURLHandler_PathTraversal` covering traversal attempts and confirming legitimate clean URLs still work

---

### C3 — Nil Pointer Dereference in Custom Mode Render
**File:** `internal/builder/builder_custom.go:436-439`

`s.ConfigsLookup[page.Collection]` returns `nil` when the key is absent (Go map zero-value). Accessing `.Template` or `.LayoutPath` on a nil pointer panicked. This can be triggered by any markdown file in custom mode that doesn't belong to a configured collection.

- Changed bare map index to two-value form (`config, ok := ...`)
- Returns a descriptive error (`fmt.Errorf`) rather than panicking, matching the error-return pattern used elsewhere in `render()`

---

---

### H1 — XSS: Unescaped Tag Name in href Attribute
**File:** `internal/obsidian/markdown/transformer.go:48-51`

`tagName` and `fullTag` were interpolated raw into the `<a href>` and link text. Applied `html.EscapeString` to both. Note: the tag regex `#[\p{L}\p{N}_\-]` inherently excludes `"`, `<`, `>`, and `&`, so this is defense-in-depth against future regex relaxation. Added `TestTransformTags_EscapesDisplayText` verifying normal output is unchanged.

---

### H2 — XSS: Unescaped Callout Type in data-callout Attribute
**File:** `internal/obsidian/markdown/transformer.go:135, 142`

`cType` was concatenated raw into `data-callout="..."` at two sites (collapsible `<details>` and static `<div>`). Applied `html.EscapeString(cType)` at both. The callout regex `[\w-]+` similarly constrains input, making this defense-in-depth. Added `TestTransformCallouts_EscapesTypeAttribute` verifying normal output.

---

---

### H4 — 11 os.Exit() Calls in buildCustom
**File:** `internal/builder/builder_custom.go`, `internal/builder/builder.go`

`buildCustom` called `os.Exit(1)` on every error (11 sites), making the function impossible to call in tests without terminating the test process. Changed the signature from `buildCustom(log) ` to `buildCustom(log) error`, replacing every `os.Exit(1)` with a wrapped `fmt.Errorf` return. `Build()` and `IncrementalBuild()` in `builder.go` now check the returned error and call `os.Exit(1)` in one consolidated place each, preserving production behavior while making `buildCustom` independently testable.

---

### H5 — LoadFontFace Returns nil, Masking Errors
**File:** `internal/builder/themes.go`, `internal/builder/builder_default.go`

`LoadFontFace` returned `nil` on three error paths with no way for the caller to distinguish success (nil is valid for an unused font) from failure. Changed the return type to `(font.Face, error)`, replacing all silent `return nil` paths with `return nil, fmt.Errorf(...)`. The caller in `builder_default.go` now logs a warning on error. Note: `ogimage` already has a nil fallback to `basicfont.Face7x13`, so OG image generation degrades gracefully rather than panicking.

---

## Remaining (from Top 10 Action Items)

| Priority | ID | Issue | Effort |
|----------|----|-------|--------|
| ~~3~~ | ~~H1~~ | ~~Escape tag name in href attribute~~ | Done |
| ~~4~~ | ~~H2~~ | ~~Escape callout type in data-callout attribute~~ | Done |
| ~~6~~ | ~~H4~~ | ~~Replace os.Exit with error returns in buildCustom~~ | Done |
| ~~7~~ | ~~H3~~ | ~~Remove global variables, thread BuildContext through~~ | Done (project 15 M2) |
| ~~8~~ | ~~H7~~ | ~~Remove duplicate slugify, use canonical version~~ | Done |
| ~~9~~ | ~~L1~~ | ~~Extract shared JS functions from layout files~~ | Done (project 15 M4) |
| ~~10~~ | ~~—~~ | ~~Expand test coverage for obsidian, bases, server~~ | Done (guide Phase 6) |

---

### H6 — Silent Font Extraction Failures
**File:** `internal/builder/themes.go` (`extractFonts`)

After a failed `os.MkdirAll`, the code logged an error but fell through into the font-writing loop, which would then write to a directory that doesn't exist (producing silent failures or writes to unexpected paths). Added `return` after the `MkdirAll` error so the entire extraction is skipped. Also added `continue` after each per-file read error (was missing) and added `"file"` to the log attributes so failures identify which font failed.

---

### H7 — Duplicate Slugify Implementations
**Files:** `internal/obsidian/markdown/wikilinks.go`, `internal/obsidian/paths.go`

`wikilinks.go` had a local unexported `slugify` that only lowercased and replaced spaces — it skipped the regex sanitization step in the canonical `obsidian.Slugify`. This meant wikilink-generated URLs could contain characters (e.g. `!`, `?`, `#`) that page URLs strip, causing broken links for notes with such characters in their names.

Deleted the local copy and replaced all four call sites (`lines 180, 193, 327, 501`) with `obsidian.Slugify`. The `obsidian` package was already imported.

---

---

### M11 — Canvas mousemove Not Throttled
**File:** `assets/canvas.js`

`handleMouseMove` was calling `updateTransform()` (which sets `element.style.transform`) on every raw `mousemove` event — potentially hundreds of times per second. Added a `_mouseTicking` flag and `_pendingMouseEvent` buffer to the instance. The handler now stores the latest event and schedules a single `requestAnimationFrame` callback if one isn't already pending; that callback applies the accumulated delta and resets the flag. This matches the pattern already used by `default_app.js`'s scroll handler (`scrollTicking`).

---

---

### M2 — SSE Event Drops Are Silent to Clients
**File:** `internal/overlay/events.go`, `internal/overlay/events_dropped_test.go`

When a subscriber's channel buffer (8 slots) was full, events were dropped and counted but the client received no signal that it had missed updates. In `Publish`, the `default` branch now: (1) drains the oldest pending event from the channel to make room, then (2) sends `{"type":"stale"}` to notify the client it missed updates and should reload. The dropped counter still increments. The channel remains full (8 items), so the existing count test still passes. Added `TestEventBroker_StaleNotificationSentOnDrop` verifying the stale message appears as the last item after an overflow.

---

### M3 — Missing X-Forwarded-Host in Reverse Proxy
**File:** `internal/proxy/reverse.go`, `internal/proxy/reverse_test.go`

The proxy Director set `X-Forwarded-For` and `X-Forwarded-Proto` but not `X-Forwarded-Host`. Without it, the backend cannot reconstruct the original request URL for redirects or CORS. Added `req.Header.Set("X-Forwarded-Host", req.Host)` before overwriting `req.Host` with the backend address. Added `TestNewReverseProxy_ForwardsHost` verifying the original host is preserved, and extended `TestNewReverseProxy_ForwardsRequest` to assert the header is non-empty.

---

## Other Open Issues (not in Top 10)

- H5/H6 — Font loading nil return + silent extraction failures (`themes.go`)
- H8 — `link_preview.js` sets `innerHTML` from fetched HTML (XSS)
- M1–M13 — Medium issues (notFoundRecorder interfaces, SSE drops, proxy headers, etc.)
- L2–L10 — Low-priority polish items
