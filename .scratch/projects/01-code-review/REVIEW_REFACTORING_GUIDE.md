# Forge Code Review — Refactoring Guide

**Purpose**: Step-by-step instructions to fix all issues identified in `CODE_REVIEW.md`.
**Estimated scope**: ~13 fixes across 7 files. Each step is self-contained and testable.

---

## Prerequisites

```bash
cd /home/andrew/Documents/Projects/forge
go test ./...    # All 26 tests should pass before starting
go vet ./...     # Should be clean
```

Create a working branch:

```bash
git checkout -b fix/code-review-items
```

---

## Step 1: Fix CSS selector mismatch (Issue #20)

**File**: `static/ops.css`
**Problem**: CSS targets `#ops-modal-header` but the JS creates the element with `id="ops-header"`. The `justify-content: space-between` rule never applies, so the header's page-context and close button aren't properly spaced.

**Fix**: Change the CSS selector to match the JS.

In `static/ops.css`, line 62, change:

```css
#ops-modal-header {
```

to:

```css
#ops-header {
```

**Verification**:

1. Run `forge dev` with `--inject-overlay --overlay-dir ./static` on a test vault.
2. Open the browser, click the FAB, and inspect the modal header.
3. Confirm the page-context path text is on the left and the × close button is on the right (the `justify-content: space-between` rule is now applied).
4. Verify in DevTools that `#ops-header` has the flexbox styles.

---

## Step 2: Clone `http.DefaultTransport` instead of bare `http.Transport` (Issue #6)

**File**: `internal/proxy/reverse.go`
**Problem**: Creating a bare `&http.Transport{ResponseHeaderTimeout: timeout}` discards all default settings — connection pooling limits, TLS config, dial timeouts, keepalive, proxy support.

**Fix**: Replace lines 28–30 with:

```go
transport := http.DefaultTransport.(*http.Transport).Clone()
transport.ResponseHeaderTimeout = timeout
proxy.Transport = transport
```

The full function should look like:

```go
func NewReverseProxy(backendURL string, timeout time.Duration) (http.Handler, error) {
	if backendURL == "" {
		return nil, nil
	}

	target, err := url.Parse(backendURL)
	if err != nil {
		return nil, err
	}

	proxy := &httputil.ReverseProxy{
		Director: func(req *http.Request) {
			req.URL.Scheme = target.Scheme
			req.URL.Host = target.Host
			req.Host = target.Host
		},
	}

	transport := http.DefaultTransport.(*http.Transport).Clone()
	transport.ResponseHeaderTimeout = timeout
	proxy.Transport = transport

	return proxy, nil
}
```

**Verification**:

```bash
go build ./...
go test ./internal/proxy/...
```

All 7 proxy tests must pass. The behavior is identical from the outside — the change only affects internal transport settings.

---

## Step 3: Add response body size limit to injection middleware (Issue #1)

**File**: `internal/overlay/inject.go`
**Problem**: The middleware buffers the entire response body into memory. A pathologically large HTML page would consume unbounded memory.

**Fix**: Add a size cap constant and skip injection if the buffered response exceeds it.

```go
const maxInjectSize = 10 << 20 // 10 MB
```

Then in the `InjectMiddleware` handler function, after `body := rec.body.Bytes()`, add:

```go
body := rec.body.Bytes()
contentType := rec.header.Get("Content-Type")

if strings.Contains(contentType, "text/html") && len(body) <= maxInjectSize {
    body = injectIntoHTML(body)
}
```

This replaces the existing two-line block:

```go
// BEFORE (remove this):
if strings.Contains(contentType, "text/html") {
    body = injectIntoHTML(body)
}

// AFTER (replace with this):
if strings.Contains(contentType, "text/html") && len(body) <= maxInjectSize {
    body = injectIntoHTML(body)
}
```

**Add a test** in `internal/overlay/inject_test.go`:

