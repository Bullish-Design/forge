# Review Refactoring Status

Source: `.scratch/projects/13-code-review/REVIEW_REFACTORING_GUIDE.md`
Assessed on: 2026-04-24
Method: repository code scan plus milestone validation evidence from `.scratch/projects/15-execution-queue-closure/PROGRESS.md`

Legend: `DONE` | `PARTIAL` | `TODO`

## Phase 1: Critical Bug Fixes

- `1.1` Remove Dead Code After `log.Fatal()` — `DONE`
  - Evidence: `cmd/forge/main.go` no longer has unreachable `os.Exit(1)`.
- `1.3` Guard `CleanOutputDir` Against Dangerous Paths — `DONE`
  - Evidence: `internal/builder/utils.go` now uses `CleanOutputDir(outputDir, log)` with empty/root/home/`.` safeguards and updated callers/tests.
- `1.4` Fix Panic on Nil File in Asset Writing — `DONE`
  - Evidence: `internal/builder/builder_default.go` uses `writeTemplate(...)` helper for asset writes.
- `1.5` Add HTML Escaping to String-Concatenated Output — `DONE`
  - Evidence: escaping present in `internal/obsidian/markdown/transformer.go`, `toc.go`, `wikilinks.go`.

## Phase 2: High-Severity Correctness Fixes

- `2.1` Fix Wikilink Path Matching (Too Loose) — `DONE`
  - Evidence: suffix/exact logic in `internal/obsidian/markdown/wikilinks.go`.
- `2.2` Propagate Vault Scan Errors in Dev Mode — `DONE`
  - Evidence: `return fmt.Errorf("rescan vault: %w", err)` in `internal/cli/dev.go`.
- `2.3` Fix `ops/tools.go` Glob to Match Full Path — `DONE`
  - Evidence: `filepath.Match(pattern, rel)` in `internal/ops/tools.go`.
- `2.4` Reuse HTTP Client in Agent — `DONE`
  - Evidence: `internal/ops/agent.go` now uses a shared reusable `defaultAgentClient`; model-resolution uses request-scoped timeout context.
- `2.5` Add Drop Counter to SSE Broker — `DONE`
  - Evidence: `internal/overlay/events.go` now tracks dropped publishes atomically and exposes `DroppedCount()`, with a buffer-overflow test.
- `2.6` Add Request Body Size Limit to `ops/handler.go` — `DONE`
  - Evidence: `handleApply` now wraps body with `http.MaxBytesReader` and returns `413` for oversized payloads; covered by `internal/ops/handler_test.go`.
- `2.7` Add Circular Embed Detection — `DONE`
  - Evidence: `internal/obsidian/markdown/wikilinks.go` now enforces embed depth and circular-embed detection; guard logic is covered by tests in `wikilinks_test.go`.
- `2.8` Fix Content-Length After Overlay Injection — `DONE`
  - Evidence: middleware now sets recalculated `Content-Length` after injection in `internal/overlay/inject.go` with test coverage.
- `2.9` `validateFrontmatterField`: Extract Type Handlers — `DONE`
  - Evidence: `internal/builder/builder_custom.go` now dispatches via `fieldHandlers` map with extracted per-type handler functions.
- `2.10` Fix Sitemap XML Escaping — `DONE`
  - Evidence: sitemap generation now checks/returns XML marshal errors, with tests asserting escaped output for `&` and `< >`.
- `2.11` Fix `buildDefault()` God Function — `DONE`
  - Evidence: `internal/builder/builder_default.go` now uses a short orchestrator and extracted helpers (`categorizeFiles`, `copyStaticAssets`, `renderAllPages`, `buildSearchIndex`, `writeAssets`, `writeMetaFiles`).
- `2.12` Fix Orphaned File Handling in Navbar — `DONE`
  - Evidence: orphaned navbar files are now surfaced at warning level and collision behavior is documented in `internal/obsidian/navbar.go`.

## Phase 3: Architectural Refactoring — Builder

