# Dependency Library Review

## Scope

This review evaluates the two extracted Python dependencies intended to sit beneath the Forge architecture refactor:

- `obsidian-ops`: `/home/andrew/Documents/Projects/obsidian-ops`
- `obsidian-agent`: `/home/andrew/Documents/Projects/obsidian-agent`

The goal is not just to describe the libraries as they exist today, but to judge whether they are ready to become the stable dependency boundary underneath Forge, and to identify what needs to change before the Forge refactor should begin.

The review is grounded in:

- the refactor docs in `.scratch/projects/06-forge-architecture-refactor/`
- the current source code and tests in both repos
- the existing Go implementation in `forge/internal/ops`
- local test execution where possible

## Executive Summary

The split itself is correct.

`obsidian-ops` is already the right conceptual home for vault sandboxing, content operations, frontmatter handling, search, and Jujutsu-backed version control. `obsidian-agent` is already the right conceptual home for the LLM loop, HTTP API, provider selection, prompt construction, and tool dispatch. That dependency direction is materially better than the current Forge-internal `internal/ops` package.

The libraries are not yet fully ready to serve as the long-term hard boundary for Forge.

The main reason is not that the extraction failed. The extraction is directionally good. The issue is that a few important boundaries are still soft or inconsistent:

1. `obsidian-agent` still contains some version-control behavior that should live in `obsidian-ops`.
2. `obsidian-ops` does not yet implement the richer frontmatter and content patch semantics promised by the refactor docs.
3. packaging and local-dev ergonomics are inconsistent, especially around server dependencies and inter-repo versioning.
4. the caller contract between Forge and `obsidian-agent` is still underspecified around URL-to-file resolution.
5. the two repos have different test maturity levels: `obsidian-agent` is already in decent shape; `obsidian-ops` has strong core coverage but weaker environment packaging and server validation.

My recommendation is:

- treat both libraries as the correct base for the refactor,
- do not start the Forge extraction until the boundary-cleanup items in this document are addressed,
- prioritize `obsidian-ops` API hardening first, then align `obsidian-agent` to that API, and only then remove Forge's in-process Go backend.

## Validation Summary

### `obsidian-agent`

Local validation succeeded.

- Command run: `devenv shell -- pytest -q`
- Result: `109 passed in 15.24s`

This matters. It means the current agent package is testable and the baseline functionality is not speculative.

### `obsidian-ops`

The core library validated, but the full repo test run did not.

- Command run: `devenv shell -- pytest -q`
- Result: failed during test collection because `fastapi` was not installed
- Failing import: `tests/test_server.py` -> `ModuleNotFoundError: No module named 'fastapi'`

A narrower validation of the non-server suite did succeed:

- Command run: `devenv shell -- pytest -q tests/test_vault.py tests/test_frontmatter.py tests/test_content.py tests/test_search.py tests/test_lock.py tests/test_vcs.py tests/test_integration.py tests/test_smoke.py tests/test_sandbox.py`
- Result: passed

This is a packaging/environment problem, not evidence that the vault core is broken. It still matters, because a dependency library intended to anchor the refactor needs a reproducible development and test story.

## Target Architectural Fit

The refactor docs describe the intended shape clearly:

- Forge becomes the thin host: page serving, overlay injection, `/ops/*` assets, `/api/*` reverse proxy.
- `obsidian-agent` becomes the LLM-facing backend service.
- `obsidian-ops` becomes the vault interaction substrate that the agent imports and that other tools can also use independently.

Measured against that design, the current extraction is mostly correct:

- `obsidian-ops` is library-first and has no LLM dependency.
- `obsidian-agent` imports `obsidian_ops.Vault` rather than touching the vault directly.
- the old Go concerns in `forge/internal/ops` map cleanly into the two extracted repos.

That said, the split is not fully hardened yet. The main remaining work is about enforcing the boundary operationally, not redesigning it conceptually.

## Review: `obsidian-ops`

### What is already solid

#### 1. The core responsibility is correct

`obsidian-ops` owns the right layer:

- sandboxed file IO
- frontmatter parsing and serialization
- heading/block patch operations
- search and listing
- mutation locking
- Jujutsu wrappers
- an optional HTTP surface

That is the right dependency footprint for the lower-level library.

#### 2. The public shape is small and understandable

The `Vault` API is concise and practical. It is easy to see how `obsidian-agent` or a future CLI would consume it:

- `read_file`, `write_file`, `delete_file`
- `list_files`, `search_files`
- `get_frontmatter`, `set_frontmatter`, `update_frontmatter`, `delete_frontmatter_field`
- `read_heading`, `write_heading`, `read_block`, `write_block`
- `commit`, `undo`, `vcs_status`

This is the right level of abstraction. It is much better than asking each caller to stitch together filesystem operations, YAML parsing, sandboxing, and `jj` subprocesses itself.

#### 3. The safety defaults are good

The path validation and mutation-lock story is already strong enough to be useful as a shared primitive layer.

The implementation enforces:

- no absolute paths
- no traversal paths
- symlink-escape prevention
- serialized writes through a non-blocking mutation lock
- explicit file size limits on reads

That is exactly the sort of defensive surface Forge should stop owning directly.

#### 4. The core library tests are strong

The non-server test suite covers the important low-level behavior well:

- sandbox validation
- lock semantics
- frontmatter parsing
- heading/block patching
- Jujutsu command dispatch
- integration snapshots for vault operations

For the core library API, this is a good foundation.

### What is not ready yet

#### 1. Frontmatter patch semantics are shallower than the spec promises

The refactor docs describe `obsidian-ops` as the place where Forge can rely on targeted, Obsidian-aware patch operations rather than full-file rewrites. The current implementation does not fully meet that bar.

`update_frontmatter()` performs a shallow dict update:

- nested objects are replaced, not merged
- there is no field-path patch language
- there is no explicit delete-via-patch behavior
- there is no ordering-preservation strategy beyond `yaml.safe_dump(..., sort_keys=False)`

That is enough for simple key replacement, but it is not enough to serve as the durable editing primitive for more sophisticated Forge interactions.

This matters because once Forge is refactored around `obsidian-ops`, callers will start to treat the library API as the architectural contract. It is cheaper to harden this now than to change the tool contract later.

#### 2. Content patching is useful but still narrow

The heading and block operations are a good start, but they are still MVP-grade.

Current limitations:

- `write_block()` only replaces an existing located block and cannot create one.
- block matching is paragraph/list-item oriented and may not be sufficient for broader Obsidian structures.
- there is no higher-level patch result model describing whether content was inserted, replaced, or created.
- there is no explicit support for idempotent patch operations.

This is probably acceptable for the first extraction, but not yet ideal as the long-lived editing substrate.

#### 3. The library/server packaging contract is inconsistent

The package advertises a console script unconditionally:

- `obsidian-ops-server = "obsidian_ops.server:main"`

But the server module imports `fastapi` and `uvicorn` at import time, while those dependencies are only listed under the optional `server` extra.

That creates an avoidable footgun:

- install the package without extras
- run the shipped script
- crash on import

That is exactly the kind of packaging ambiguity that becomes expensive once the repo boundary is formalized.

The fix should be explicit and opinionated. Either:

- make the server dependencies mandatory because the script is part of the package contract, or
- move the console script behind the `server` extra and ensure importing the core package never requires FastAPI.

The current middle state is weak.

#### 4. The local dev/test environment is not aligned with the package contract

The repo contains server tests and a server entrypoint, but the default `devenv` does not provide `fastapi`, so the default test command fails at collection time.

That creates three separate truths:

- the package metadata says server support exists
- the test suite says server support matters
- the default local environment does not satisfy server support

That needs to be unified before this library is used as a foundational dependency.

#### 5. Some contract details are still ambiguous

There are a few smaller but important mismatches between prose/spec expectations and actual behavior:

- `list_files()` matches against the relative path via `fnmatch`, not just the filename.
- the server health endpoint returns `{"status": "ok"}` rather than the `{"ok": true, ...}` style used elsewhere.
- request/response models in the server are mostly untyped `dict` payloads rather than explicit Pydantic models.

None of these alone block the refactor. Together, they indicate the API still needs a contract-hardening pass.

### Required changes before the Forge refactor

#### Required

1. Implement deep frontmatter patch behavior.
   The API should support nested updates predictably. This can be done with nested dict merge semantics, dot-path updates, or both, but the contract must be explicit and tested.

2. Move toward explicit patch/result semantics for content operations.
   At minimum, heading/block writes should expose whether they created or replaced content. That will make agent behavior and future UI flows more reliable.

3. Fix server packaging.
   The installed script and dependency model must agree. There should be no path where the package looks server-capable but the default install is broken.

4. Fix the `devenv` test environment so the default test command can run the full repo suite.

5. Write a real `README`.
   Right now the repo-level documentation is effectively empty. That is not acceptable for a dependency library that is supposed to become part of the architecture boundary.

#### Strongly recommended

1. Add explicit request/response models in the FastAPI layer.
2. Standardize health responses with the rest of the stack.
3. Define and document the exact glob semantics for `list_files()` and `search_files()`.
4. Add one or two tests around malformed/non-UTF-8 file handling if binary or mixed-content vaults are expected.

## Review: `obsidian-agent`

### What is already solid

#### 1. The dependency direction is correct

This is the most important fact about the repo: `obsidian-agent` imports `obsidian_ops.Vault` and does not reimplement vault behavior itself.

That is the right boundary.

The agent owns:

- provider/model setup
- prompt construction
- tool registration
- the tool-calling loop
- HTTP endpoints
- operation timeout behavior
- request/response models

Those are exactly the concerns that should leave Forge.

#### 2. The extracted agent is far smaller and cleaner than the Go version

The old Go agent in `forge/internal/ops/agent.go` is 990 lines and contains a large amount of provider-specific and tool-call parsing complexity. The current Python agent is much smaller and clearer.

That is a meaningful architectural improvement, not just a language rewrite.

The current code is easier to reason about because:

- provider wiring is delegated to `pydantic-ai`
- tools are registered as normal Python functions
- the run loop is concise
- config and API models are straightforward

This gives the refactor a cleaner long-term maintenance story.

#### 3. The HTTP API aligns with the planned Forge MVP

`obsidian-agent` already exposes the right shape for the current simplified Forge contract:

- `POST /api/apply`
- `POST /api/undo`
- `GET /api/health`

That is enough to replace the in-process Go backend without requiring a simultaneous frontend redesign.

#### 4. The tests are materially better than the original extraction plan required

The repo already has:

- unit coverage for config, prompt, models, tools, app, and agent flow
- real retained filesystem artifacts under `tests/artifacts/`
- integration tests that initialize `jj`, apply edits, and undo them
- HTTP integration tests through FastAPI

That is a credible baseline for the repo to serve as a real dependency rather than an experiment.

### What is not ready yet

#### 1. The version-control boundary is not clean enough

This is the single most important issue in `obsidian-agent`.

The agent correctly delegates `commit()` and `undo()` to the `Vault` abstraction, but then it performs a raw subprocess call to `jj restore --from @-` itself during undo.

That means the version-control contract is split across both libraries:

- `obsidian-ops` owns some of the undo lifecycle
- `obsidian-agent` owns the rest

That weakens the repository boundary immediately.

If another client besides `obsidian-agent` uses `obsidian-ops`, it will not get the same undo semantics. That is exactly the kind of hidden behavior split this refactor is trying to eliminate.

The VCS lifecycle should be unified in `obsidian-ops`.

The simplest fix is to introduce a higher-level vault method, something like:

- `vault.undo_last_change()`
- or `vault.revert_last_mutation()`

That method should encapsulate every required `jj` step. `obsidian-agent` should not shell out to `jj` directly.

#### 2. Inter-repo dependency management is still repo-local and fragile