```go
func TestInjectMiddleware_LargeBodySkipsInjection(t *testing.T) {
	// Create a body just over the 10MB limit
	largeBody := "<html><head></head><body>" + strings.Repeat("x", 10<<20) + "</body></html>"
	inner := htmlHandler(largeBody)
	handler := overlay.InjectMiddleware(inner, true)

	req := httptest.NewRequest("GET", "/", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if strings.Contains(rec.Body.String(), "ops-overlay") {
		t.Fatal("should skip injection for bodies over 10MB")
	}
}
```

**Note**: You'll need to export or document the `maxInjectSize` constant if you want the test to reference the exact threshold. The test above just creates a body that exceeds 10MB, which is sufficient.

**Verification**:

```bash
go test ./internal/overlay/... -v
```

The new test must pass alongside all existing injection tests.

---

## Step 4: Handle non-JSON error responses in `ops.js` (Issue #16)

**File**: `static/ops.js`
**Problem**: If the backend returns a non-JSON error (502 HTML page, connection timeout), `resp.json()` throws a `SyntaxError` with an unhelpful message.

**Fix**: Check `resp.ok` before parsing JSON. Update both `submitJob` and `submitUndo`.

In `submitJob`, replace lines 132–145:

```javascript
try {
    const resp = await fetch("/api/apply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            instruction: instruction,
            current_url_path: getCurrentUrlPath(),
        }),
    });
    if (!resp.ok) {
        setResult(els, { ok: false, error: "Server error: " + resp.status + " " + resp.statusText });
        return;
    }
    const result = await resp.json();
    setResult(els, result);
} catch (err) {
    setResult(els, { ok: false, error: "Request failed: " + err.message });
}
```

In `submitUndo`, replace lines 150–159:

```javascript
try {
    const resp = await fetch("/api/undo", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
    });
    if (!resp.ok) {
        setResult(els, { ok: false, error: "Server error: " + resp.status + " " + resp.statusText });
        return;
    }
    const result = await resp.json();
    setResult(els, result);
} catch (err) {
    setResult(els, { ok: false, error: "Undo failed: " + err.message });
}
```

**Verification**:

1. Run `forge dev` with a `--proxy-backend` pointing to a stopped backend.
2. Open the overlay, type an instruction, and click Run.
3. Confirm the error message says `"Server error: 502 Bad Gateway"` instead of `"Unexpected token '<'"`.
4. Also test with the backend running normally to confirm successful requests still work.

---

## Step 5: Update `flake.nix` references from "kiln" to "forge" (Issue #22)

**File**: `flake.nix`
**Problem**: The Nix build produces a binary named `kiln` instead of `forge`.

**Fix**: Three changes:

1. **Line 2** — Change `description`:
   ```nix
   description = "Bullish-Design/forge";
   ```

2. **Line 16** — Change `pname`:
   ```nix
   pname = "forge";
   ```

3. **Line 41** — Change binary path:
   ```nix
   program = "${self.packages.${system}.default}/bin/forge";
   ```

**Verification**:

If you have Nix installed:

```bash
nix build
ls result/bin/
# Should list "forge", not "kiln"
```

If Nix is not available, visually confirm the three changes are correct. The `vendorHash` may need updating after any dependency changes — follow the instructions in the comment at line 22–23.

---

## Step 6: Log warning when `--overlay-dir` path doesn't exist (Issue #5)

**File**: `internal/overlay/static.go`
**Problem**: `NewStaticHandler` silently returns `nil` for invalid paths. A typo in `--overlay-dir` would silently result in 404s with no diagnostic.

**Fix**: Change the function signature to accept a logger and log a warning.

```go
package overlay

import (
	"log/slog"
	"net/http"
	"os"
)

func NewStaticHandler(dir string, log *slog.Logger) http.Handler {
	if dir == "" {
		return nil
	}
	if info, err := os.Stat(dir); err != nil || !info.IsDir() {
		log.Warn("overlay-dir does not exist or is not a directory, overlay disabled", "path", dir)
		return nil
	}
	return http.StripPrefix("/ops/", http.FileServer(http.Dir(dir)))
}
```

**Update the call site** in `internal/cli/dev.go`, line 196:

```go
OverlayHandler: overlay.NewStaticHandler(overlayDir, log),
```

**Update the test** in `internal/overlay/static_test.go` to pass a logger. Use `slog.Default()` or create a discard logger:

```go
import "log/slog"

// In each test, update calls like:
overlay.NewStaticHandler(dir, slog.Default())
```

**Update the integration test** in `internal/server/forge_test.go`, line 40:

```go
import "log/slog"

overlayHandler := overlay.NewStaticHandler(overlayDir, slog.Default())
```

**Verification**:

```bash
go build ./...
go test ./...
```

Then manually test:

```bash
forge dev --overlay-dir /nonexistent/path --inject-overlay
# Should log: "overlay-dir does not exist or is not a directory, overlay disabled"
```

---

## Step 7: Validate `--proxy-timeout` minimum value (Issue #13)

**File**: `internal/cli/dev.go`
**Problem**: A user could pass `--proxy-timeout 0` or `--proxy-timeout -5` and get a zero or negative duration.

**Fix**: Add validation in `runDev` before using `proxyTimeout`. After line 92 (the last `applyStringFlag` call) and before line 94 (`builder.OutputDir = outputDir`), add:

```go
if proxyTimeout < 1 {
    log.Warn("proxy-timeout must be at least 1 second, using default of 180", "provided", proxyTimeout)
    proxyTimeout = 180
}
```

**Note**: This requires `log` to already be initialized. The `log := getLogger()` call is at line 109. You have two options:

**Option A** (simpler): Move the validation to after `log := getLogger()` on line 109, right before the proxy is created at line 188:

```go
log := getLogger()

if proxyTimeout < 1 {
    log.Warn("proxy-timeout must be at least 1 second, using default of 180", "provided", proxyTimeout)
    proxyTimeout = 180
}
```

**Option B**: Do the validation without logging, using a simple clamp:

```go
if proxyTimeout < 1 {
    proxyTimeout = 180
}
```

Option A is recommended since it informs the user.

**Verification**:

```bash
go build ./...
forge dev --proxy-timeout 0 --proxy-backend http://127.0.0.1:8081
# Should log warning and use 180s default
forge dev --proxy-timeout -5 --proxy-backend http://127.0.0.1:8081
# Should log warning and use 180s default
```

---

## Step 8: Improve diagnostic for invalid `--proxy-backend` URL (Issue #14)

**File**: `internal/cli/dev.go`
**Problem**: If the user passes `--proxy-backend not-a-url`, the error is logged but `runDev` returns silently with no clear diagnostic.

**Fix**: At lines 188–192, improve the log message and return clearly:

```go
proxyHandler, err := proxy.NewReverseProxy(proxyBackend, time.Duration(proxyTimeout)*time.Second)
if err != nil {
    log.Error("invalid --proxy-backend URL, cannot start server", "url", proxyBackend, "err", err)
    return
}
```

**Verification**:

```bash
go build ./...
forge dev --proxy-backend "not-a-url"
# Should show a clear error: "invalid --proxy-backend URL, cannot start server"
```

---

## Step 9: Route proxy error logging through slog (Issue #8)

**File**: `internal/proxy/reverse.go`
**Problem**: `httputil.ReverseProxy` logs errors (like backend connection failures) to Go's default logger, which is inconsistent with the rest of Forge using `slog`.

**Fix**: Add a `log/slog` logger parameter and set `proxy.ErrorLog`.

```go
package proxy

import (
	"log"
	"log/slog"
	"net/http"
	"net/http/httputil"
	"net/url"
	"time"
)

func NewReverseProxy(backendURL string, timeout time.Duration, logger *slog.Logger) (http.Handler, error) {
	if backendURL == "" {
		return nil, nil
	}

	target, err := url.Parse(backendURL)
	if err != nil {
		return nil, err
	}

	proxy := &httputil.ReverseProxy{
		Director: func(req *http.Request) {
			req.URL.Scheme = target.Scheme
			req.URL.Host = target.Host
			req.Host = target.Host
		},
		ErrorLog: log.New(slogWriter{logger}, "", 0),
	}

	transport := http.DefaultTransport.(*http.Transport).Clone()
	transport.ResponseHeaderTimeout = timeout
	proxy.Transport = transport

	return proxy, nil
}

// slogWriter adapts slog.Logger to io.Writer for use with log.Logger.
type slogWriter struct {
	logger *slog.Logger
}

func (w slogWriter) Write(p []byte) (int, error) {
	w.logger.Error(string(p))
	return len(p), nil
}
```

