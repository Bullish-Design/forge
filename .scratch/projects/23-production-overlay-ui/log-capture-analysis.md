# Analysis: Log Capture Strategy (Task 1.3)

## Goal
Determine how to capture LLM request/response data from obsidian-agent API calls so the production overlay can display:
- Request payload (instruction, file path, etc.)
- Response payload (modifications, status, etc.)
- Metadata (tokens, duration, model name, timestamp)
- System prompt (for debugging)

## Option A: Client-Side Fetch Intercept

### Implementation
Monkey-patch the global `fetch()` function in the browser to log `/api/agent/*` calls.

```javascript
const originalFetch = window.fetch;
window.fetch = async function(...args) {
  const [url, options] = args;
  const startTime = performance.now();

  if (typeof url === 'string' && url.includes('/api/agent/')) {
    // Log the request
    logger.logRequest(url, options);

    // Call original fetch
    const response = await originalFetch(...args);
    const cloned = response.clone();
    const duration = performance.now() - startTime;

    // Log the response
    const data = await cloned.json();
    logger.logResponse(url, data, duration);

    return response;
  }
  return originalFetch(...args);
};
```

### Pros
- ✅ **Transparent**: No backend changes required
- ✅ **Complete**: Captures all request/response data automatically
- ✅ **Metadata**: Easy to measure duration, detect errors
- ✅ **No latency**: Minimal overhead (synchronous logging)
- ✅ **Ephemeral**: Logs cleared on reload (good for privacy)

### Cons
- ❌ **Fragile**: Relies on implementation details; doesn't work if agent uses XMLHttpRequest or other HTTP libs
- ❌ **Limited metadata**: Can't easily extract token counts or model name without parsing response
- ❌ **Response cloning**: Must clone response to read body; slight overhead
- ❌ **Cross-origin**: May be blocked by CORS if agent is on different domain (unlikely in this case)

### Token Counting
If the agent response includes token counts in a standard field (e.g., `response.usage { prompt_tokens, completion_tokens }`), we can extract them. Otherwise, we'd need:
- Token counter library (tiktoken) - requires JS port (large)
- OR ask obsidian-agent to include token info in response

### System Prompt Access
System prompt is typically not included in responses. Options:
- Add a `/api/agent/system-prompt` endpoint to retrieve it
- OR parse it from the first response (if agent includes it)
- OR hardcode common prompts in overlay UI

---

## Option B: Backend Response Injection

### Implementation
Modify obsidian-agent responses to include a `_forge_logs` field with metadata.

```json
{
  "ok": true,
  "modified": [...],
  "_forge_logs": {
    "duration_ms": 2345,
    "tokens_prompt": 245,
    "tokens_completion": 267,
    "tokens_total": 512,
    "model": "claude-sonnet-4-20250514",
    "system_prompt_hash": "abc123...",
    "request_id": "uuid-12345"
  }
}
```

Then the overlay can:
1. Intercept responses (same as Option A)
2. Extract `_forge_logs` field
3. Store request + response + logs together

### Pros
- ✅ **Complete metadata**: All info available in standard format
- ✅ **No guessing**: Token counts, model, duration from authoritative source
- ✅ **Coupled**: Backend can log more context (e.g., function calls, intermediate steps)
- ✅ **Extensible**: Easy to add more fields later

### Cons
- ❌ **Backend changes**: Requires modifying obsidian-agent
- ❌ **Version coupling**: Need obsidian-agent v0.4+ (current is v0.3.1)
- ❌ **Out of scope**: This project is supposed to NOT modify backend
- ❌ **Blocker**: Need obsidian-agent to be updated first
- ❌ **Privacy**: Logs stored in responses (harder to keep ephemeral)

### Timeline
- Requires PRs to obsidian-agent, review, release
- Dependency bump in forge
- Would delay this project

---

## Option C: Status Polling

### Implementation
Poll `/api/agent/status` endpoint periodically to get historical log entries.

```javascript
const logs = [];
setInterval(async () => {
  const status = await fetch('/api/agent/status').then(r => r.json());
  // status.recent_calls: [ { id, timestamp, duration, tokens, ... }, ...]
  logs = status.recent_calls;
  renderer.update(logs);
}, 1000);
```