`obsidian-agent` depends on `obsidian-ops` through a pinned Git URL:

- `obsidian-ops @ git+https://github.com/...@<commit>`

That is useful while bootstrapping. It is not a good long-term dependency contract for the refactor.

Problems with the current approach:

- offline or restricted-network development is harder
- release/version compatibility is not explicit
- local multi-repo development is awkward
- CI/reproducibility relies on external Git resolution rather than a package index or workspace strategy

Before Forge depends on this stack, the versioning story should be cleaned up.

Acceptable options include:

- publish `obsidian-ops` and depend on a semantic version range
- use a workspace/local editable strategy for active development and a published version for CI
- at minimum, standardize a documented local-dev install flow across the repos

The current direct Git pin is a bootstrap mechanism, not a stable foundation.

#### 3. The Python version floor should be aligned deliberately

`obsidian-ops` requires `>=3.12`. `obsidian-agent` requires `>=3.13`.

That may be intentional, but if it is not, it should be resolved now.

For a split architecture, version skew at the dependency boundary adds friction with little upside. If `obsidian-agent` does not actually require 3.13-only language/runtime features, the better move is probably to align both repos on the same floor. If it does require 3.13, that should be made explicit and documented as a deliberate stack choice.

#### 4. The tool contract is still slightly behind the planned richer ops surface

The agent exposes a sensible tool set, but it is still narrower than the intended long-term `obsidian-ops` feature set.

Current gaps relative to the broader design direction:

- no tool for `set_frontmatter`
- no tool for `delete_frontmatter_field`
- no richer patch tool abstractions
- no structured edit results beyond human-readable strings

The current tool set is good enough for the simplified Forge MVP. It is not yet the final shape for a more capable multi-interface backend.

#### 5. The caller contract around `current_file` is correct but incomplete at the system level

`obsidian-agent` explicitly expects a vault-relative `current_file`. It does not resolve web URLs. That is a good boundary for the agent itself.

But the system-level question remains unresolved:

- how will Forge translate `current_url_path` into `current_file` after the split?

The refactor docs already identified this as an issue through the old Go `PathIndex`. That still needs a concrete system decision before the Forge refactor starts.

The agent is not wrong here. The missing piece is the integration contract above it.

### Required changes before the Forge refactor

#### Required

1. Move the full VCS undo/restore lifecycle into `obsidian-ops`.
   `obsidian-agent` should not invoke raw `jj` subprocesses directly.

2. Replace the direct Git dependency on `obsidian-ops` with a deliberate versioning strategy.

3. Resolve the Forge-to-agent caller contract for current-file resolution.
   Either Forge resolves URL paths before proxying, or the API contract changes to send `current_file` directly. Do not leave this implicit.

4. Align Python version requirements intentionally.
   Either standardize them or document why they differ.

#### Strongly recommended

1. Expand the tool layer only after the `obsidian-ops` API is hardened.
2. Consider making FastAPI/uvicorn optional if the library-first usage is expected to matter outside the HTTP service case.
3. Add structured logging comparable to what the old Go stack had, especially around tool calls and operation timing.

## Cross-Library Findings

### 1. The dependency direction is good

This is the strongest part of the current state.

The direction is now:

- Forge -> `obsidian-agent` HTTP API
- `obsidian-agent` -> `obsidian-ops` library
- `obsidian-ops` -> vault filesystem and `jj`

That is the right direction and should not be reversed.

### 2. The abstraction leak is now mostly in version control

The main boundary leak left between the two libraries is VCS behavior.

If that is fixed, the split becomes substantially cleaner.

### 3. The packaging story is weaker than the code story

Both libraries are stronger in code structure than in install/release ergonomics.

The biggest packaging issues are:

- `obsidian-ops` optional-server mismatch
- `obsidian-agent` direct Git dependency on `obsidian-ops`
- minimal repo docs for `obsidian-ops`

This is normal for early extraction work, but it should be cleaned up before the Forge refactor depends on the repos as infrastructure.

### 4. The tests are good enough to support refactoring, but not equally mature