**Update the call site** in `internal/cli/dev.go`, line 188:

```go
proxyHandler, err := proxy.NewReverseProxy(proxyBackend, time.Duration(proxyTimeout)*time.Second, log)
```

**Update all test call sites** in `internal/proxy/reverse_test.go`:

```go
import "log/slog"

// Update every call to proxy.NewReverseProxy to add the logger:
handler, err := proxy.NewReverseProxy(backend.URL, 180*time.Second, slog.Default())
```

**Update** `internal/server/forge_test.go`, line 39:

```go
proxyHandler, _ := proxy.NewReverseProxy(backend.URL, 180*time.Second, slog.Default())
```

**Verification**:

```bash
go build ./...
go test ./...
```

All tests must pass. The backend-down test (`TestNewReverseProxy_BackendDown`) should now route its error through slog instead of printing raw log lines to stderr.

---

## Step 10: Silence proxy error log in backend-down test (Issue #25)

**File**: `internal/proxy/reverse_test.go`
**Problem**: `TestNewReverseProxy_BackendDown` produces noisy log output.

**Fix**: After Step 9, pass a discard logger in this specific test:

```go
func TestNewReverseProxy_BackendDown(t *testing.T) {
	discardLogger := slog.New(slog.NewTextHandler(io.Discard, nil))
	handler, err := proxy.NewReverseProxy("http://127.0.0.1:19999", 180*time.Second, discardLogger)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	req := httptest.NewRequest("GET", "/api/health", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != 502 {
		t.Fatalf("expected 502, got %d", rec.Code)
	}
}
```

You'll need to add `"io"` to the test file imports.

**Verification**:

```bash
go test ./internal/proxy/... -v 2>&1 | grep "proxy error"
# Should produce no output — the error is silenced in this test
```

---

## Step 11: Optimize case-insensitive `</head>` search (Issue #2)

**File**: `internal/overlay/inject.go`
**Problem**: `bytes.ToLower(body)` copies the entire body to find `</head>`, doubling memory for every HTML response.

**Fix**: Replace the `injectIntoHTML` function with a case-insensitive byte search:

```go
func injectIntoHTML(body []byte) []byte {
	idx := indexCaseInsensitive(body, headCloseBytes)
	if idx < 0 {
		return body
	}

	var buf bytes.Buffer
	buf.Grow(len(body) + len(injectionSnippet))
	buf.Write(body[:idx])
	buf.WriteString(injectionSnippet)
	buf.Write(body[idx:])
	return buf.Bytes()
}

// indexCaseInsensitive finds needle in haystack, case-insensitively.
// needle must be lowercase.
func indexCaseInsensitive(haystack, needle []byte) int {
	if len(needle) == 0 || len(haystack) < len(needle) {
		return -1
	}
	for i := 0; i <= len(haystack)-len(needle); i++ {
		match := true
		for j := 0; j < len(needle); j++ {
			c := haystack[i+j]
			if c >= 'A' && c <= 'Z' {
				c += 'a' - 'A'
			}
			if c != needle[j] {
				match = false
				break
			}
		}
		if match {
			return i
		}
	}
	return -1
}
```

**Verification**:

```bash
go test ./internal/overlay/... -v
```

All existing tests (including `TestInjectMiddleware_CaseInsensitiveHead`) must still pass. The behavior is identical — only the implementation changes.

---

## Step 12: Update or remove `build.sh` (Issue #23)

**File**: `build.sh`
**Problem**: Still references Kiln's GitHub releases and downloads the Kiln binary.

**Decision**: If Forge won't use Cloudflare Pages deployment, delete the file. If it will, update it.

**Option A — Delete**:

```bash
git rm build.sh
```

**Option B — Update** (replace file contents):