### Pros
- ✅ **No client hacks**: Uses documented API
- ✅ **Server-authoritative**: Agent maintains log state
- ✅ **Complete**: Can include all request/response context
- ✅ **Cleaner**: No fetch patching, separate data fetching

### Cons
- ❌ **Latency**: 1-second polling interval (adjust trade-off between freshness and overhead)
- ❌ **Stale logs**: May miss calls if polling interval is too long
- ❌ **Backend changes**: Still requires obsidian-agent to expose status endpoint
- ❌ **Storage**: Agent needs to maintain log buffer in memory
- ❌ **Complex**: More moving parts (polling, cache invalidation)

### Requirements
- `/api/agent/status` endpoint returns `{ recent_calls: [...] }`
- Each call includes: id, timestamp, duration, tokens, model, request, response

---

## Comparative Table

| Criteria | Option A (Fetch) | Option B (Response) | Option C (Polling) |
|----------|------------------|---------------------|-------------------|
| **Implementation difficulty** | Medium | High | Medium |
| **Backend changes** | None | Yes (breaking) | Yes (adding endpoint) |
| **Metadata availability** | Low (need parsing) | High | High |
| **Latency/freshness** | Real-time | Real-time | ~1s delay |
| **Reliability** | Medium (fragile) | High | High |
| **Privacy** | Good (ephemeral) | Fair | Fair |
| **Extensibility** | Low | High | High |
| **Timeline** | Can start now | Blocked on v0.4 | Depends on agent API |

---

## Recommendation

**Option A (Fetch Intercept)** is the best starting point because:
1. **No blocking dependencies** - Can proceed immediately
2. **Already sufficient** - Can capture request/response payloads
3. **Can augment later** - If obsidian-agent adds `/api/status` or response fields, we can upgrade
4. **Non-intrusive** - Demo overlay and forge untouched
5. **Ephemeral logs** - Good privacy model for browser UI

### Limitations to Accept
- **Token counts**: Won't have exact counts without parsing model-specific tokenizers
  - Workaround: Parse response to detect token fields if agent includes them
  - OR: Display "~123 tokens" estimates based on character count
- **System prompt**: Won't have unless agent includes it in response
  - Workaround: Generic system prompt template in UI ("Optimizing note...")
- **No intermediate steps**: Just final request/response, not intermediate LLM calls

### Migration Path
If obsidian-agent later exposes:
- `/api/agent/status` with recent_calls - Can switch to Option C (better)
- Response `_forge_logs` field - Can upgrade to Option B (best)

We can implement detection and graceful fallback:
```javascript
// Try to get token info from response field
const tokens = response._forge_logs?.tokens_total
  || extractTokensFromResponse(response)
  || estimateTokenCount(request + response);
```

---

## Implementation Plan (Option A)

### Phase 2.5 (Log Capture) Tasks
1. **Create logger.js module**
   - `class Logger { logRequest(), logResponse(), getLogs() }`
   - Store in memory as array of objects
   - Implement cap (max 100 entries)

2. **Implement fetch intercept**
   - Monkey-patch global fetch
   - Detect `/api/agent/*` URLs
   - Clone request body (if needed)
   - Clone response and store JSON
   - Measure duration

3. **Parse response for metadata**
   - Look for `response.usage` (OpenAI format)
   - Look for `response._forge_logs` (custom format)
   - Extract `response.model` if present
   - Fallback to sensible defaults

4. **Handle errors gracefully**
   - Network errors → log as error entry
   - Malformed JSON → log raw text
   - Rate limiting (429) → special handling

### Log Entry Structure
```javascript
{
  id: 'uuid-or-index',
  timestamp: Date.now(),
  method: 'POST',
  url: '/api/agent/apply',
  request: { instruction: '...', current_file: '...' },
  response: { ok: true, modified: [...] },
  duration_ms: 2345,
  tokens_prompt: 245,  // if available
  tokens_completion: 267,  // if available
  model: 'claude-sonnet-4-20250514',  // if available
  status: 200,
  error: null,  // set if response.ok === false or network error
}
```

---

## Decision Required
**Proceed with Option A (Fetch Intercept)** to unblock Phase 2 implementation?