`obsidian-agent` is already operating like a maintained package.

`obsidian-ops` has a strong core but still looks like a freshly extracted library whose packaging and HTTP layer have not been normalized yet.

That suggests the right sequencing:

- harden `obsidian-ops` first
- then align `obsidian-agent` to the finalized ops contract
- then cut Forge over to the external backend

## Comparison Against Existing Forge Go Behavior

The current Go backend in `forge/internal/ops` contains six major concerns:

- tool-calling LLM runtime
- sandboxed vault file operations
- mutation locking
- Jujutsu wrappers
- URL-path resolution through `PathIndex`
- HTTP handlers for apply/undo/health

The extracted repos now map to those concerns like this:

### Good mapping

- Go vault tools -> `obsidian-ops`
- Go mutation lock -> `obsidian-ops`
- Go Jujutsu wrapper -> `obsidian-ops`
- Go agent runtime -> `obsidian-agent`
- Go HTTP handlers -> `obsidian-agent`

### Still unresolved

- Go `PathIndex` ownership after extraction
- rebuild timing semantics once Forge becomes proxy-only
- whether Forge passes `current_file` or `current_url_path`

This means the libraries are close to ready, but the system integration boundary is not yet complete.

## Recommended Pre-Forge Work Plan

### Phase 1: Harden `obsidian-ops`

1. Fix server packaging and `devenv` so the full repo test suite runs in the default environment.
2. Expand frontmatter patch semantics to support nested updates explicitly.
3. Consolidate full undo/restore behavior into the `Vault` API.
4. Write proper package documentation and usage examples.
5. Lock down the API contract for file glob behavior and health response shape.

### Phase 2: Align `obsidian-agent`

1. Remove direct `jj` subprocess logic from the agent and use the hardened `obsidian-ops` VCS API only.
2. Replace the Git-pinned dependency with a deliberate release/workspace strategy.
3. Align Python runtime requirements.
4. Add logging/observability expectations for long-running or tool-heavy operations.
5. Keep the current `/api/apply` contract stable while the Forge split happens.

### Phase 3: Finalize system contracts before touching Forge

1. Decide where URL-to-file resolution lives.
   My recommendation: keep it out of `obsidian-agent`; let Forge resolve the current page to a vault-relative path before proxying.

2. Decide whether the first cut uses two processes or three.
   My recommendation: for the Forge migration, run two processes:
   - Forge
   - `obsidian-agent`

   Let `obsidian-agent` import `obsidian-ops` directly.

   Keep the `obsidian-ops` HTTP server as optional, not required for the MVP integration.

3. Confirm timeout coordination.
   Forge proxy timeout must exceed agent timeout.

4. Confirm rebuild semantics.
   If Forge rebuilds from filesystem watch events, document the race explicitly and accept it as an MVP tradeoff.

## Final Verdict

### `obsidian-ops`

Verdict: promising foundation, not yet hardened enough.

It already owns the right responsibilities and its core library behavior is strong. But it still needs API hardening, packaging cleanup, and a better-defined server contract before it should be treated as the stable architecture boundary under Forge.

### `obsidian-agent`

Verdict: substantially closer to ready.

The repo is in better operational shape than `obsidian-ops`. The tests pass, the API contract is usable, and the core split from Forge is correct. The main issue is that it still reaches below its intended layer for part of the Jujutsu undo lifecycle, and its dependency/versioning story with `obsidian-ops` is still bootstrap-grade.

### Overall

The extraction was the right move.

Do not revert it, and do not collapse the repos back together.

But do not begin the Forge-side cutover yet.

The correct next step is to harden the dependency boundary first, especially:

1. consolidate VCS behavior into `obsidian-ops`
2. clean up `obsidian-ops` packaging and dev environment
3. replace `obsidian-agent`'s direct Git pin with a stable dependency strategy
4. settle the Forge-to-agent `current_file` contract

Once those are done, the Forge refactor should be significantly lower-risk and the boundary will actually be hard rather than aspirational.