```bash
# Cloudflare Pages build script that downloads and runs forge. @feature:deploy
#!/bin/bash

INPUT_DIR="./docs"
SITE_NAME="Forge"
DEPLOYMENT_URL="https://forge.example.com"

set -e

echo "Forge build script"

LATEST_TAG=$(curl -s https://api.github.com/repos/Bullish-Design/forge/releases/latest | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/')

if [ -z "$LATEST_TAG" ]; then
  echo "Error: Could not determine latest Forge version."
  exit 1
fi

echo "Detected latest version: $LATEST_TAG"

URL="https://github.com/Bullish-Design/forge/releases/download/${LATEST_TAG}/forge_linux_amd64"

echo "Downloading binary from $URL..."
curl -L -o ./forge "$URL"
chmod +x ./forge

echo "Building site..."
./forge generate

echo "Forge build complete successfully"
```

**Verification**:

```bash
go build ./...   # build.sh is not Go code, just confirm nothing else broke
```

---

## Step 13: Add `X-Forwarded-Proto` / `X-Forwarded-Host` headers (Issue #7)

**File**: `internal/proxy/reverse.go`
**Problem**: The proxy doesn't set `X-Forwarded-Proto` or `X-Forwarded-Host`. `httputil.ReverseProxy` adds `X-Forwarded-For` automatically but not the others.

**Fix**: Add the headers in the `Director` function:

```go
Director: func(req *http.Request) {
    req.Header.Set("X-Forwarded-Host", req.Host)
    req.Header.Set("X-Forwarded-Proto", "http")
    req.URL.Scheme = target.Scheme
    req.URL.Host = target.Host
    req.Host = target.Host
},
```

Note: `X-Forwarded-Host` must be captured *before* `req.Host` is overwritten. The proto is always `"http"` since the dev server doesn't use TLS.

**Add a test** in `internal/proxy/reverse_test.go`:

```go
func TestNewReverseProxy_ForwardingHeaders(t *testing.T) {
	var gotHost, gotProto string
	backend := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotHost = r.Header.Get("X-Forwarded-Host")
		gotProto = r.Header.Get("X-Forwarded-Proto")
		w.WriteHeader(200)
	}))
	defer backend.Close()

	handler, _ := proxy.NewReverseProxy(backend.URL, 180*time.Second, slog.Default())
	req := httptest.NewRequest("GET", "/api/health", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if gotProto != "http" {
		t.Fatalf("expected X-Forwarded-Proto 'http', got %q", gotProto)
	}
	if gotHost == "" {
		t.Fatal("expected X-Forwarded-Host to be set")
	}
}
```

**Verification**:

```bash
go test ./internal/proxy/... -v
```

---

## Final Verification

After completing all steps:

```bash
go build ./...
go test ./... -v
go vet ./...
```

All tests must pass and `go vet` must be clean.

---

## Summary Checklist

| Step | Issue # | Severity | File(s) | Done |
|------|---------|----------|---------|------|
| 1 | #20 | Low | `static/ops.css` | [ ] |
| 2 | #6 | Medium | `internal/proxy/reverse.go` | [ ] |
| 3 | #1 | Medium | `internal/overlay/inject.go`, `inject_test.go` | [ ] |
| 4 | #16 | Medium | `static/ops.js` | [ ] |
| 5 | #22 | Medium | `flake.nix` | [ ] |
| 6 | #5 | Low | `internal/overlay/static.go`, `dev.go`, tests | [ ] |
| 7 | #13 | Low | `internal/cli/dev.go` | [ ] |
| 8 | #14 | Low | `internal/cli/dev.go` | [ ] |
| 9 | #8 | Low | `internal/proxy/reverse.go`, `dev.go`, tests | [ ] |
| 10 | #25 | Low | `internal/proxy/reverse_test.go` | [ ] |
| 11 | #2 | Low | `internal/overlay/inject.go` | [ ] |
| 12 | #23 | Low | `build.sh` | [ ] |
| 13 | #7 | Low | `internal/proxy/reverse.go`, `reverse_test.go` | [ ] |

**Ordering notes**: Steps 1–5 are the four medium issues plus one bug fix — do these first. Steps 9 and 10 are sequential (10 depends on 9). Step 2 must be done before Step 9 (both modify `reverse.go`). All other steps are independent and can be done in any order.