- `3.1` Define `BuildContext` Struct — `DONE`
  - Evidence: `internal/builder/builder.go` now defines `BuildContext` with all build config fields plus logger.
- `3.2` Update `Build()` and `IncrementalBuild()` Signatures — `DONE`
  - Evidence: `internal/builder/builder.go` now accepts `BuildContext` for both `Build` and `IncrementalBuild`.
- `3.3` Update CLI Callers — `DONE`
  - Evidence: `internal/cli/generate.go` and `internal/cli/dev.go` now construct/pass `BuildContext`; clean/init/stats pass explicit paths.
- `3.4` Thread `BuildContext` Into `buildDefault` and `buildCustom` — `DONE`
  - Evidence: `internal/builder/builder_default.go` (`func buildDefault(ctx BuildContext, ...)`) and `internal/builder/builder_custom.go` (`func buildCustom(ctx BuildContext) error`) now accept build context directly.
- `3.5` Remove Global Variables — `DONE`
  - Evidence: package-level builder globals were removed; builder/CLI callers now use explicit context and command-local resolved values.
- `3.6` Update `CleanOutputDir`, `Init`, `Stats` Signatures — `DONE`
  - Evidence: `Init(inputDir, log)` and `Stats(inputDir, log)` now use explicit parameters; callers updated.

## Phase 4: Architectural Refactoring — Error Handling

- `4.1` Create `ErrorCollector` Utility — `DONE`
  - Evidence: new `internal/builder/errors.go` provides thread-safe add/list/summary helpers with tests in `errors_test.go`.
- `4.2` Use `ErrorCollector` in `buildDefault` — `DONE`
  - Evidence: `buildDefault` now aggregates render/write/meta failures and prints an end-of-build summary count.
- `4.3` Fix Silent Errors in Supporting Packages — `DONE`
  - Evidence: addressed silent error paths across builder stats, linter file reads, JSON response encoding, and JSON-LD generation signatures/callers.
- `4.4` Fix `linter.BrokenLinks` to Return Error Count — `DONE`
  - Evidence: `CollectNotes` now returns `(map,error)` and `BrokenLinks` returns issue count; doctor and tests updated to handle the new signatures.

## Phase 5: Medium-Severity Fixes

- `5.1` Config: Replace Hardcoded Switches with Reflection — `DONE`
  - Evidence: `internal/config/config.go` now resolves `ValueOr` and `BoolOr` via YAML-tag reflection rather than hardcoded switches.
- `5.2` Fix Case Sensitivity Inconsistencies — `DONE`
  - Evidence: `InFolder` now uses case-insensitive equality/prefix matching and file-name lookup case-sensitivity convention is documented in `internal/obsidian/obsidian.go`.
- `5.3` Improve Slugify — `DONE`
  - Evidence: `internal/obsidian/paths.go` now strips unsafe URL characters and collapses repeated dashes; behavior covered by `internal/obsidian/paths_test.go`.
- `5.4` Fix FlatURLs Comment Mismatch — `DONE`
  - Evidence: corrected FlatURLs comment in `internal/obsidian/paths.go` to match actual behavior.
- `5.5` Make RSS Entry Limit Configurable — `DONE`
  - Evidence: `GenerateRSS(maxEntries int)` now accepts a caller-provided limit with default fallback behavior.
- `5.6` Move Theme Definitions to Embedded YAML — `DONE`
  - Evidence: theme catalog now loads from embedded `themes.yaml` in `internal/builder/themes.go` via `//go:embed themes.yaml` and parsing helpers.
- `5.7` Add Cycle Detection to Dependency Graph — `DONE`
  - Evidence: `internal/watch/changeset.go` now recursively expands dependents with visited-node guards; cycle termination covered by `changeset_test.go`.
- `5.8` Make Watcher Debounce Configurable — `DONE`
  - Evidence: `Watcher.Debounce` plus `DefaultDebounce` in `internal/watch/watcher.go`.
- `5.9` Add X-Forwarded Headers to Reverse Proxy — `DONE`
  - Evidence: proxy director now sets `X-Forwarded-For` and `X-Forwarded-Proto`, with assertions in `internal/proxy/reverse_test.go`.
