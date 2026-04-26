# Forge Code Review

**Reviewer**: Claude
**Date**: 2026-04-05
**Scope**: All new and modified code in the Kiln → Forge fork
**Verdict**: **Ship with minor fixes** — the implementation is clean, well-tested, and architecturally sound. The issues below are real but none are blockers.

---

## Executive Summary

The fork adds ~400 lines of production Go code and ~500 lines of test code across three clean packages (`internal/overlay`, `internal/proxy`, `internal/server`), plus ~360 lines of frontend assets. All 26 new tests pass. `go vet` is clean. No new dependencies were added — everything uses the Go standard library.

The code follows the spec from `SIMPLIFIED_CONCEPT.md` faithfully. The handler chain routing, injection middleware, and reverse proxy are all implemented correctly. The main concerns are around robustness edge cases (memory on large responses, `http.DefaultServeMux` pollution, transport configuration) rather than correctness bugs.

---

## File-by-File Review

### `internal/overlay/inject.go` — HTML Injection Middleware

**Quality: Good**

Clean implementation. The response-recorder pattern, case-insensitive `</head>` search, and Content-Length stripping are all correct.

| # | Severity | Issue | Location |
|---|----------|-------|----------|
| 1 | **Medium** | **Full response buffering has no size limit.** The middleware buffers the entire response body into memory before scanning for `</head>`. A pathologically large HTML page (e.g., a vault with a single 50MB note) would be fully buffered. Consider adding a size cap — if the response exceeds some threshold (e.g., 10MB), pass it through without injection. | `inject.go:29-31` |
| 2 | **Low** | **`bytes.ToLower` copies the entire body.** `injectIntoHTML` lowercases the full body to find `</head>`. This doubles memory for every HTML response. A more efficient approach would be to scan for `</head>` with a case-insensitive byte search (e.g., scanning byte-by-byte or using `bytes.Index` on a sliding window). For the expected workload (sub-100KB HTML pages) this is fine, but worth noting. | `inject.go:53` |
| 3 | **Low** | **`headCloseBytes` is a package-level `var`, not `const`-like.** It's a `[]byte` so it can't be a `const`, but it could be mutated. Idiomatic Go would accept this as-is, but you could make it a function return or document it as effectively immutable. Very minor. | `inject.go:14` |
| 4 | **Info** | The `responseRecorder` does not implement `http.Flusher`, `http.Hijacker`, or `http.Pusher`. This is correct for the current use case (buffering is intentional), but means the injection middleware would break any handler that type-asserts the writer to these interfaces. Since it only wraps the Kiln file server (which doesn't use these), this is fine. Just be aware if you ever wrap handlers that use WebSockets or SSE through the injection path. | `inject.go:67-86` |

### `internal/overlay/static.go` — Static File Serving

**Quality: Good**

Minimal and correct. 16 lines, does exactly what's needed.

| # | Severity | Issue | Location |
|---|----------|-------|----------|
| 5 | **Info** | `NewStaticHandler` silently returns `nil` when the directory doesn't exist. The caller in `dev.go` doesn't log a warning if `--overlay-dir` is provided but the path is invalid. A user typo in `--overlay-dir` would silently result in 404s on `/ops/*` with no diagnostic. Consider either logging a warning at the call site or returning an error from this function. | `static.go:12` |

### `internal/proxy/reverse.go` — API Reverse Proxy

**Quality: Good with one notable issue**

| # | Severity | Issue | Location |
|---|----------|-------|----------|
| 6 | **Medium** | **Custom `http.Transport` discards all default settings.** The proxy creates a bare `&http.Transport{ResponseHeaderTimeout: timeout}` which loses all `http.DefaultTransport` settings: connection pooling limits (`MaxIdleConns`, `MaxIdleConnsPerHost`), TLS config, dial timeouts, keepalive settings, and proxy support. For a single-backend proxy this works, but connections won't be properly pooled and the dial timeout is zero (infinite). Consider cloning `http.DefaultTransport` and overriding just the timeout: | `reverse.go:28-30` |

```go
transport := http.DefaultTransport.(*http.Transport).Clone()
transport.ResponseHeaderTimeout = timeout
proxy.Transport = transport
```

| # | Severity | Issue | Location |
|---|----------|-------|----------|
| 7 | **Low** | **No `X-Forwarded-For` / `X-Forwarded-Proto` headers.** The proxy doesn't add standard forwarding headers. `httputil.ReverseProxy` adds `X-Forwarded-For` by default, but `X-Forwarded-Proto` and `X-Forwarded-Host` are not set. The agent doesn't currently use these, so this is a non-issue for MVP, but worth adding if the agent ever needs to construct absolute URLs or log client IPs. | `reverse.go:21-25` |
| 8 | **Low** | **Proxy error logging goes to `log.Printf` (default logger).** `httputil.ReverseProxy` logs errors (like backend connection failures) to the default Go logger, as visible in the test output: `2026/04/05 22:39:44 http: proxy error: dial tcp 127.0.0.1:19999: connect: connection refused`. Consider setting `proxy.ErrorLog` to use the structured slog logger for consistency with the rest of Forge. | `reverse.go:20` |
| 9 | **Info** | The `Director` function sets `req.Host = target.Host`. This is correct for proxying to `127.0.0.1:8081` but worth noting: it overwrites the original Host header. The agent doesn't care about Host, so this is fine. | `reverse.go:24` |

### `internal/server/mux.go` — Handler Chain Composition

**Quality: Excellent**

32 lines of clear, correct routing. The prefix matching order (`/api/` → `/ops/` → everything else) is right. The injection middleware wraps only the base handler, not the proxy or overlay handlers. This is exactly right.

| # | Severity | Issue | Location |
|---|----------|-------|----------|
| 10 | **Info** | `strings.HasPrefix(r.URL.Path, "/api/")` uses a simple string prefix match. This means a request to `/api` (no trailing slash) would NOT be proxied. This is probably correct (the agent expects `/api/apply`, `/api/undo`, `/api/health` — all with the slash), but a request to `/api` would fall through to the Kiln handler and likely 404. Consider whether `/api` (without slash) should redirect to `/api/` or return 404 explicitly. Very minor. | `mux.go:20` |

### `internal/server/server.go` — Dev Server Integration

**Quality: Good with one architectural concern**

| # | Severity | Issue | Location |
|---|----------|-------|----------|
| 11 | **Medium** | **Uses `http.DefaultServeMux` (the global mux).** `http.Handle(...)` and `http.HandleFunc(...)` register on `http.DefaultServeMux`, which is a package-level global. This means: (a) calling `Serve` twice in the same process would panic on duplicate route registration, (b) tests that call `Serve` would pollute global state. This is inherited from Kiln and not something Forge introduced, but since Forge adds integration tests that construct handlers separately (via `NewForgeHandler`), this hasn't caused test failures yet. If you ever need to test `Serve` directly, this would bite you. Consider creating a local `http.NewServeMux()` instead. | `server.go:71-82` |
| 12 | **Low** | `os.Exit(1)` is called on parse error and server failure. This is inherited Kiln behavior but makes the function untestable — you can't test the error paths without killing the test process. Not a Forge concern since this is pre-existing. | `server.go:21, 96` |

### `internal/cli/dev.go` — CLI Flag Registration & Wiring

**Quality: Good**

Clean integration. The new flags are registered consistently with the existing Kiln flags. The wiring in `runDev` is straightforward.

| # | Severity | Issue | Location |
|---|----------|-------|----------|
| 13 | **Low** | **No validation on `proxyTimeout`.** A user could pass `--proxy-timeout 0` or `--proxy-timeout -5` and get a zero or negative `time.Duration`. Consider clamping to a minimum (e.g., 10 seconds) or validating the input. | `dev.go:72, 188` |
| 14 | **Low** | **`proxyBackend` URL is not validated until proxy creation.** If the user passes `--proxy-backend not-a-url`, the error is logged but `runDev` just returns silently with no clear diagnostic. The user might not notice the log line among other startup output. | `dev.go:188-192` |
| 15 | **Info** | The new Forge flags (`--proxy-backend`, `--overlay-dir`, etc.) are not wired through `loadConfig`/`applyStringFlag` like the existing Kiln flags. This means they can't be set via `kiln.yaml`. This is probably intentional (Forge flags are orchestrator concerns), but worth documenting. | `dev.go:66-72, 77-92` |

### `static/ops.js` — Frontend Overlay

**Quality: Good**

Clean IIFE structure, proper DOM event handling, good error handling in fetch calls.

| # | Severity | Issue | Location |
|---|----------|-------|----------|
| 16 | **Medium** | **No handling of non-JSON error responses.** If the backend returns a non-JSON error (e.g., a 502 HTML page from the proxy, or a raw connection timeout), `resp.json()` will throw a SyntaxError. The `catch` block catches this, but the error message would be unhelpful: `"Request failed: Unexpected token '<' ..."`. Consider checking `resp.ok` or `resp.headers.get('content-type')` before parsing. | `ops.js:141` |
| 17 | **Low** | **No debounce on submit.** Double-clicking "Run" or hitting Ctrl+Enter rapidly could fire multiple concurrent requests. The `state.running` flag prevents UI interaction during a run, but the flag is set synchronously in `setRunning` which is called before `await fetch`, so this is actually fine — a second click during the fetch would be blocked by the disabled button. This is correct as-is. | Retracted — not an issue |
| 18 | **Low** | **Undo button visible in error state.** On error (`!result.ok`), the CSS shows `#ops-progress` (via `.ops-error #ops-progress { display: block }`) but does NOT show `#ops-actions`. This is correct — the undo button shouldn't appear on error. Good. | Retracted — not an issue |
| 19 | **Info** | **`closeModal` resets state on close.** If the user closes the modal after a successful operation (before refreshing), the summary/state is cleared. Reopening the modal starts fresh. This seems intentional and correct. | `ops.js:81-85` |

### `static/ops.css` — Frontend Styling

**Quality: Good**

Well-structured CSS with custom properties, responsive breakpoints, and clear state-based display toggling.

| # | Severity | Issue | Location |
|---|----------|-------|----------|
| 20 | **Low** | **CSS selector `#ops-modal-header` doesn't match the JS.** The CSS defines `#ops-modal-header` (line 62-66) but the JS creates the header div with `id="ops-header"` (ops.js line 26). The CSS rules for `#ops-modal-header` will never match. The header still works because flexbox defaults and the close button styles work independently, but the `justify-content: space-between` intended to separate the page context and close button is not being applied. | `ops.css:62-66` vs `ops.js:26` |
| 21 | **Info** | Hard-coded light-mode colors only. No `prefers-color-scheme: dark` support. Fine for MVP — the overlay sits on top of Kiln's themed content and a light modal is acceptable. | `ops.css:1-8` |

### `flake.nix` — Nix Build

| # | Severity | Issue | Location |
|---|----------|-------|----------|
| 22 | **Medium** | **Still references "kiln" throughout.** `pname = "kiln"`, `program = "...bin/kiln"`, `description = "otaleghani/kiln"`. The Nix build will produce a binary named `kiln`, not `forge`. Anyone building via `nix build` will get the wrong binary name. Needs to be updated to `forge`. | `flake.nix:2,16,41` |

### `build.sh` — Deployment Script

| # | Severity | Issue | Location |
|---|----------|-------|----------|
| 23 | **Low** | Still references Kiln's GitHub releases and downloads the Kiln binary. This script is for Cloudflare Pages deployment of the Kiln docs site — it's not relevant to Forge's operation. Either update it for Forge or delete it if Forge won't be deployed this way. | `build.sh:1-42` |

### `README.md` — Documentation

**Quality: Good**

Clear, concise, covers the new flags, usage examples, and architecture diagram.

| # | Severity | Issue | Location |
|---|----------|-------|----------|
| 24 | **Info** | No mention of the `--proxy-timeout` flag in the usage example with all flags enabled. The table lists it but the example doesn't demonstrate it. | `README.md:29-33` |

---

## Test Review

**Overall: Strong coverage, well-structured tests.**

All 26 tests pass. Tests are well-isolated using `t.TempDir()`, `httptest.NewServer`, and `httptest.NewRecorder`. No global state pollution between tests (the `Serve` function is tested indirectly via `NewForgeHandler`, avoiding the `http.DefaultServeMux` issue).

| # | Severity | Issue | Location |
|---|----------|-------|----------|
| 25 | **Low** | **Proxy "backend down" test logs to stderr.** `TestNewReverseProxy_BackendDown` produces a log line: `http: proxy error: dial tcp 127.0.0.1:19999: connect: connection refused`. This is noisy in test output but harmless. Could be silenced by setting `proxy.ErrorLog` to a discard logger in the test. | `reverse_test.go:82-95` |
| 26 | **Info** | **No test for concurrent requests.** The handler chain will be hit by concurrent browser requests in production. A test that fires e.g., 10 parallel requests through `NewForgeHandler` (mix of `/api/*`, `/ops/*`, and HTML requests) would verify thread safety. The implementation looks safe (no shared mutable state), but a test would confirm. | — |
| 27 | **Info** | **No test for the `--inject-overlay false` + `--overlay-dir set` case.** What happens when static assets are served at `/ops/*` but injection is disabled? The assets would be available but no HTML would reference them. This is a valid user configuration (they might inject manually). Tests cover each feature independently, which is sufficient. | — |

---

## Summary of Findings by Severity

### Must fix before shipping (0)

None. The code is correct and functional.

### Should fix soon (4 Medium)

| # | Summary | Effort |
|---|---------|--------|
| 1 | Add response body size limit to injection middleware | Small |
| 6 | Clone `http.DefaultTransport` instead of bare `http.Transport` | Trivial |
| 16 | Handle non-JSON error responses in `ops.js` | Small |
| 22 | Update `flake.nix` to reference "forge" instead of "kiln" | Trivial |

### Nice to have (9 Low)

| # | Summary |
|---|---------|
| 2 | Optimize case-insensitive `</head>` search to avoid full-body copy |
| 5 | Log warning when `--overlay-dir` path doesn't exist |
| 7 | Add `X-Forwarded-Proto` / `X-Forwarded-Host` headers |
| 8 | Route proxy error logging through slog |
| 13 | Validate `--proxy-timeout` minimum value |
| 14 | Improve diagnostic for invalid `--proxy-backend` URL |
| 20 | Fix CSS `#ops-modal-header` → `#ops-header` selector mismatch |
| 23 | Update or remove `build.sh` |
| 25 | Silence proxy error log in backend-down test |

### Informational (8)

Items 3, 4, 9, 10, 11, 12, 15, 19, 21, 24, 26, 27 — noted for awareness, no action needed.

---

## Architecture Assessment

The fork is well-executed:

- **Zero new dependencies** — all Forge code uses the Go stdlib.
- **Clean package boundaries** — `overlay`, `proxy`, and `server` don't import each other (except `server` → `overlay` for the middleware, which is appropriate).
- **Minimal Kiln modifications** — only `server.go` and `dev.go` were touched in Kiln's core code. The `Serve` function signature gained one parameter (`forgeCfg ForgeConfig`). This is the lightest possible integration.
- **Full backwards compatibility** — running `forge dev` without the new flags behaves identically to `kiln dev`. The `ForgeConfig` zero value disables all extensions.
- **Good test isolation** — tests use `httptest` throughout and avoid the global `http.DefaultServeMux`.
- **Frontend is clean** — the simplified `ops.js` (186 lines vs original 270) removes all SSE complexity and is straightforward synchronous fetch + DOM manipulation.