- `5.10` Fix `ops/agent.go` Silent Type Assertions — `DONE`
  - Evidence: agent loop now validates key assertion types (`stop_reason`, `content`, `tool_calls`, tool `function`) and logs/returns explicit errors on malformed payloads.
- `5.11` Standardize Logging on `slog` — `DONE`
  - Evidence: frontmatter parse warning now uses structured `slog` logging in `internal/obsidian/obsidian.go` instead of `fmt.Printf`.
- `5.12` Fix Dependency Graph Regex-Based Link Parsing — `DONE`
  - Evidence: markdown link extraction now strips fenced and inline code segments before regex parsing; tests ensure code-block links are ignored.
- `5.13` Fix Global CLI Flag Variables — `DONE`
  - Evidence: package-level CLI flag state removed; command-local resolution now uses `resolveStringFlag`/`resolveBoolFlag` and `getLogger(logLevel string)` in `internal/cli/commands.go`.
- `5.14` Fix Missing Error Check on `fmt.Sscanf` — `DONE`
  - Evidence: `cmd/kiln-palette/main.go` now checks parsed field count and errors for both 6-digit and 3-digit hex inputs.
- `5.15` Fix Server Shutdown Context — `DONE`
  - Evidence: `internal/server/server.go` now uses `context.WithTimeout(..., 5*time.Second)` for graceful shutdown.

## Phase 6: Test Coverage Expansion

- `6.1` Builder Integration Test (Golden File) — `DONE`
  - Evidence: `internal/builder/builder_integration_test.go` now validates core build artifacts for a temp vault build.
- `6.2` Custom Mode Field Validation Tests — `DONE`
  - Evidence: `internal/builder/field_handlers_test.go` adds table-style validation coverage for core field handlers and reference collection checks.
- `6.3` CLI Smoke Tests — `DONE`
  - Evidence: `internal/cli/cli_test.go` verifies command registration and expected generate/dev flags.
- `6.4` `obsidian/bases` Package Tests — `DONE`
  - Evidence: added focused bases tests for case-insensitive `infolder` and truthiness behavior in `internal/obsidian/bases/bases_test.go`.
- `6.5` Obsidian Package Tests (Vault Scanning) — `DONE`
  - Evidence: added vault scanning extraction tests in `internal/obsidian/obsidian_links_test.go` and Unicode-tag coverage in `internal/obsidian/obsidian_tags_test.go`.
- `6.6` Server Package Tests — `DONE`
  - Evidence: `internal/server/server_test.go` now includes additional recorder behavior coverage (default-200 write path) alongside existing 404/recorder tests.
- `6.7` Markdown Transformer Tests — `DONE`
  - Evidence: transformer tests now cover escaping, highlight edge-cases, and Unicode tag transformations in `internal/obsidian/markdown/transformer_test.go`.
- `6.8` Frontend Test Expansion — `DONE`
  - Evidence: added `static/src/__tests__/events.test.js`, `state.test.js`, and `page-context.test.js`; node test suite passes.

## Phase 7: JavaScript & CSS Cleanup

- `7.1` Extract Shared JS Functions — `DONE`
  - Evidence: shared JS extracted to `assets/shared_app.js`; `internal/builder/layouts.go` and `builder_default.go` now compose shared + layout JS into generated `app.js`.
- `7.2` Remove Legacy `old_app.js` and `old_style.css` — `DONE`
  - Evidence: removed unused `assets/old_app.js` and `assets/old_style.css`; no references remain and test suite passes.
- `7.3` Add Focus Trap and ESC Handler to Modal — `DONE`
  - Evidence: command modal now handles `Escape` close and traps tab focus within modal controls in `static/src/modes/command-mode.js`.
- `7.4` Add `aria-live` to Toast — `DONE`
  - Evidence: toasts now expose `role=status`, `aria-live=polite`, and `aria-atomic=true` in `static/src/ui/toast.js`.
- `7.5` Add Form Validation to `new-page-mode` — `DONE`
  - Evidence: new page flow now validates template selection and form validity, trims field values, and guards duplicate submits in `static/src/modes/new-page-mode.js`.
- `7.6` Add Debouncing to Search Input — `DONE`
  - Evidence: search input handling in `assets/search.js` now uses debounced query execution.
- `7.7` Sanitize `innerHTML` in `canvas.js` — `DONE`
  - Evidence: canvas rendering now sanitizes injected HTML and removes unsafe URL/event-attribute surfaces in `assets/canvas.js`.
- `7.8` Consolidate Duplicate CSS — `DONE`
  - Evidence: duplicated `body` rule removed from `assets/default_style.css`; shared typography/color rule remains in `assets/shared.css`.

## Phase 8: Low-Severity Polish

- `8.1` Replace Deprecated `strings.Title()` — `DONE`
  - Evidence: callout title fallback now uses local `titleCase()` helper in `internal/obsidian/markdown/transformer.go`.
- `8.2` Fix Highlight Regex Edge Case — `DONE`
  - Evidence: highlight transformer now supports inner `=` content via non-greedy matching, covered by `transformer_test.go`.
- `8.3` Fix Tag Regex to Support Unicode — `DONE`
  - Evidence: tag regexes in markdown transform and vault scan now use Unicode letter/number classes; covered by markdown and obsidian tag tests.
- `8.4` Consolidate Image Extension Lists — `DONE`
  - Evidence: image/static extension checks now share `internal/fileext` helpers and tests, replacing duplicate hardcoded lists.
- `8.5` Fix `bases.go` `InFolder` Case Sensitivity — `DONE`
  - Evidence: `infolder` evaluation now uses `strings.EqualFold` plus normalized lowercase prefix checks, covered by `internal/obsidian/bases/bases_test.go`.
- `8.6` Fix `bases.go` `isTrue` to Handle Truthy Values — `DONE`
  - Evidence: `internal/obsidian/bases/bases.go` now handles bool/int/int64/float64/string truthiness; coverage added in `bases_test.go`.
- `8.7` Add Backpressure Awareness to `imgopt` — `DONE`
  - Evidence: `ProcessImages` now uses worker-bounded job buffering and returns a per-path error map, with tests for both success and error cases.
- `8.8` Add Debouncing to Back-to-Top Button — `DONE`
  - Evidence: `assets/default_app.js` now uses a `scrollTicking` + `requestAnimationFrame` guard to throttle scroll-driven visibility updates.
- `8.9` Document FlatURLs Convention — `DONE`
  - Evidence: `docs/Features/Configuration File.md` now explains `flat-urls: true/false` output and URL behavior explicitly.
- `8.10` Clean Up Commented-Out Code — `DONE`
  - Evidence: removed obsolete commented code blocks from `internal/obsidian/bases/bases.go` and `internal/obsidian/markdown/wikilinks.go`.
- `8.11` Add Missing Encoder Handling in `imgopt` — `DONE`
  - Evidence: CLI now warns when `cwebp` or `avifenc` are missing before generate/dev builds via `warnMissingEncoders(...)`.
- `8.12` Make Command-Mode Reload Delay Configurable — `DONE`
  - Evidence: `static/src/modes/command-mode.js` now uses `RELOAD_DELAY_MS` constant instead of hardcoded value.

## Summary

- `DONE`: 70
- `PARTIAL`: 0
- `TODO`: 0

## Remaining Steps (Explicit)

- None. All tracked refactoring-guide steps are complete as of 2026-04-24.

## Open Questions / Deferrals

- No unresolved blockers remain in this tracker.
- Previously deferred implementation items were closed in project `15-execution-queue-closure` milestones M2-M4, with validation evidence logged in that project's `PROGRESS.md`.

Notes:
- Step numbering in the guide starts at `1.1`, `1.3`, `1.4`, `1.5` (no `1.2` heading present).
- This tracker is intentionally conservative: items are only marked `DONE` where the targeted behavior is clearly present in code.
